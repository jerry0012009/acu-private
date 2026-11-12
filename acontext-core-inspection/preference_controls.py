"""Authenticated owner corrections using existing skill metadata and space locks."""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from uuid import UUID

from preference_document import preference_fields, patch_preference
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

router = APIRouter(prefix="/internal/preferences")


class Correction(BaseModel):
    action: str
    summary: str | None = Field(default=None, max_length=400)
    rule: str | None = Field(default=None, max_length=30000)
    scope: str | None = Field(default=None, max_length=30000)
    exceptions: str | None = Field(default=None, max_length=30000)
    expected_hash: str = Field(min_length=64, max_length=64)


def authorize(value):
    expected = os.getenv("ACU_LEARNING_EVENT_TOKEN", "")
    if not expected or not hmac.compare_digest(value or "", "Bearer " + expected):
        raise HTTPException(403)


@router.get("/{space_id}")
async def controls(space_id: UUID, authorization: str | None = Header(default=None)):
    authorize(authorization)
    from acontext_core.infra.db import DB_CLIENT
    from acontext_core.schema.orm import AgentSkill
    from acontext_core.service.data import learning_space as LS
    from acontext_core.service.data.artifact import get_artifact_by_path, decode_content
    async with DB_CLIENT.get_session_context() as db:
        ids, error = (await LS.get_learning_space_skill_ids(db, space_id)).unpack()
        if error:
            raise HTTPException(404)
        skills = (await db.execute(select(AgentSkill).where(AgentSkill.id.in_(ids)))).scalars().all()
        records = []
        for skill in skills:
            if skill.name in ("daily-logs", "user-general-facts") or (skill.description or "").startswith("[ACU_PREFERENCE_INDEX]"):
                continue
            artifact, error = (await get_artifact_by_path(db, skill.disk_id, "/", "SKILL.md")).unpack()
            if error:
                raise HTTPException(503, "Preference unavailable")
            content = decode_content(artifact.asset_meta.get("content", ""), None)
            control = (skill.meta or {}).get("acu_control", {})
            records.append({"id": str(skill.id), "summary": (control.get("summary") if control.get("disabled") else skill.description),
                            **preference_fields(content), "disabled": control.get("disabled", False),
                            "revision": hashlib.sha256(content.encode()).hexdigest(), "updatedAt": skill.updated_at.isoformat()})
        return {"records": records}


@router.put("/{space_id}/{skill_id}")
async def correct(space_id: UUID, skill_id: UUID, change: Correction, authorization: str | None = Header(default=None)):
    authorize(authorization)
    if change.action not in ("edit", "disable", "restore"):
        raise HTTPException(400, "Unknown preference action")
    if change.action == "edit" and change.summary is not None and not change.summary.strip():
        raise HTTPException(400, "Summary cannot be empty")
    from acontext_core.infra.db import DB_CLIENT
    from acontext_core.schema.orm import AgentSkill, LearningSpace
    from acontext_core.service.data import learning_space as LS
    from acontext_core.service.data.artifact import get_artifact_by_path, decode_content, upload_and_build_artifact_meta, upsert_artifact
    from acontext_core.service.utils import check_redis_lock_or_set, release_redis_lock
    async with DB_CLIENT.get_session_context() as db:
        space = (await db.execute(select(LearningSpace).where(LearningSpace.id == space_id))).scalar_one_or_none()
        if space is None:
            raise HTTPException(404)
        project_id = space.project_id
    lock = f"skill_learn.{space_id}"
    if not await check_redis_lock_or_set(project_id, lock, ttl_seconds=120):
        raise HTTPException(409, "Learning in progress; retry after completion")
    try:
        async with DB_CLIENT.get_session_context() as db:
            ids, error = (await LS.get_learning_space_skill_ids(db, space_id)).unpack()
            if error or skill_id not in ids:
                raise HTTPException(404)
            skill = (await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))).scalar_one()
            if skill.name in ("daily-logs", "user-general-facts") or (skill.description or "").startswith("[ACU_PREFERENCE_INDEX]"):
                raise HTTPException(400, "This record is not an editable preference")
            artifact, error = (await get_artifact_by_path(db, skill.disk_id, "/", "SKILL.md")).unpack()
            if error:
                raise HTTPException(503)
            original = decode_content(artifact.asset_meta.get("content", ""), None)
            if hashlib.sha256(original.encode()).hexdigest() != change.expected_hash:
                raise HTTPException(409, "Preference changed; refresh before editing")
            updated = original
            changed = []
            if change.action == "edit":
                try:
                    updated, changed = patch_preference(original, change.model_dump(exclude_none=True))
                except ValueError as error:
                    raise HTTPException(409, str(error)) from error
            meta, detail = await upload_and_build_artifact_meta(project_id, "/", f"before-user-edit-{change.expected_hash[:16]}.md", original)
            if not (await upsert_artifact(db, skill.disk_id, "/", f"before-user-edit-{change.expected_hash[:16]}.md", meta, meta=detail)).ok():
                raise HTTPException(503)
            control = dict((skill.meta or {}).get("acu_control", {}))
            if not control.get("disabled"):
                control["summary"] = skill.description or ""
            if change.action in ("disable", "restore"):
                control["disabled"] = change.action == "disable"
            control["updated_at"] = datetime.now(timezone.utc).isoformat()
            if change.action == "edit":
                if change.summary is not None:
                    control["summary"] = change.summary.strip()
                control.update(origin="user_explicit", edited_fields=changed)
                original = updated
            # A revision also changes for disable/restore, preventing stale editor writes.
            original += "\n<!-- preference-control: " + control["updated_at"] + " -->\n"
            skill.meta = {**(skill.meta or {}), "acu_control": control}
            skill.description = ("[ACU_PREFERENCE_DISABLED] " if control.get("disabled") else "") + control["summary"]
            skill.updated_at = datetime.now(timezone.utc)
            meta, detail = await upload_and_build_artifact_meta(project_id, "/", "SKILL.md", original)
            if not (await upsert_artifact(db, skill.disk_id, "/", "SKILL.md", meta, meta=detail)).ok():
                raise HTTPException(503)
            record = {"id": str(skill_id), "summary": control["summary"], **preference_fields(original),
                      "disabled": bool(control.get("disabled")), "revision": hashlib.sha256(original.encode()).hexdigest(),
                      "updatedAt": control["updated_at"]}
        return {"updated": True, "record": record}
    finally:
        await release_redis_lock(project_id, lock)
