FROM ghcr.io/memodb-io/acontext-core:latest

COPY inspection.py /app/inspection.py
COPY api_with_inspection.py /app/api_with_inspection.py

CMD ["/app/.venv/bin/uvicorn", "api_with_inspection:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "600"]
