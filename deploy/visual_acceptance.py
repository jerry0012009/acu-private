"""Verify actual image evidence traverses account distillation in a fixture."""
import argparse
import base64
import json
import struct
import time
import uuid
import zlib
from pathlib import Path
from learning_canary import command, container_environment, request


def image():
    # Deterministic solid warm-red reference, not a claim about a real user's taste.
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
    size = 64
    pixels = b"".join(b"\0" + bytes([230, 45, 55]) * size for _ in range(size))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.project.startswith("acu-quality-fixture-"):
        raise ValueError("Isolated fixture required")
    api = args.project + "-api-1"
    info = json.loads(command(["docker", "inspect", api]))[0]
    base = "http://" + info["NetworkSettings"]["Networks"][args.project + "_default"]["IPAddress"] + ":8029"
    token = "sk-ac-" + container_environment(api)["ROOT_API_BEARER_TOKEN"]
    user = "visual-fixture-" + uuid.uuid4().hex
    space = request(base, token, "POST", "/learning_spaces", {"user": user})["id"]
    session = request(base, token, "POST", "/session", {"user": user, "disable_task_tracking": False})["id"]
    request(base, token, "POST", f"/learning_spaces/{space}/learn", {"session_id": session})
    request(base, token, "POST", f"/session/{session}/messages", {"format": "openai", "blob": {"role": "user", "content": [
        {"type": "text", "text": "learning_trigger: explicit_user_preference\nexperience_id: visual-fixture-1\n用户：以后给这个艺术节做海报，我偏好参考图这种主色，不要默认用冷蓝色。只记这个项目的色彩取向，不推断字体、人物或构图。请根据真实图片描述主色。"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image()).decode() }},
    ]}})
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        state = request(base, token, "GET", f"/learning_spaces/{space}/sessions/{session}")
        if state.get("status") == "failed":
            raise RuntimeError("Visual learning failed")
        if state.get("status") == "completed":
            break
        time.sleep(3)
    else:
        raise RuntimeError("Visual learning timed out")
    skills = request(base, token, "GET", f"/learning_spaces/{space}/skills")
    documents = []
    for skill in skills:
        if skill["name"] in ("daily-logs", "user-general-facts"):
            continue
        content = request(base, token, "GET", f"/agent_skills/{skill['id']}/file?file_path=SKILL.md")["content"]["raw"]
        documents.append(content)
    if not documents or not any("红" in text or "red" in text.lower() for text in documents):
        raise RuntimeError("Image color evidence missing")
    path = Path(args.output)
    path.write_text(json.dumps({"session": session, "space": space, "documents": documents}, ensure_ascii=False, indent=2))
    path.chmod(0o600)
    print(json.dumps({"visualEvidence": "red-reference", "documents": len(documents), "session": session}))


if __name__ == "__main__":
    main()
