from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

PROMPT_ROOT = Path("/app/acontext_core/llm/prompt")
PROMPT_FILES = (
    "task.py",
    "skill_learner.py",
    "skill_distillation.py",
    "acu_learning_prompts.py",
)


def resolved_prompt_cards(learning_space_id: str | None) -> list[dict[str, object]]:
    from acontext_core.llm.prompt.acu_learning_prompts import (
        account_prompt_examples,
        film_prompt_cards,
        is_film_space,
    )

    if is_film_space(learning_space_id):
        return film_prompt_cards()

    from acontext_core.llm.prompt.skill_distillation import SkillDistillationPrompt
    from acontext_core.llm.prompt.skill_learner import SkillLearnerPrompt
    from acontext_core.llm.prompt.task import TaskPrompt

    return [
        {
            "id": "account-task",
            "stage": "task",
            "title": "通用 Acontext 任务整理提示词",
            "description": "处理普通 Learning Space 的任务整理和消息关联。",
            "content": TaskPrompt.system_prompt(learning_space_id),
            "language": "mixed",
            "source": "llm/prompt/task.py: TaskPrompt.system_prompt",
            "execution": "bypassed_for_explicit_learning",
            "examples": account_prompt_examples("task"),
        },
        {
            "id": "account-distillation",
            "stage": "distillation",
            "title": "账户偏好蒸馏提示词",
            "description": "从账户级学习 Experience 中提取可复用的条件化偏好。",
            "content": SkillDistillationPrompt.failure_distillation_prompt(
                learning_space_id
            ),
            "language": "zh-CN",
            "source": (
                "llm/prompt/skill_distillation.py: "
                "SkillDistillationPrompt.failure_distillation_prompt"
            ),
            "execution": "used",
            "examples": account_prompt_examples("distillation"),
        },
        {
            "id": "account-skill-learner",
            "stage": "skill_learner",
            "title": "账户偏好 Skill 学习提示词",
            "description": "根据账户级蒸馏结果更新或创建偏好 Skill。",
            "content": SkillLearnerPrompt.system_prompt(learning_space_id),
            "language": "zh-CN",
            "source": "llm/prompt/skill_learner.py: SkillLearnerPrompt.system_prompt",
            "execution": "used",
            "examples": account_prompt_examples("skill_learner"),
        },
    ]


@router.get("/internal/inspection/prompts")
async def inspect_prompts(learning_space_id: str | None = None) -> dict:
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
    try:
        prompts = resolved_prompt_cards(learning_space_id)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Resolved prompt inspection is unavailable: {error}",
        ) from error
    return {"files": files, "prompts": prompts}
