"""Apply reviewed model summaries only, preserving rules/evidence and owner edits."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID
from sqlalchemy import select
from preference_document import patch_preference


async def apply_plan(args):
    from acontext_core.infra.db import DB_CLIENT
    from acontext_core.schema.orm import AgentSkill, LearningSpace
    from acontext_core.service.data import learning_space as LS
    from acontext_core.service.data.artifact import decode_content, get_artifact_by_path, upload_and_build_artifact_meta, upsert_artifact
    from acontext_core.service.utils import check_redis_lock_or_set, release_redis_lock
    plan = json.loads(args.plan.read_text())
    records = plan['records']
    approved = {r['id'] for r in plan.get('review', {}).get('reviews', []) if r.get('pass') is True}
    if not records or len({r['id'] for r in records}) != len(records):
        raise ValueError('Invalid plan')
    space_id = UUID(args.space)
    async with DB_CLIENT.get_session_context() as db:
        space = (await db.execute(select(LearningSpace).where(LearningSpace.id == space_id))).scalar_one()
        project_id = space.project_id
    lock = f'skill_learn.{space_id}'
    if not await check_redis_lock_or_set(project_id, lock, ttl_seconds=600):
        raise RuntimeError('Space busy; no writes')
    report = {'space': args.space, 'changed': [], 'skipped': [], 'applied': False}
    try:
        async with DB_CLIENT.get_session_context() as db:
            ids, error = (await LS.get_learning_space_skill_ids(db, space_id)).unpack()
            if error:
                raise RuntimeError('Space read failed')
            prepared = []
            for record in records:
                skill_id = UUID(record['id'])
                if skill_id not in ids:
                    raise ValueError('Source outside selected space')
                skill = (await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))).scalar_one()
                if (skill.meta or {}).get('acu_control') or (skill.description or '').startswith('[ACU_PREFERENCE_'):
                    report['skipped'].append({'id': record['id'], 'reason': 'owner-controlled or archived'})
                    continue
                artifact, error = (await get_artifact_by_path(db, skill.disk_id, '/', 'SKILL.md')).unpack()
                if error:
                    raise RuntimeError('Source unavailable')
                original = decode_content(artifact.asset_meta.get('content', ''), None)
                if hashlib.sha256(original.encode()).hexdigest() != record['sourceHash'] or skill.description != record['beforeDescription']:
                    report['skipped'].append({'id': record['id'], 'reason': 'changed since review'})
                    continue
                summary = record['description']
                if record['keep'] or summary == skill.description:
                    continue
                if record['id'] not in approved:
                    raise ValueError('Independent review required')
                quote = record['evidence']
                if not 1 <= len(summary) <= 100 or not quote or not (quote in original or quote in skill.description):
                    raise ValueError('Unverified summary')
                updated, changed = patch_preference(original, {'summary': summary})
                if changed != ['summary']:
                    raise ValueError('Unexpected rule mutation')
                prepared.append((skill, record, original, updated))
            for skill, record, original, updated in prepared:
                report['changed'].append({'id': record['id'], 'before': skill.description, 'after': record['description']})
                if not args.apply:
                    continue
                backup = 'before-summary-maintenance-' + record['sourceHash'][:16] + '.md'
                for filename, content in [(backup, original), ('SKILL.md', updated)]:
                    meta, detail = await upload_and_build_artifact_meta(project_id, '/', filename, content)
                    if not (await upsert_artifact(db, skill.disk_id, '/', filename, meta, meta=detail)).ok():
                        raise RuntimeError('Write failed')
                skill.description = record['description']
                skill.updated_at = datetime.now(timezone.utc)
                skill.meta = {**(skill.meta or {}), 'acu_summary_maintenance': {'model': plan['model'], 'source_hash': record['sourceHash'], 'backup': backup}}
                stored, error = (await get_artifact_by_path(db, skill.disk_id, '/', 'SKILL.md')).unpack()
                if error or decode_content(stored.asset_meta.get('content', ''), None) != updated:
                    raise RuntimeError('Readback failed')
        report['applied'] = args.apply
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        args.output.chmod(0o600)
        print(json.dumps({'applied': args.apply, 'changed': len(report['changed']), 'skipped': len(report['skipped'])}))
    finally:
        await release_redis_lock(project_id, lock)


async def run(args):
    from acontext_core.infra.s3 import close_s3
    from acontext_core.infra.redis import close_redis
    from acontext_core.infra.db import close_database
    try:
        await apply_plan(args)
    finally:
        await close_s3()
        await close_redis()
        await close_database()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--space', required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(run(parser.parse_args()))
