"""Check that a related new learning run preserves an owner's explicit exception."""
import argparse
import json
import time
from pathlib import Path
from learning_canary import command, container_environment, request
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True)
parser.add_argument("--report", required=True)
args = parser.parse_args()
if not args.project.startswith("acu-quality-fixture-"):
    raise RuntimeError("Isolated fixture required")
report = json.loads(Path(args.report).read_text())
space = report["space"]
api = args.project + "-api-1"
core = args.project + "-core-1"
network = args.project + "_default"
api_ip = json.loads(command(["docker", "inspect", api]))[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
core_ip = json.loads(command(["docker", "inspect", core]))[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
base = "http://" + api_ip + ":8029"
token = "sk-ac-" + container_environment(api)["ROOT_API_BEARER_TOKEN"]
core_token = container_environment(core)["ACU_LEARNING_EVENT_TOKEN"]
def records():
    with urlopen(Request(f"http://{core_ip}:8000/internal/preferences/{space}", headers={"Authorization":"Bearer " + core_token}), timeout=30) as response:
        return json.load(response)["records"]
before = next(record for record in records() if record["exceptions"] == "Legal agreements retain formal wording.")
session = request(base, token, "POST", "/session", {"user":"related-learning-edit-acceptance","disable_task_tracking":False})["id"]
request(base, token, "POST", f"/learning_spaces/{space}/learn", {"session_id":session})
request(base, token, "POST", f"/session/{session}/messages", {"format":"openai","blob":{"role":"user","content":"learning_trigger: explicit_user_preference\nexperience_id: owner-edit-related-learning\nUSER: For future weekly project reports, I also prefer decisions written as a short bullet list. Keep my existing legal-agreement exception and other explicit corrections unchanged."}})
deadline = time.monotonic() + 600
while time.monotonic() < deadline:
    status = request(base, token, "GET", f"/learning_spaces/{space}/sessions/{session}")["status"]
    if status == "failed":
        raise RuntimeError("Related learning failed")
    if status == "completed":
        break
    time.sleep(3)
else:
    raise RuntimeError("Related learning timed out")
after = next(record for record in records() if record["id"] == before["id"])
assert after["exceptions"] == before["exceptions"], "Owner exception overwritten"
print(json.dumps({"status":"completed","preservedOwnerException":True,"session":session}))
