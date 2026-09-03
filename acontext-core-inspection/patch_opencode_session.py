from pathlib import Path


OPENAI_COMPLETE_PATH = Path("/app/acontext_core/llm/complete/openai_sdk.py")
SKILL_LEARNER_SERVICE_PATH = Path("/app/acontext_core/service/skill_learner.py")


def add_session_header_to_completion(source: str) -> str:
    marker = '    prompt_id = prompt_kwargs.get("prompt_id", "...")\n'
    if marker not in source:
        raise RuntimeError("Acontext OpenAI completion prompt marker is unavailable")
    patched = source.replace(
        marker,
        marker
        + "\n"
        + "    _session_id = get_wide_event().get(\"session_id\")\n"
        + "    _extra_headers = (\n"
        + '        {"x-opencode-session": str(_session_id)}\n'
        + "        if _session_id\n"
        + "        else None\n"
        + "    )\n",
        1,
    )
    request_marker = "        **DEFAULT_CORE_CONFIG.llm_openai_completion_kwargs,\n"
    if request_marker not in patched:
        raise RuntimeError("Acontext OpenAI completion request marker is unavailable")
    return patched.replace(
        request_marker,
        "        extra_headers=_extra_headers,\n" + request_marker,
        1,
    )


def add_session_id_to_learning_consumers(source: str) -> str:
    marker = "async def process_skill_distillation(body: SkillLearnTask, message: Message):\n    wide = get_wide_event()\n"
    if marker not in source:
        raise RuntimeError("Acontext distillation consumer marker is unavailable")
    patched = source.replace(
        marker,
        marker + '    wide["session_id"] = str(body.session_id)\n',
        1,
    )
    marker = "async def process_skill_agent(body: SkillLearnDistilled, message: Message):\n    wide = get_wide_event()\n"
    if marker not in patched:
        raise RuntimeError("Acontext skill-agent consumer marker is unavailable")
    return patched.replace(
        marker,
        marker + '    wide["session_id"] = str(body.session_id)\n',
        1,
    )


def main() -> None:
    source = OPENAI_COMPLETE_PATH.read_text(encoding="utf-8")
    if "extra_headers=_extra_headers" in source:
        raise RuntimeError("Acontext OpenCode session header patch already exists")
    OPENAI_COMPLETE_PATH.write_text(
        add_session_header_to_completion(source),
        encoding="utf-8",
    )

    source = SKILL_LEARNER_SERVICE_PATH.read_text(encoding="utf-8")
    if 'wide["session_id"] = str(body.session_id)' in source:
        raise RuntimeError("Acontext learning consumer session patch already exists")
    SKILL_LEARNER_SERVICE_PATH.write_text(
        add_session_id_to_learning_consumers(source),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
