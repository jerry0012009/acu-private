"""Prepare and independently execute a configuration-only Acontext Core release."""

import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

import yaml


ENV_FILE = Path("/root/jerry/claw-router/deploy/alpha/.env")
BASE_COMPOSE = Path("/tmp/acontext-acceptance/compose.yaml")
RUNTIME_CONFIG = Path("/tmp/acontext-acceptance/core-config.yaml")
CORE = "private-acu-acontext-acceptance-core-1"
PROTECTED = (
    "acu-router-alpha-acu-router-1", "acu-router-alpha-new-api-1",
    "private-acu-acontext-acceptance-api-1",
)


def command(args, timeout=120):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args[:4])}")
    return result.stdout.strip()


def inspect(name):
    return json.loads(command(["docker", "inspect", name]))[0]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_private(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + ".new-" + secrets.token_hex(4))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data if isinstance(data, bytes) else data.encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def compose(*files):
    return ["docker", "compose", "--env-file", str(ENV_FILE)] + [
        argument for file in files for argument in ("-f", str(file))
    ]


def validate_config(config):
    if config != {
        "llm_simple_model": "gpt-6.1-sol",
        "llm_openai_completion_kwargs": {"reasoning_effort": "medium"},
    }:
        raise ValueError("Release configuration must be exactly GPT-6.1 Sol medium")


def production_projection(base, config):
    validate_config(config)
    candidate = copy.deepcopy(base)
    candidate["services"]["core"]["environment"]["LLM_SIMPLE_MODEL"] = config["llm_simple_model"]
    for name, service in base["services"].items():
        if name != "core" and candidate["services"][name] != service:
            raise ValueError("A Core release cannot change another service")
    return candidate


def prepare(release):
    release.mkdir(mode=0o700, parents=True, exist_ok=False)
    config_bytes = (Path(__file__).parent / "core-config.yaml").read_bytes()
    config = yaml.safe_load(config_bytes)
    validate_config(config)
    baseline = BASE_COMPOSE.read_bytes()
    previous_config = RUNTIME_CONFIG.read_bytes()
    current = inspect(CORE)
    protected = {name: inspect(name)["Id"] for name in PROTECTED}
    image = current["Image"]
    command(["docker", "image", "inspect", image])
    command(["docker", "image", "tag", image, f"acu-private-core:rollback-{release.name.lower()}"])
    candidate = production_projection(yaml.safe_load(baseline), config)
    for name, contents in {
        "compose.before.yaml": baseline, "config.before.yaml": previous_config,
        "compose.candidate.yaml": yaml.safe_dump(candidate, sort_keys=False),
        "core-config.yaml": config_bytes,
        "core-image.yaml": yaml.safe_dump({"services": {"core": {"image": image}}}),
        "core_release.py": Path(__file__).read_bytes(),
        "learning_canary.py": (Path(__file__).parent / "learning_canary.py").read_bytes(),
    }.items():
        write_private(release / name, contents)
    command(compose(release / "compose.candidate.yaml", release / "core-image.yaml") + ["config", "-q"])
    manifest = {
        "revision": command(["git", "-C", str(Path(__file__).parent), "rev-parse", "HEAD"]),
        "coreId": current["Id"], "coreImage": image, "protectedIds": protected,
        "baseHash": digest(baseline), "oldConfigHash": digest(previous_config),
        "configHash": digest(config_bytes), "preparedAt": time.time(),
    }
    write_private(release / "manifest.json", json.dumps(manifest, indent=2))
    print(json.dumps({"status": "prepared", "release": str(release), **manifest}), flush=True)


def prepare_canary(release, port):
    manifest = json.loads((release / "manifest.json").read_text())
    base = yaml.safe_load((release / "compose.before.yaml").read_text())
    canary = release / "canary"
    canary.mkdir(mode=0o700)
    project = "acu-core-canary-" + secrets.token_hex(4)
    base["name"] = project
    for name, service in base["services"].items():
        service.pop("build", None)
        if name == "core":
            service["image"] = manifest["coreImage"]
        elif name != "seaweedfs-setup":
            service["image"] = inspect(f"private-acu-acontext-acceptance-{name}-1")["Image"]
        if "volumes" in service:
            service["volumes"] = [
                volume.replace("/tmp/acontext-acceptance/", str(canary) + "/")
                for volume in service["volumes"]
            ]
        service["networks"] = {"default": {}}
    core = base["services"]["core"]
    core["networks"]["alpha-backend"] = {}
    core["environment"].update({
        "LLM_SIMPLE_MODEL": "gpt-6.1-sol", "ACU_USAGE_REPORT_URL": "",
        "ACU_USAGE_REPORT_TOKEN": "", "ACU_LEARNING_EVENT_URL": "",
        "ACU_LEARNING_EVENT_TOKEN": "", "ACU_FILM_LEARNING_SPACE_ID": "",
    })
    api = base["services"]["api"]
    api["ports"] = [f"127.0.0.1:{port}:8029"]
    api["environment"]["ROOT_API_BEARER_TOKEN"] = secrets.token_hex(32)
    api["environment"]["ROOT_SECRET_PEPPER"] = secrets.token_hex(32)
    api["environment"]["APP_EXTERNALURL"] = f"http://127.0.0.1:{port}"
    write_private(canary / "core-config.yaml", (release / "core-config.yaml").read_bytes())
    write_private(canary / "compose.yaml", yaml.safe_dump(base, sort_keys=False))
    write_private(canary / "identity.json", json.dumps({"project": project, "port": port}))
    command(compose(canary / "compose.yaml") + ["config", "-q"])
    print(json.dumps({"project": project, "port": port, "compose": str(canary / "compose.yaml")}))


def verify_protected(manifest):
    for name, container_id in manifest["protectedIds"].items():
        info = inspect(name)
        if info["Id"] != container_id or info["State"].get("Health", {}).get("Status") != "healthy":
            raise RuntimeError(f"Protected service changed or is unhealthy: {name}")


def wait_idle(timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output = command([
            "docker", "exec", "private-acu-acontext-acceptance-rabbitmq-1",
            "rabbitmqctl", "-q", "list_queues", "name", "messages_ready", "messages_unacknowledged",
        ])
        rows = [line.split() for line in output.splitlines()]
        queues = [row for row in rows if len(row) == 3 and row[1].isdigit() and row[2].isdigit()]
        if not any(row[0] == "learning.skill.agent.entry" for row in queues):
            raise RuntimeError("Core queue inventory could not be verified")
        if all(int(row[1]) == 0 and int(row[2]) == 0 for row in queues):
            return
        time.sleep(3)
    raise RuntimeError("Core queues did not become idle; production was not replaced")


def apply(release):
    manifest = json.loads((release / "manifest.json").read_text())
    status_path = release / "status.json"
    with open("/run/lock/acu-private-core-model.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_protected(manifest)
        if inspect(CORE)["Id"] != manifest["coreId"]:
            raise RuntimeError("Core changed after release preparation")
        if digest(BASE_COMPOSE.read_bytes()) != manifest["baseHash"] or digest(
            RUNTIME_CONFIG.read_bytes()
        ) != manifest["oldConfigHash"]:
            raise RuntimeError("Production configuration changed after preparation")
        preflight = json.loads((release / "canary-success.json").read_text())
        if preflight["model"] != "gpt-6.1-sol" or preflight["reasoningEffort"] != "medium":
            raise RuntimeError("The isolated end-to-end canary has not passed")
        if digest((release / "core-config.yaml").read_bytes()) != manifest["configHash"]:
            raise RuntimeError("Frozen release configuration changed after preparation")
        wait_idle()
        changed = False
        try:
            changed = True
            write_private(RUNTIME_CONFIG, (release / "core-config.yaml").read_bytes())
            write_private(BASE_COMPOSE, (release / "compose.candidate.yaml").read_bytes())
            command(compose(BASE_COMPOSE, release / "core-image.yaml") + [
                "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                "--wait", "--wait-timeout", "150", "core",
            ], timeout=210)
            verify_protected(manifest)
            smoke = json.loads(command([
                sys.executable, str(release / "learning_canary.py"),
                "--api-url", "http://127.0.0.1:18029",
                "--api-container", "private-acu-acontext-acceptance-api-1",
                "--core-container", CORE,
                "--pg-container", "private-acu-acontext-acceptance-pg-1",
            ], timeout=690))
            verify_protected(manifest)
            current = inspect(CORE)
            if current["Image"] != manifest["coreImage"] or current["RestartCount"] != 0:
                raise RuntimeError("Unexpected Core image or restart loop")
            write_private(status_path, json.dumps({
                "status": "deployed", "revision": manifest["revision"],
                "configHash": manifest["configHash"], "coreId": current["Id"],
                "coreImage": current["Image"], "completedAt": time.time(), "canary": smoke,
                "protectedIds": manifest["protectedIds"],
            }, indent=2))
            print(status_path.read_text(), flush=True)
        except BaseException as error:
            if changed:
                write_private(RUNTIME_CONFIG, (release / "config.before.yaml").read_bytes())
                write_private(BASE_COMPOSE, (release / "compose.before.yaml").read_bytes())
                command(compose(BASE_COMPOSE, release / "core-image.yaml") + [
                    "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                    "--wait", "--wait-timeout", "150", "core",
                ], timeout=210)
            verify_protected(manifest)
            write_private(status_path, json.dumps({
                "status": "rolled_back" if changed else "not_started",
                "error": str(error), "completedAt": time.time(),
            }, indent=2))
            raise


def terminated(*_):
    raise RuntimeError("Release terminated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "prepare-canary", "apply"))
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--canary-port", type=int, default=18030)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, terminated)
    if args.action == "prepare":
        prepare(args.release.resolve())
    elif args.action == "prepare-canary":
        prepare_canary(args.release.resolve(), args.canary_port)
    else:
        apply(args.release.resolve())
