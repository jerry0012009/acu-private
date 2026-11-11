"""Hold a real learning run across consumer drain, then resume its queue."""
import json
import subprocess
import sys
import time
from urllib.request import Request, urlopen


def main():
    core = sys.argv[1]
    command = sys.argv[2:]
    details = json.loads(subprocess.check_output(["docker", "inspect", core]))[0]
    env = dict(item.split("=", 1) for item in details["Config"]["Env"])
    address = details["NetworkSettings"]["Networks"]["acu-router-alpha_alpha-backend"]["IPAddress"]
    def control(action):
        request = Request(f"http://{address}:8000/internal/deployment/{action}",
                          headers={"Authorization": "Bearer " + env["ACU_DEPLOY_TOKEN"]},
                          method="GET" if action == "status" else "POST")
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        end = time.monotonic() + 90
        while time.monotonic() < end:
            if control("status")["pendingTasks"] > 0:
                break
            if process.poll() is not None:
                raise RuntimeError("canary ended before active-task drain test")
            time.sleep(0.5)
        else:
            raise RuntimeError("no in-flight learning task observed")
        control("drain")
        end = time.monotonic() + 180
        while time.monotonic() < end:
            status = control("status")
            if status["error"]:
                raise RuntimeError("Core drain reported failure")
            if not status["draining"] and not status["pendingTasks"] and not status["pendingUsage"]:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("drain did not complete; no forced termination")
        assert not status["accepting"]
        control("activate")
        output, error = process.communicate(timeout=600)
        if process.returncode:
            raise RuntimeError("learning canary failed after drain: " + error[-500:])
        print(json.dumps({"drainedWhileProcessing": True, "pendingTasksAfterDrain": 0,
                          "pendingUsageAfterDrain": 0, "learning": json.loads(output.strip().splitlines()[-1])}))
    finally:
        if process.poll() is None:
            control("activate")
            process.terminate()
            process.communicate(timeout=20)


if __name__ == "__main__":
    main()
