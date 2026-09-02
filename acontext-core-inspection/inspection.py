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
            "title": "账户任务整理提示词",
            "description": "Acontext 常规会话用于整理任务；Private ACU 主动 Learning 直接提交 Experience，因此当前链路不执行此步骤。",
            "content": TaskPrompt.system_prompt(learning_space_id),
            "language": "zh-CN",
            "source": "llm/prompt/acu_learning_prompts.py: ACCOUNT_TASK_PROMPT",
            "execution": "bypassed_for_explicit_learning",
            "examples": account_prompt_examples("task"),
        },
        {
            "id": "account-distillation",
            "stage": "distillation",
            "title": "账户不满意反馈蒸馏提示词",
            "description": "当前 user_dissatisfaction 路径从完整账户 Experience 中提取可迁移的条件化偏好。",
            "content": SkillDistillationPrompt.failure_distillation_prompt(
                learning_space_id
            ),
            "language": "zh-CN",
            "source": "llm/prompt/acu_learning_prompts.py: ACCOUNT_FAILURE_DISTILLATION_PROMPT",
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
            "source": "llm/prompt/acu_learning_prompts.py: ACCOUNT_SKILL_LEARNER_PROMPT",
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
