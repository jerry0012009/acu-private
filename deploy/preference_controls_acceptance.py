"""Exercise owner corrections against an isolated Core and its real database."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from learning_canary import command, container_environment, request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    if not args.project.startswith("acu-quality-fixture-"):
        raise RuntimeError("Isolated fixture required")
    report = json.loads(Path(args.report).read_text())
    core = args.project + "-core-1"
    address = json.loads(command(["docker", "inspect", core]))[0]["NetworkSettings"]["Networks"][args.project + "_default"]["IPAddress"]
    env = container_environment(core)
    token = env["ACU_LEARNING_EVENT_TOKEN"]
    def call(method, path, body=None, expected=200, bearer=token):
        req = Request(f"http://{address}:8000/internal/preferences/{path}", method=method,
                      headers={"Authorization": "Bearer " + bearer, "Content-Type": "application/json"},
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(req, timeout=30) as response:
                assert response.status == expected
                return json.load(response)
        except HTTPError as error:
            assert error.code == expected, error.code
    space = report["space"]
    call("GET", space, expected=403, bearer="invalid")
    records = call("GET", space)["records"]
    assert records
    record = records[0]
    path = space + "/" + record["id"]
    call("PUT", path, {"action": "disable", "expected_hash": record["revision"]})
    paused = next(r for r in call("GET", space)["records"] if r["id"] == record["id"])
    assert paused["disabled"]
    call("PUT", path, {"action": "restore", "expected_hash": record["revision"]}, expected=409)
    call("PUT", path, {"action": "restore", "expected_hash": paused["revision"]})
    restored = next(r for r in call("GET", space)["records"] if r["id"] == record["id"])
    assert not restored["disabled"]
    call("PUT", path, {"action": "edit", "summary": "Keep conclusions first.", "scope": "Weekly project reports only.", "expected_hash": restored["revision"]})
    edited = next(r for r in call("GET", space)["records"] if r["id"] == record["id"])
    assert edited["summary"] == "Keep conclusions first."
    assert edited["scope"] == "Weekly project reports only."
    assert edited["rule"] == restored["rule"], "Editing summary must preserve the actual rule"
    assert edited["exceptions"] == restored["exceptions"], "Editing summary must preserve exceptions"
    call("PUT", path, {"action":"edit", "exceptions":"Legal agreements retain formal wording.", "expected_hash":edited["revision"]})
    scoped = next(r for r in call("GET", space)["records"] if r["id"] == record["id"])
    call("PUT", path, {"action":"edit", "rule":"Decisions before implementation details.", "expected_hash":scoped["revision"]})
    edited = next(r for r in call("GET", space)["records"] if r["id"] == record["id"])
    assert edited["exceptions"] == "Legal agreements retain formal wording."
    assert edited["scope"] == "Weekly project reports only."
    api = args.project + "-api-1"
    api_ip = json.loads(command(["docker", "inspect", api]))[0]["NetworkSettings"]["Networks"][args.project + "_default"]["IPAddress"]
    key = "sk-ac-" + container_environment(api)["ROOT_API_BEARER_TOKEN"]
    other = request("http://" + api_ip + ":8029", key, "POST", "/learning_spaces", {"user": "other-owner-controls"})["id"]
    call("PUT", other + "/" + record["id"], {"action": "disable", "expected_hash": edited["revision"]}, expected=404)
    print(json.dumps({"auth": True, "ownership": True, "disableRestore": True, "staleRevision": True, "edit": True}))


if __name__ == "__main__":
    main()
