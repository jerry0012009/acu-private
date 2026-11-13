"""Clone reviewed documents into an isolated fixture and verify summary-only writes."""
import argparse
import json
from pathlib import Path
import subprocess
from learning_canary import command, container_environment, request

parser = argparse.ArgumentParser()
parser.add_argument('--project', required=True)
parser.add_argument('--directory', required=True)
args = parser.parse_args()
if not args.project.startswith('acu-quality-fixture-'):
    raise ValueError('Isolated fixture required')
directory = Path(args.directory)
sources = json.loads((directory / 'sources.private.json').read_text())
plan = json.loads((directory / 'reviewed-plan.private.json').read_text())
api, core = args.project + '-api-1', args.project + '-core-1'
info = json.loads(command(['docker', 'inspect', api]))[0]
base = 'http://' + info['NetworkSettings']['Networks'][args.project + '_default']['IPAddress'] + ':8029'
token = 'sk-ac-' + container_environment(api)['ROOT_API_BEARER_TOKEN']
space = request(base, token, 'POST', '/learning_spaces', {'user': 'summary-maintenance-fixture'})['id']
script = '''import asyncio,json,sys
from uuid import UUID
from sqlalchemy import select
from acontext_core.infra.db import DB_CLIENT
from acontext_core.schema.orm import LearningSpace
from acontext_core.service.data.agent_skill import create_skill
from acontext_core.service.data.learning_space import add_skill_to_learning_space
data=json.load(sys.stdin)
async def main():
 mapping={}
 async with DB_CLIENT.get_session_context() as db:
  s=(await db.execute(select(LearningSpace).where(LearningSpace.id==UUID(data['space'])))).scalar_one()
  for source in data['sources']:
   skill,error=(await create_skill(db,s.project_id,source['content'],user_id=s.user_id)).unpack()
   if error: raise RuntimeError('seed failed')
   if not (await add_skill_to_learning_space(db,s.id,skill.id)).ok(): raise RuntimeError('attach failed')
   mapping[source['id']]=str(skill.id)
 print('MAPPING='+json.dumps(mapping))
asyncio.run(main())
'''
result = subprocess.run(['docker', 'exec', '-i', core, '/app/.venv/bin/python', '-B', '-c', script], input=json.dumps({'space': space, 'sources': sources}), text=True, capture_output=True, timeout=180, check=True)
mapping = json.loads(next(line[8:] for line in result.stdout.splitlines() if line.startswith('MAPPING=')))
for record in plan['records']:
    record['id'] = mapping[record['id']]
for review in plan['review']['reviews']:
    review['id'] = mapping[review['id']]
local = directory / 'fixture-plan.private.json'
local.write_text(json.dumps(plan)); local.chmod(0o600)
source = Path(__file__).resolve().parent.parent / 'acontext-core-inspection/maintain_preference_summaries.py'
for file, target in [(source, '/tmp/maintain.py'), (local, '/tmp/plan.json')]:
    subprocess.run(['docker', 'cp', str(file), core + ':' + target], check=True)
subprocess.run(['docker', 'exec', '-e', 'PYTHONPATH=/app', core, '/app/.venv/bin/python', '/tmp/maintain.py', '--space', space, '--plan', '/tmp/plan.json', '--output', '/tmp/maintenance-report.json', '--apply'], check=True, timeout=180)
for source in sources:
    current = request(base, token, 'GET', f"/agent_skills/{mapping[source['id']]}/file?file_path=SKILL.md")['content']['raw']
    original_body = source['content'].split('---', 2)[2]
    current_body = current.split('---', 2)[2]
    if current_body != original_body:
        raise RuntimeError('Rules/evidence changed')
subprocess.run(['docker', 'cp', core + ':/tmp/maintenance-report.json', str(directory / 'fixture-maintenance-report.private.json')], check=True)
print(json.dumps({'fixture': args.project, 'documents': len(sources), 'all_rule_and_evidence_bodies_unchanged': True}))
