from pathlib import Path


CLIENTS_PATH = Path("/app/acontext_core/llm/complete/clients.py")


def disable_sdk_retries(source: str) -> str:
    replacements = {
        "            api_key=DEFAULT_CORE_CONFIG.llm_api_key,\n"
        "            default_query=DEFAULT_CORE_CONFIG.llm_openai_default_query,\n":
        "            api_key=DEFAULT_CORE_CONFIG.llm_api_key,\n"
        "            max_retries=0,\n"
        "            default_query=DEFAULT_CORE_CONFIG.llm_openai_default_query,\n",
        "            api_key=DEFAULT_CORE_CONFIG.llm_api_key,\n"
        "            base_url=DEFAULT_CORE_CONFIG.llm_base_url,\n":
        "            api_key=DEFAULT_CORE_CONFIG.llm_api_key,\n"
        "            base_url=DEFAULT_CORE_CONFIG.llm_base_url,\n"
        "            max_retries=0,\n",
    }
    patched = source
    for original, replacement in replacements.items():
        if original not in patched:
            raise RuntimeError("Acontext LLM client constructor is unavailable")
        patched = patched.replace(original, replacement, 1)
    return patched


def main() -> None:
    source = CLIENTS_PATH.read_text(encoding="utf-8")
    if "max_retries=0" in source:
        raise RuntimeError("Acontext SDK retry patch already exists")
    CLIENTS_PATH.write_text(disable_sdk_retries(source), encoding="utf-8")


if __name__ == "__main__":
    main()
