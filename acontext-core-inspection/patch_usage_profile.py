from pathlib import Path


OPENAI_COMPLETE_PATH = Path("/app/acontext_core/llm/complete/openai_sdk.py")


def add_acu_profile_to_completion_log(source: str) -> str:
    marker = "    LOG.info(\n        \"llm.complete\",\n"
    if marker not in source:
        raise RuntimeError("Acontext OpenAI completion log is unavailable")
    profile_read = (
        "    _model_extra = getattr(response, \"model_extra\", None) or {}\n"
        "    _acu_profile = getattr(response, \"acu_profile\", None) or "
        "_model_extra.get(\"acu_profile\") or {}\n\n"
    )
    patched = source.replace(marker, profile_read + marker, 1)
    fields_marker = "        duration_s=round(_end_s - _start_s, 4),\n"
    if fields_marker not in patched:
        raise RuntimeError("Acontext OpenAI completion fields are unavailable")
    return patched.replace(
        fields_marker,
        fields_marker
        + "        execution_profile_id=_acu_profile.get(\"execution_profile_id\"),\n"
        + "        provider=_acu_profile.get(\"provider\"),\n"
        + "        channel_id=_acu_profile.get(\"channel_id\"),\n",
        1,
    )


def main() -> None:
    source = OPENAI_COMPLETE_PATH.read_text(encoding="utf-8")
    if "execution_profile_id=_acu_profile.get" in source:
        raise RuntimeError("Acontext usage Profile patch already exists")
    OPENAI_COMPLETE_PATH.write_text(
        add_acu_profile_to_completion_log(source),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
