"""Authenticated owner corrections using existing skill metadata and space locks."""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from uuid import UUID

import yaml
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

router = APIRouter(prefix="/internal/preferences")


class Correction(BaseModel):
    action: str
    summary: str = Field(default="", max_length=400)
    scope: str = Field(default="", max_length=400)
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
                            "scope": control.get("scope", ""), "disabled": control.get("disabled", False),
                            "revision": hashlib.sha256(content.encode()).hexdigest(), "updatedAt": skill.updated_at.isoformat()})
        return {"records": records}


@router.put("/{space_id}/{skill_id}")
async def correct(space_id: UUID, skill_id: UUID, change: Correction, authorization: str | None = Header(default=None)):
    authorize(authorization)
    if change.action not in ("edit", "disable", "restore"):
        raise HTTPException(400, "Unknown preference action")
    if change.action == "edit" and (not change.summary.strip() or not change.scope.strip()):
        raise HTTPException(400, "Rule and applicability are required")
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
            meta, detail = await upload_and_build_artifact_meta(project_id, "/", f"before-user-edit-{change.expected_hash[:16]}.md", original)
            if not (await upsert_artifact(db, skill.disk_id, "/", f"before-user-edit-{change.expected_hash[:16]}.md", meta, meta=detail)).ok():
                raise HTTPException(503)
            control = dict((skill.meta or {}).get("acu_control", {}))
            if not control.get("disabled"):
                control["summary"] = skill.description or ""
            control["disabled"] = change.action == "disable"
            control["updated_at"] = datetime.now(timezone.utc).isoformat()
            if change.action == "edit":
                control.update(summary=change.summary.strip(), scope=change.scope.strip(), origin="user_explicit")
                front = yaml.safe_dump({"name": skill.name, "description": control["summary"], "type": "user_preference", "origin": "user_explicit"}, allow_unicode=True, sort_keys=False)
                original = "---\n" + front + "---\n# 用户修订的偏好\n\n## Applies When\n" + control["scope"] + "\n\n## Prefer\n" + control["summary"] + "\n\n## Evidence\n用户通过账户偏好编辑确认。此前内容保存在本文件的 before-user-edit 附件中，不作为当前规则。\n"
            # A revision also changes for disable/restore, preventing stale editor writes.
            original += "\n<!-- preference-control: " + control["updated_at"] + " -->\n"
            skill.meta = {**(skill.meta or {}), "acu_control": control}
            skill.description = ("[ACU_PREFERENCE_DISABLED] " if control["disabled"] else "") + control["summary"]
            skill.updated_at = datetime.now(timezone.utc)
            meta, detail = await upload_and_build_artifact_meta(project_id, "/", "SKILL.md", original)
            if not (await upsert_artifact(db, skill.disk_id, "/", "SKILL.md", meta, meta=detail)).ok():
                raise HTTPException(503)
        return {"updated": True}
    finally:
        await release_redis_lock(project_id, lock)
