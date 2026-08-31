FROM ghcr.io/memodb-io/acontext-core:latest

COPY acu_learning_prompts.py /app/acontext_core/llm/prompt/acu_learning_prompts.py

COPY patch_skill_language.py /app/patch_skill_language.py
RUN /app/.venv/bin/python /app/patch_skill_language.py

COPY patch_llm_retries.py /app/patch_llm_retries.py
RUN /app/.venv/bin/python /app/patch_llm_retries.py

COPY patch_usage_profile.py /app/patch_usage_profile.py
RUN /app/.venv/bin/python /app/patch_usage_profile.py

COPY inspection.py /app/inspection.py
COPY api_with_inspection.py /app/api_with_inspection.py
COPY usage_ledger.py /app/usage_ledger.py
COPY ledger_startup.py /app/ledger_startup.py

CMD ["/app/.venv/bin/uvicorn", "api_with_inspection:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "600"]
