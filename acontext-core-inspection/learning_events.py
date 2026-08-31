import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from ..env import LOG


async def report_learning_event(
    event_type: str,
    session_id: object,
    learning_space_id: object,
    *,
    task_id: object | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    url = os.getenv("ACU_LEARNING_EVENT_URL", "").strip()
    token = os.getenv("ACU_LEARNING_EVENT_TOKEN", "").strip()
    if not url or not token:
        return

    body: dict[str, Any] = {
        "event_id": f"acontext_{uuid4().hex}",
        "event_type": event_type,
        "session_id": str(session_id),
        "learning_space_id": str(learning_space_id),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
    if task_id is not None:
        body["task_id"] = str(task_id)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
    except Exception as error:
        LOG.warning(
            "acu.learning_event_report_failed",
            event_type=event_type,
            session_id=str(session_id),
            error=str(error)[:240],
        )
