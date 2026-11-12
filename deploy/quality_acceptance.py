"""Real-model preference learning acceptance in an isolated fixture only."""
import argparse
import json
from pathlib import Path
import time
import uuid
from learning_canary import command, container_environment, request, ledger_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.project.startswith("acu-quality-fixture-"):
        raise ValueError("Only isolated quality fixtures are allowed")
    api = args.project + "-api-1"
    info = json.loads(command(["docker", "inspect", api]))[0]
    address = info["NetworkSettings"]["Networks"][args.project + "_default"]["IPAddress"]
    base = "http://" + address + ":8029"
    token = "sk-ac-" + container_environment(api)["ROOT_API_BEARER_TOKEN"]
    user = "quality-acceptance-" + uuid.uuid4().hex
    space = request(base, token, "POST", "/learning_spaces", {"user": user})["id"]
    report = {"space": space, "project": args.project, "cases": []}
    cases = [
        ("long-context-independent-preferences",
         "learning_trigger: user_dissatisfaction\nexperience_id: quality-independent-1\n"
         "feedback_reason: Two independent reusable choices were missed.\n"
         + ("Earlier unrelated tool output: build succeeded.\n" * 100)
         + "\nUSER: For all future work reports, conclusions and decisions first, technical details last. "
         "For our public art exhibition posters, I prefer expansive bright imagery and minimal text. "
         "Do not apply the compact work-report style to those posters. "
         "These are independent preferences. ASSISTANT: I used detailed logs first and dense text posters. "
         "USER: Redo both; keep the two different contexts and choices.\n",
         2),
        ("no-portable-preference",
         "learning_trigger: user_dissatisfaction\nexperience_id: quality-skip-1\n"
         "feedback_reason: A one-off factual correction, not a preference.\n"
         "USER: The value on line 12 was 8081, not 8080. Correct that typo only. "
         "This is a factual correction for this task, not a reusable preference or workflow rule.\n",
         0),
        ("explicit-choice-after-long-prefix",
         "learning_trigger: explicit_user_preference\nexperience_id: quality-explicit-1\n"
         + ("Earlier context: unrelated implementation detail.\n" * 100)
         + "USER: For our brand's public announcements I choose a warm conversational voice "
         "instead of formal bureaucratic language. Keep this standard for future announcements, "
         "but legal agreements still need precise formal wording.\n",
         1),
    ]
    initial = request(base, token, "GET", f"/learning_spaces/{space}/skills")
    previous_ids = {skill["id"] for skill in initial if skill["name"] not in ("daily-logs", "user-general-facts")}
    for name, text, minimum_new in cases:
        session = request(base, token, "POST", "/session", {"user": user, "disable_task_tracking": False})["id"]
        request(base, token, "POST", f"/learning_spaces/{space}/learn", {"session_id": session})
        request(base, token, "POST", f"/session/{session}/messages", {
            "format": "openai", "blob": {"role": "user", "content": text},
        })
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            state = request(base, token, "GET", f"/learning_spaces/{space}/sessions/{session}")
            if state.get("status") == "failed":
                raise RuntimeError(name + " failed")
            if state.get("status") == "completed":
                break
            time.sleep(3)
        else:
            raise RuntimeError(name + " timed out")
        skills = request(base, token, "GET", f"/learning_spaces/{space}/skills")
        skills = [skill for skill in skills if skill["name"] not in ("daily-logs", "user-general-facts")]
        ids = {skill["id"] for skill in skills}
        if minimum_new and len(ids - previous_ids) < minimum_new:
            raise RuntimeError("Independent preferences were not split")
        if not minimum_new and ids != previous_ids:
            raise RuntimeError("One-off fact created a preference")
        documents = []
        for skill in skills:
            result = request(base, token, "GET", f"/agent_skills/{skill['id']}/file?file_path=SKILL.md")
            documents.append({"id": skill["id"], "name": skill["name"], "content": result.get("content")})
        report["cases"].append({"name": name, "session": session, "status": "completed",
                                "newDocuments": len(ids - previous_ids), "documents": documents,
                                "ledger": ledger_rows(args.project + "-pg-1", [session])})
        previous_ids = ids
        print(json.dumps({"case": name, "documents": len(ids), "status": "completed"}), flush=True)
        path = Path(args.output)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        path.chmod(0o600)


if __name__ == "__main__":
    main()
