"""Control queue ownership without cancelling delivered learning tasks."""
import asyncio
import hmac
import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException


class ConsumerLifecycle:
    def __init__(self, client, ledger):
        self.client = client
        self.ledger = ledger
        self.channels = []
        self.subscriptions = []
        self.tasks = set()
        self.accepting = False
        self.draining = False
        self.error = None
        self.lock = asyncio.Lock()
        self.finished = asyncio.Event()
        self.drain_task = None

    def _role(self, active):
        filename = os.environ.get("ACU_CORE_ROLE_FILE")
        if filename:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            if active:
                temporary = path.with_suffix(".tmp")
                with temporary.open("w") as output:
                    output.write("active\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            else:
                path.unlink(missing_ok=True)

    async def activate(self):
        async with self.lock:
            if self.accepting:
                return
            if self.draining or self.error:
                raise RuntimeError("consumer drain is incomplete")
            await self.client.connect()
            try:
                from acontext_core.infra.async_mq import SpecialHandler

                for config in self.client.consumers.values():
                    channel = await self.client.connection.channel()
                    self.channels.append(channel)
                    await channel.set_qos(prefetch_count=config.prefetch_count)
                    queue = await self.client._setup_consumer_on_channel(config, channel)
                    if isinstance(config.handler, SpecialHandler):
                        continue

                    async def receive(message, selected=config):
                        task = asyncio.current_task()
                        self.tasks.add(task)
                        try:
                            await self.client._process_message_with_tracing(selected, message)
                        finally:
                            self.tasks.discard(task)

                    tag = await queue.consume(receive)
                    self.subscriptions.append((queue, tag))
                self.accepting = True
                self._role(True)
            except BaseException:
                await self._cancel_subscriptions()
                await self._finish_tasks()
                await self._close_channels()
                raise

    async def _cancel_subscriptions(self):
        for queue, tag in self.subscriptions:
            await queue.cancel(tag)
        self.subscriptions.clear()
        # Let callbacks already delivered by the channel register their tasks.
        await asyncio.sleep(0)

    async def _finish_tasks(self):
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def _close_channels(self):
        for channel in self.channels:
            if not channel.is_closed:
                await channel.close()
        self.channels.clear()

    async def drain(self, preserve_role=False):
        async with self.lock:
            if not preserve_role:
                self._role(False)
            self.draining = True
            self.accepting = False
            try:
                # Keep channels open until delivered messages have ACKed and
                # any follow-up messages have been published.
                await self._cancel_subscriptions()
                await self._finish_tasks()
                await self.ledger.flush()
                await self._close_channels()
                self.error = None
            except Exception:
                self.error = "consumer_or_ledger_drain_failed"
                raise
            finally:
                self.draining = False

    async def run(self):
        role = os.environ.get("ACU_CORE_ROLE_FILE")
        if os.environ.get("ACU_CORE_STANDBY") != "true" or (role and Path(role).is_file()):
            await self.activate()
        await self.finished.wait()

    async def stop(self):
        if self.finished.is_set():
            return
        if self.drain_task:
            await self.drain_task
        await self.drain(preserve_role=self.accepting)
        await self.client.disconnect()
        self.finished.set()

    def snapshot(self):
        return {"accepting": self.accepting, "draining": self.draining,
                "pendingTasks": len(self.tasks), "pendingUsage": self.ledger.pending_count(),
                "error": self.error}


def install(app, ledger):
    import api
    from acontext_core.infra import async_mq

    lifecycle = ConsumerLifecycle(async_mq.MQ_CLIENT, ledger)
    api.start_mq = lifecycle.run
    # di.cleanup imports close_mq, which dispatches to this stop method.
    async_mq.MQ_CLIENT.stop = lifecycle.stop
    router = APIRouter(prefix="/internal/deployment")

    def authorize(authorization):
        expected = os.environ.get("ACU_DEPLOY_TOKEN", "")
        if not expected or not hmac.compare_digest(authorization or "", "Bearer " + expected):
            raise HTTPException(status_code=403)

    @router.get("/status")
    async def status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return lifecycle.snapshot()

    @router.post("/activate")
    async def activate(authorization: str | None = Header(default=None)):
        authorize(authorization)
        await lifecycle.activate()
        return lifecycle.snapshot()

    @router.post("/drain")
    async def drain(authorization: str | None = Header(default=None)):
        authorize(authorization)
        if not lifecycle.drain_task or lifecycle.drain_task.done():
            lifecycle.drain_task = asyncio.create_task(lifecycle.drain())
            # Retrieve failures immediately; status retains the error marker.
            lifecycle.drain_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        await asyncio.sleep(0)
        return lifecycle.snapshot()

    app.include_router(router)
    return lifecycle
