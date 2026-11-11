import asyncio
import sys
import types
import unittest
from enum import Enum
from unittest.mock import AsyncMock, patch

from deployment import ConsumerLifecycle


class ConsumerLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_draining_waits_for_delivered_work_before_closing_channel_and_usage(self):
        events = []
        client = types.SimpleNamespace(disconnect=AsyncMock())
        ledger = types.SimpleNamespace(flush=AsyncMock(side_effect=lambda: events.append("usage")), pending_count=lambda: 0)
        lifecycle = ConsumerLifecycle(client, ledger)
        started = asyncio.Event()
        finish = asyncio.Event()

        async def handle():
            lifecycle.tasks.add(asyncio.current_task())
            started.set()
            try:
                await finish.wait()
                events.append("ack")
            finally:
                lifecycle.tasks.discard(asyncio.current_task())

        queue = types.SimpleNamespace(cancel=AsyncMock(side_effect=lambda tag: events.append("cancel")))
        channel = types.SimpleNamespace(is_closed=False, close=AsyncMock(side_effect=lambda: events.append("close")))
        lifecycle.subscriptions = [(queue, "consumer-tag")]
        lifecycle.channels = [channel]
        lifecycle.accepting = True
        task = asyncio.create_task(handle())
        await started.wait()
        draining = asyncio.create_task(lifecycle.drain())
        await asyncio.sleep(0)
        self.assertFalse(lifecycle.accepting)
        self.assertFalse(draining.done())
        channel.close.assert_not_called()
        self.assertFalse(task.cancelled())
        finish.set()
        await draining
        self.assertEqual(events, ["cancel", "ack", "usage", "close"])
        self.assertEqual(lifecycle.snapshot()["pendingTasks"], 0)

    async def test_usage_failure_prevents_successful_retirement(self):
        ledger = types.SimpleNamespace(flush=AsyncMock(side_effect=RuntimeError("failed")), pending_count=lambda: 1)
        lifecycle = ConsumerLifecycle(types.SimpleNamespace(), ledger)
        channel = types.SimpleNamespace(is_closed=False, close=AsyncMock())
        lifecycle.channels = [channel]
        with self.assertRaisesRegex(RuntimeError, "failed"):
            await lifecycle.drain()
        self.assertEqual(lifecycle.error, "consumer_or_ledger_drain_failed")
        channel.close.assert_not_called()

    async def test_standby_does_not_consume_until_explicit_activation(self):
        lifecycle = ConsumerLifecycle(types.SimpleNamespace(), types.SimpleNamespace())
        lifecycle.activate = AsyncMock()
        with patch.dict("os.environ", {"ACU_CORE_STANDBY": "true"}):
            running = asyncio.create_task(lifecycle.run())
            await asyncio.sleep(0)
            lifecycle.activate.assert_not_called()
            lifecycle.finished.set()
            await running

    async def test_activate_is_idempotent_and_handles_one_callback_without_replay(self):
        class SpecialHandler(Enum):
            NONE = "none"
        callbacks = []
        queue = types.SimpleNamespace(consume=AsyncMock(side_effect=lambda cb: callbacks.append(cb) or "tag"))
        channel = types.SimpleNamespace(set_qos=AsyncMock(), is_closed=False, close=AsyncMock())
        client = types.SimpleNamespace(
            connect=AsyncMock(), connection=types.SimpleNamespace(channel=AsyncMock(return_value=channel)),
            consumers={"test": types.SimpleNamespace(prefetch_count=1, handler=lambda: None)},
            _setup_consumer_on_channel=AsyncMock(return_value=queue), _process_message_with_tracing=AsyncMock(),
        )
        lifecycle = ConsumerLifecycle(client, types.SimpleNamespace())
        stub = types.ModuleType("acontext_core.infra.async_mq")
        stub.SpecialHandler = SpecialHandler
        with patch.dict(sys.modules, {"acontext_core.infra.async_mq": stub}):
            await lifecycle.activate()
            await lifecycle.activate()
        self.assertEqual(len(callbacks), 1)
        await callbacks[0]("message")
        client._process_message_with_tracing.assert_awaited_once_with(client.consumers["test"], "message")


if __name__ == "__main__":
    unittest.main()
