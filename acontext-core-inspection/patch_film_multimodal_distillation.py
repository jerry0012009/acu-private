from pathlib import Path
from typing import Any


PROMPT_PATH = Path("/app/acontext_core/llm/prompt/skill_distillation.py")
CONTROLLER_PATH = Path(
    "/app/acontext_core/service/controller/skill_learner.py"
)


def append_once(path: Path, sentinel: str, patch: str) -> None:
    source = path.read_text(encoding="utf-8")
    if sentinel in source:
        raise RuntimeError(f"ACU patch already exists in {path}")
    path.write_text(source.rstrip() + patch, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if old not in source:
        raise RuntimeError(f"Acontext source marker is unavailable in {path}: {old[:100]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def _image_url(part: Any) -> tuple[str, str] | None:
    if getattr(part, "type", None) != "image":
        return None
    meta = getattr(part, "meta", None)
    if not isinstance(meta, dict):
        return None
    url = meta.get("url")
    if isinstance(url, dict):
        url = url.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    if not (
        url.startswith("data:image/")
        or url.startswith("https://")
        or url.startswith("http://")
    ):
        return None
    detail = meta.get("detail")
    if detail not in {"low", "high", "auto"}:
        detail = "high"
    return url, detail


def build_film_distillation_content(
    text: str, task_messages: list[Any]
) -> str | list[dict[str, Any]]:
    image_contents: list[dict[str, Any]] = []
    image_count = 0
    for message_index, message in enumerate(task_messages, 1):
        for part_index, part in enumerate(getattr(message, "parts", []) or [], 1):
            image = _image_url(part)
            if image is None:
                continue
            url, detail = image
            image_count += 1
            image_contents.extend(
                [
                    {
                        "type": "text",
                        "text": (
                            f"\n[图像证据 {image_count}，来自第 {message_index} 条任务消息"
                            f"的第 {part_index} 个素材]\n"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": url, "detail": detail},
                    },
                ]
            )

    if image_count == 0:
        return text

    return [
        {
            "type": "text",
            "text": (
                f"{text}\n\n"
                "## 图像证据\n"
                "下面的图像与上方任务消息中的图片 Part 按顺序绑定。"
                "请将图像观察与文字 JSON 结合，并只记录有证据支持的影视语言。"
            ),
        },
        *image_contents,
    ]


def main() -> None:
    append_once(
        PROMPT_PATH,
        "ACU customization: preserve film image evidence in distillation",
        r'''

# ACU customization: preserve film image evidence in distillation.
def _acu_film_image_url(part):
    if getattr(part, "type", None) != "image":
        return None
    meta = getattr(part, "meta", None)
    if not isinstance(meta, dict):
        return None
    url = meta.get("url")
    if isinstance(url, dict):
        url = url.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    if not (
        url.startswith("data:image/")
        or url.startswith("https://")
        or url.startswith("http://")
    ):
        return None
    detail = meta.get("detail")
    if detail not in {"low", "high", "auto"}:
        detail = "high"
    return url, detail


def _acu_build_film_distillation_content(text, task_messages):
    image_contents = []
    image_count = 0
    for message_index, message in enumerate(task_messages, 1):
        for part_index, part in enumerate(getattr(message, "parts", []) or [], 1):
            image = _acu_film_image_url(part)
            if image is None:
                continue
            url, detail = image
            image_count += 1
            image_contents.extend(
                [
                    {
                        "type": "text",
                        "text": (
                            f"\n[图像证据 {image_count}，来自第 {message_index} 条任务消息"
                            f"的第 {part_index} 个素材]\n"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": url, "detail": detail},
                    },
                ]
            )

    if image_count == 0:
        return text

    return [
        {
            "type": "text",
            "text": (
                f"{text}\n\n"
                "## 图像证据\n"
                "下面的图像与上方任务消息中的图片 Part 按顺序绑定。"
                "请将图像观察与文字 JSON 结合，并只记录有证据支持的影视语言。"
            ),
        },
        *image_contents,
    ]


_acu_original_pack_distillation_input = (
    SkillDistillationPrompt.pack_distillation_input
)


def _acu_space_bound_pack_distillation_input(
    cls,
    finished_task,
    task_messages,
    all_tasks,
    skill_descriptions=None,
    include_images=False,
):
    text = _acu_original_pack_distillation_input(
        finished_task,
        task_messages,
        all_tasks,
        skill_descriptions,
    )
    if not include_images:
        return text
    return _acu_build_film_distillation_content(text, task_messages)


SkillDistillationPrompt.pack_distillation_input = classmethod(
    _acu_space_bound_pack_distillation_input
)
''',
    )

    replace_once(
        CONTROLLER_PATH,
        "    user_content = SkillDistillationPrompt.pack_distillation_input(\n"
        "        finished_task, task_messages, all_tasks, skill_descriptions\n"
        "    )\n",
        "    user_content = SkillDistillationPrompt.pack_distillation_input(\n"
        "        finished_task,\n"
        "        task_messages,\n"
        "        all_tasks,\n"
        "        skill_descriptions,\n"
        "        include_images=is_film_space(learning_space_id),\n"
        "    )\n"
        "    input_image_count = (\n"
        "        sum(\n"
        "            1\n"
        "            for item in user_content\n"
        "            if isinstance(item, dict) and item.get(\"type\") == \"image_url\"\n"
        "        )\n"
        "        if isinstance(user_content, list)\n"
        "        else 0\n"
        "    )\n"
        "    wide[\"input_image_count\"] = input_image_count\n"
        "    wide[\"input_images_included\"] = input_image_count > 0\n",
    )

    replace_once(
        CONTROLLER_PATH,
        '            "element_count": element_count,\n'
        "        },\n",
        '            "element_count": element_count,\n'
        '            "input_image_count": input_image_count,\n'
        '            "input_images_included": input_image_count > 0,\n'
        "        },\n",
    )


if __name__ == "__main__":
    main()
