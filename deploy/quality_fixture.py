"""Create an isolated learning fixture; never mutate production containers or data."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import yaml


def inspect(name):
    return json.loads(subprocess.check_output(["docker", "inspect", name]))[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    directory = Path(args.directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    base = yaml.safe_load(Path("/tmp/acontext-acceptance/compose.yaml").read_text())
    private_routes = json.loads(Path("/var/lib/acu/acontext-slots/routes.json").read_text())
    active_core = inspect(private_routes["core"]["container"])
    active_api = inspect(private_routes["api"]["container"])
    core_env = dict(item.split("=", 1) for item in active_core["Config"]["Env"])
    project = "acu-quality-fixture-" + secrets.token_hex(4)
    base["name"] = project
    for name, service in base["services"].items():
        service.pop("build", None)
        service.pop("container_name", None)
        service["networks"] = {"default": {}}
        if name == "core":
            service["image"] = args.image
        elif name == "api":
            service["image"] = active_api["Image"]
        elif name != "seaweedfs-setup":
            service["image"] = inspect(f"private-acu-acontext-acceptance-{name}-1")["Image"]
        service["volumes"] = [value.replace("/tmp/acontext-acceptance/", str(directory) + "/")
                              for value in service.get("volumes", [])]
        service.pop("restart", None)
    core = base["services"]["core"]
    core["networks"]["alpha-backend"] = {}
    # Core has relay egress on the production network. Never resolve common
    # state-service aliases there: use this fixture's unique container names.
    for key, value in list(core["environment"].items()):
        if isinstance(value, str):
            for service in ("pg", "redis", "rabbitmq", "seaweedfs", "jaeger"):
                value = value.replace(f"@{service}:", f"@{project}-{service}-1:")
                value = value.replace(f"://{service}:", f"://{project}-{service}-1:")
            core["environment"][key] = value
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_SIMPLE_MODEL"):
        core["environment"][key] = core_env[key]
    core["environment"].update({
        "ACU_USAGE_REPORT_URL": "", "ACU_USAGE_REPORT_TOKEN": "",
        "ACU_LEARNING_EVENT_URL": "", "ACU_LEARNING_EVENT_TOKEN": secrets.token_hex(32),
        "ACU_FILM_LEARNING_SPACE_ID": "", "ACU_DEPLOY_TOKEN": secrets.token_hex(32),
        "OTEL_ENABLED": "false",
    })
    base["services"]["api"]["ports"] = []
    base["services"]["rabbitmq"]["tmpfs"] = ["/var/lib/rabbitmq:uid=999,gid=999,mode=0700"]
    base["services"]["rabbitmq"]["user"] = "999:999"
    base["services"]["api"]["environment"].update({
        "ROOT_API_BEARER_TOKEN": secrets.token_hex(32),
        "ROOT_SECRET_PEPPER": secrets.token_hex(32),
    })
    base["networks"] = {"default": {}, "alpha-backend": {"external": True, "name": "acu-router-alpha_alpha-backend"}}
    for name, text in {
        "compose.yaml": yaml.safe_dump(base, sort_keys=False),
        "core-config.yaml": Path("/tmp/acontext-acceptance/core-config.yaml").read_text(),
        "identity.json": json.dumps({"project": project}),
    }.items():
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(text)
    subprocess.run(["docker", "compose", "-f", str(directory / "compose.yaml"), "config", "-q"], check=True)
    print(json.dumps({"project": project, "directory": str(directory)}))


if __name__ == "__main__":
    main()
