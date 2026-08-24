import asyncio
import json
import os
from typing import Any

import asyncpg

from acontext_core.telemetry.log import get_logging_contextvars


class AcontextUsageLedger:
    """Small fire-and-forget ledger for successful Core LLM completions."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2048)
        self._pool: asyncpg.Pool | None = None
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._pool is not None:
            return
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            return
        self._pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
        async with self._pool.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS acontext_llm_usage_ledger (
                  ledger_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  prompt_id TEXT NOT NULL,
                  model TEXT,
                  queue_name TEXT,
                  project_id TEXT,
                  session_id TEXT,
                  learning_space_id TEXT,
                  task_id TEXT,
                  input_tokens BIGINT NOT NULL DEFAULT 0,
                  cached_input_tokens BIGINT NOT NULL DEFAULT 0,
                  output_tokens BIGINT NOT NULL DEFAULT 0,
                  total_tokens BIGINT NOT NULL DEFAULT 0,
                  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_acontext_llm_usage_created
                  ON acontext_llm_usage_ledger (created_at DESC)
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_acontext_llm_usage_prompt_created
                  ON acontext_llm_usage_ledger (prompt_id, created_at DESC)
                """
            )
        self._worker = asyncio.create_task(self._drain())

    def record(self, event: str, fields: dict[str, Any]) -> None:
        if event != "llm.complete":
            return
        try:
            item = dict(fields)
            item["_logging_context"] = get_logging_contextvars()
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            # Losing one ledger row must never block or fail an agent task.
            pass

    async def _drain(self) -> None:
        while True:
            fields = await self._queue.get()
            try:
                if self._pool is None:
                    continue
                context = fields.pop("_logging_context", {})
                input_tokens = max(0, int(fields.get("input_tokens", 0) or 0))
                cached_tokens = max(0, int(fields.get("cached_tokens", 0) or 0))
                output_tokens = max(0, int(fields.get("output_tokens", 0) or 0))
                metadata = {
                    key: value
                    for key, value in fields.items()
                    if key
                    not in {
                        "prompt_id",
                        "model",
                        "input_tokens",
                        "cached_tokens",
                        "output_tokens",
                        "total_tokens",
                    }
                }
                async with self._pool.acquire() as connection:
                    await connection.execute(
                        """
                        INSERT INTO acontext_llm_usage_ledger
                          (prompt_id, model, queue_name, project_id, session_id,
                           learning_space_id, task_id, input_tokens,
                           cached_input_tokens, output_tokens, total_tokens,
                           metadata_json)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                        """,
                        str(fields.get("prompt_id") or "unknown"),
                        str(fields["model"]) if fields.get("model") else None,
                        str(context.get("queue_name")) if context.get("queue_name") else None,
                        str(context.get("project_id")) if context.get("project_id") else None,
                        str(context.get("session_id")) if context.get("session_id") else None,
                        (
                            str(context.get("learning_space_id"))
                            if context.get("learning_space_id")
                            else None
                        ),
                        str(context.get("task_id")) if context.get("task_id") else None,
                        input_tokens,
                        cached_tokens,
                        output_tokens,
                        max(0, int(fields.get("total_tokens", input_tokens + output_tokens) or 0)),
                        json.dumps(metadata, ensure_ascii=True, default=str),
                    )
            except Exception:
                # Ledger persistence is deliberately best effort and isolated from Core.
                pass
            finally:
                self._queue.task_done()


class LedgerLoggerProxy:
    def __init__(self, target: Any, ledger: AcontextUsageLedger) -> None:
        self._target = target
        self._ledger = ledger

    def info(self, event: str, **fields: Any) -> Any:
        result = self._target.info(event, **fields)
        self._ledger.record(event, fields)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


ledger = AcontextUsageLedger()


async def install() -> None:
    await ledger.start()
    import acontext_core.llm.complete.openai_sdk as openai_sdk

    openai_sdk.LOG = LedgerLoggerProxy(openai_sdk.LOG, ledger)
