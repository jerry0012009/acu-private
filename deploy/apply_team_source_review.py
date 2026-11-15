"""Apply a reviewed team-stock plan through Core storage helpers under its learning lock.

Run inside the selected Core dependency environment with PAYLOAD supplied by the
maintenance runner. No source deletion, grants, personal spaces or task replay.
"""
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select


async def apply_plan(payload):
    from acontext_core.infra.db import DB_CLIENT
    from acontext_core.schema.orm import AgentSkill, LearningSpace
    from acontext_core.service.data import learning_space as LS
    from acontext_core.service.data.artifact import (
        get_artifact_by_path, decode_content, upload_and_build_artifact_meta, upsert_artifact,
    )
    from acontext_core.service.utils import check_redis_lock_or_set, release_redis_lock

    configured = os.environ.get("ACU_FILM_LEARNING_SPACE_ID", "")
    if not configured or payload["space"] != configured:
        raise RuntimeError("Only the configured team space may be rebuilt")
    documents = payload["documents"]
    if not documents or len({doc["id"] for doc in documents}) != len(documents):
        raise RuntimeError("Invalid document coverage")
    space_id = UUID(configured)
    async with DB_CLIENT.get_session_context() as db:
        space = (await db.execute(select(LearningSpace).where(LearningSpace.id == space_id))).scalar_one()
        project_id = space.project_id
    lock = f"skill_learn.{space_id}"
    if not await check_redis_lock_or_set(project_id, lock, ttl_seconds=1800):
        raise RuntimeError("Team learning in progress; no writes performed")
    try:
        # Preflight the ENTIRE plan before uploading or changing any source.
        async with DB_CLIENT.get_session_context() as db:
            ids, error = (await LS.get_learning_space_skill_ids(db, space_id)).unpack()
            if error:
                raise RuntimeError("Team space unavailable")
            snapshots = {}
            already = []
            for doc in documents:
                skill_id = UUID(doc["id"])
                if skill_id not in ids:
                    raise RuntimeError("Document outside team space")
                skill = (await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))).scalar_one()
                if skill.name != doc["name"] or not skill.name.startswith("film-language-tapnow-"):
                    raise RuntimeError("Unexpected source identity")
                if (skill.meta or {}).get("acu_control"):
                    raise RuntimeError("Owner-controlled document needs separate review")
                previous = {}
                for filename in ("SKILL.md", "evidence.md", "learning-review.json"):
                    artifact, err = (await get_artifact_by_path(db, skill.disk_id, "/", filename)).unpack()
                    if not err and artifact:
                        previous[filename] = decode_content(artifact.asset_meta.get("content", ""), None)
                digest = hashlib.sha256(previous["SKILL.md"].encode()).hexdigest()
                if previous.get("learning-review.json") == doc["review"] and previous["SKILL.md"] == doc["content"] and skill.description == doc["description"]:
                    already.append(doc["id"])
                elif digest != doc["expected_hash"]:
                    raise RuntimeError("Source changed since review; plan rejected")
                snapshots[doc["id"]] = (skill, previous)
            if not payload.get("apply"):
                return {"validated": len(documents), "alreadyApplied": len(already), "written": 0}
            for doc in documents:
                if doc["id"] in already:
                    continue
                skill, previous = snapshots[doc["id"]]
                backup = json.dumps({"name": skill.name, "description": skill.description,
                                     "meta": skill.meta, "files": previous}, ensure_ascii=False, default=str)
                files = {
                    f"before-source-review-{doc['expected_hash'][:16]}.json": backup,
                    "SKILL.md": doc["content"],
                    "learning-review.json": doc["review"],
                }
                for filename, content in files.items():
                    meta, detail = await upload_and_build_artifact_meta(project_id, "/", filename, content)
                    if not (await upsert_artifact(db, skill.disk_id, "/", filename, meta, meta=detail)).ok():
                        raise RuntimeError("Source storage failed; database transaction rolled back")
                skill.description = doc["description"]
                skill.updated_at = datetime.now(timezone.utc)
                skill.meta = {**(skill.meta or {}), "acu_source_review": {
                    "batch": payload["batch"], "input_hash": doc["input_hash"],
                    "previous_hash": doc["expected_hash"], "origin": "source_trajectory_review",
                }}
            return {"validated": len(documents), "alreadyApplied": len(already),
                    "written": len(documents) - len(already), "sourceIdsPreserved": True}
    finally:
        await release_redis_lock(project_id, lock)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(apply_plan(json.load(sys.stdin)))))
