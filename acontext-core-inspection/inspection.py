from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

PROMPT_ROOT = Path("/app/acontext_core/llm/prompt")
PROMPT_FILES = (
    "task.py",
    "skill_learner.py",
    "skill_distillation.py",
)


@router.get("/internal/inspection/prompts")
async def inspect_prompts() -> dict:
    files = []
    for name in PROMPT_FILES:
        path = PROMPT_ROOT / name
        if not path.is_file():
            raise HTTPException(status_code=503, detail=f"Prompt file is unavailable: {name}")
        files.append(
            {
                "path": f"llm/prompt/{name}",
                "mime": "text/x-python",
                "content": path.read_text(encoding="utf-8"),
            }
        )
    return {"files": files}
