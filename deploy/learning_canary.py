"""Exercise real Acontext Task, Distillation, and Skill Learner workers."""

import argparse
import json
import subprocess
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def command(args, timeout=60):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def container_environment(name):
    info = json.loads(command(["docker", "inspect", name]))[0]
    return dict(item.split("=", 1) for item in info["Config"]["Env"])


def request(base, token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(
        base.rstrip("/") + "/api/v1" + path,
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=45) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Acontext {method} {path}: HTTP {error.code}") from None
    if result.get("code", 0) not in (0, 200, 201):
        raise RuntimeError(f"Acontext {method} {path}: unsuccessful response")
    return result.get("data", result)


def ledger_rows(pg_container, sessions):
    ids = ",".join("'" + str(uuid.UUID(item)) + "'" for item in sessions)
    sql = (
        "SELECT coalesce(json_agg(t),'[]'::json) FROM "
        "(SELECT prompt_id,model,input_tokens,output_tokens,"
        "metadata_json->>'execution_profile_id' execution_profile_id "
        f"FROM acontext_llm_usage_ledger WHERE session_id IN ({ids}) "
        "ORDER BY created_at) t"
    )
    return json.loads(command([
        "docker", "exec", pg_container, "psql", "-U", "acontext", "-d", "acontext",
        "-At", "-v", "ON_ERROR_STOP=1", "-c", sql,
    ]))


def validate_ledger(rows):
    if not rows or any(row["model"] != "gpt-6.1-sol" for row in rows):
        raise RuntimeError("Canary did not exclusively use gpt-6.1-sol")
    prompts = {row["prompt_id"] for row in rows}
    required = {"agent.task", "distill.skill_learner", "agent.skill_learner"}
    if not required.issubset(prompts):
        raise RuntimeError(f"Missing canary stages: {sorted(required - prompts)}")
    if any(not row["execution_profile_id"] for row in rows):
        raise RuntimeError("Canary completion is missing its execution Profile")


def run_canary(api_url, api_container, core_container, pg_container, timeout):
    env = container_environment(api_container)
    token = "sk-ac-" + env["ROOT_API_BEARER_TOKEN"]
    config = json.loads(command([
        "docker", "exec", core_container, "/app/.venv/bin/python", "-c",
        "import json;from acontext_core.util.config import get_local_core_config;"
        "c=get_local_core_config();print(json.dumps({'model':c.llm_simple_model,"
        "'kwargs':dict(c.llm_openai_completion_kwargs)}))",
    ]))
    if config != {
        "model": "gpt-6.1-sol", "kwargs": {"reasoning_effort": "medium"},
    }:
        raise RuntimeError("Core has not loaded the exact GPT-6.1 medium configuration")
    user = "acu-core-canary-" + uuid.uuid4().hex
    sessions = []
    space_id = None
    skill_ids = []
    try:
        space_id = request(api_url, token, "POST", "/learning_spaces", {
            "user": user, "meta": {"source": "core-model-release-canary"},
        })["id"]
        task_session = request(api_url, token, "POST", "/session", {
            "user": user, "disable_task_tracking": False,
        })["id"]
        sessions.append(task_session)
        request(api_url, token, "POST", f"/session/{task_session}/messages", {
            "format": "openai",
            "blob": {"role": "user", "content":
                     "Compare a compact table with decorative cards for a daily "
                     "operations screen. My priority is fast comparison of rows."},
        })
        learning_session = request(api_url, token, "POST", "/session", {
            "user": user, "disable_task_tracking": False,
        })["id"]
        sessions.append(learning_session)
        request(api_url, token, "POST", f"/learning_spaces/{space_id}/learn", {
            "session_id": learning_session,
        })
        request(api_url, token, "POST", f"/session/{learning_session}/messages", {
            "format": "openai",
            "blob": {"role": "user", "content":
                     "learning_trigger: user_dissatisfaction\n"
                     f"experience_id: {user}\n"
                     "feedback_reason: The user repeatedly requested compact, "
                     "work-first operational screens; decorative cards prevented "
                     "side-by-side comparison.\n"
                     "User: For operational dashboards I prefer dense tables, "
                     "small headings, and visible filters, not decorative cards.\n"
                     "Assistant: I made a large marketing hero and stacked cards.\n"
                     "User: Redo it. This repeats the same problem from previous "
                     "dashboards. Preserve row comparison, compact spacing and "
                     "visible controls whenever the task is repeated operations.\n"
                     "This is a synthetic release check in an isolated user space."},
        })
        deadline = time.monotonic() + timeout
        status = None
        while time.monotonic() < deadline:
            result = request(
                api_url, token, "GET",
                f"/learning_spaces/{space_id}/sessions/{learning_session}",
            )
            status = result.get("status")
            if status == "failed":
                raise RuntimeError("Acontext learning canary failed")
            if status == "completed":
                skills = request(api_url, token, "GET", f"/learning_spaces/{space_id}/skills")
                skill_ids = [item["id"] for item in skills]
                rows = ledger_rows(pg_container, sessions)
                if skill_ids and {"agent.task", "distill.skill_learner", "agent.skill_learner"}.issubset(
                    {row["prompt_id"] for row in rows}
                ):
                    validate_ledger(rows)
                    summary = {
                        "model": config["model"], "reasoningEffort": "medium",
                        "status": status, "skillCount": len(skill_ids),
                        "completionCount": len(rows),
                        "promptIds": sorted({row["prompt_id"] for row in rows}),
                        "profileIds": sorted({row["execution_profile_id"] for row in rows}),
                        "inputTokens": sum(int(row["input_tokens"]) for row in rows),
                        "outputTokens": sum(int(row["output_tokens"]) for row in rows),
                    }
                    return summary
            time.sleep(3)
        raise RuntimeError(f"Canary did not complete within {timeout}s; last status={status}")
    finally:
        # The generated user and its space are never a real account's resources.
        for session in sessions:
            request(api_url, token, "DELETE", f"/session/{session}")
        if space_id:
            request(api_url, token, "DELETE", f"/learning_spaces/{space_id}")
        for skill in skill_ids:
            request(api_url, token, "DELETE", f"/agent_skills/{skill}")
        request(api_url, token, "DELETE", f"/user/{user}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--api-container", required=True)
    parser.add_argument("--core-container", required=True)
    parser.add_argument("--pg-container", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    print(json.dumps(run_canary(
        args.api_url, args.api_container, args.core_container, args.pg_container, args.timeout,
    )), flush=True)
