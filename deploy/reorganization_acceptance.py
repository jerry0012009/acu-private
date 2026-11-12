"""Clone one source snapshot into a disposable space and test extractive splitting."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path
from learning_canary import command, container_environment, request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.project.startswith("acu-quality-fixture-"):
        raise ValueError("Isolated fixture required")
    sql = """WITH latest AS (
      SELECT skills_after_json FROM acu_private_learning_runs
      WHERE newapi_user_id='3' AND status='completed' ORDER BY received_at DESC LIMIT 1)
      SELECT f->>'content' FROM latest l,
      LATERAL jsonb_array_elements(l.skills_after_json) s,
      LATERAL jsonb_array_elements(s->'files') f
      WHERE s->>'name'='user-facing-rendered-quality-acceptance' AND f->>'path'='SKILL.md'"""
    original = command(["docker", "exec", "acu-router-alpha-postgres-acu-1", "sh", "-c",
                        'psql -X -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"', "sh", sql])
    if len(original) < 5000:
        raise RuntimeError("Expected oversized source snapshot")
    api = args.project + "-api-1"
    core = args.project + "-core-1"
    info = json.loads(command(["docker", "inspect", api]))[0]
    address = info["NetworkSettings"]["Networks"][args.project + "_default"]["IPAddress"]
    base = "http://" + address + ":8029"
    token = "sk-ac-" + container_environment(api)["ROOT_API_BEARER_TOKEN"]
    space = request(base, token, "POST", "/learning_spaces", {"user": "split-fixture-" + uuid.uuid4().hex})["id"]
    seed = '''import asyncio,json,sys
from uuid import UUID
from sqlalchemy import select
from acontext_core.infra.db import DB_CLIENT
from acontext_core.schema.orm import LearningSpace
from acontext_core.service.data.agent_skill import create_skill
from acontext_core.service.data.learning_space import add_skill_to_learning_space
data=json.load(sys.stdin)
async def main():
 async with DB_CLIENT.get_session_context() as db:
  s=(await db.execute(select(LearningSpace).where(LearningSpace.id==UUID(data['space'])))).scalar_one()
  skill,error=(await create_skill(db,s.project_id,data['content'],user_id=s.user_id)).unpack()
  if error: raise RuntimeError('seed failed')
  await add_skill_to_learning_space(db,s.id,skill.id)
asyncio.run(main())
'''
    result = subprocess.run(["docker", "exec", "-i", core, "/app/.venv/bin/python", "-B", "-c", seed],
                            input=json.dumps({"space": space, "content": original}), text=True,
                            capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Fixture seeding failed: " + result.stderr[-1000:])
    source = Path(__file__).resolve().parent.parent / "acontext-core-inspection/reorganize_preferences.py"
    subprocess.run(["docker", "cp", str(source), core + ":/tmp/reorganize_preferences.py"], check=True)
    log = Path(args.output + ".log")
    with log.open("w") as stream:
        log.chmod(0o600)
        result = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", core, "/app/.venv/bin/python", "-B",
            "/tmp/reorganize_preferences.py", "--space", space, "--skill", "user-facing-rendered-quality-acceptance",
            "--output", "/tmp/reorganization-report.json", "--apply"], stdout=stream, stderr=subprocess.STDOUT, timeout=360)
    if result.returncode:
        raise RuntimeError("Fixture restructuring failed; inspect private log")
    subprocess.run(["docker", "cp", core + ":/tmp/reorganization-report.json", args.output], check=True)
    Path(args.output).chmod(0o600)
    report = json.loads(Path(args.output).read_text())
    print(json.dumps({"appliedInFixture": report["applied"], "documents": len(report["documents"]), "sourceChars": len(original), "space": space}))


if __name__ == "__main__":
    main()
