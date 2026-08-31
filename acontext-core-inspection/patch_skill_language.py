from pathlib import Path


PROMPT_ROOT = Path("/app/acontext_core/llm/prompt")
TASK_AGENT_PATH = Path("/app/acontext_core/llm/agent/task.py")
SKILL_AGENT_PATH = Path("/app/acontext_core/llm/agent/skill_learner.py")
DISTILL_CONTROLLER_PATH = Path(
    "/app/acontext_core/service/controller/skill_learner.py"
)
DISTILL_TOOL_PATH = Path(
    "/app/acontext_core/llm/tool/skill_learner_lib/distill.py"
)


def append_once(path: Path, sentinel: str, patch: str) -> None:
    source = path.read_text(encoding="utf-8")
    if sentinel in source:
        raise RuntimeError(f"ACU patch already exists in {path}")
    path.write_text(source.rstrip() + patch, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if old not in source:
        raise RuntimeError(f"Acontext source marker is unavailable in {path}: {old[:80]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


append_once(
    PROMPT_ROOT / "task.py",
    "ACU customization: select prompts by Learning Space",
    '''

# ACU customization: select prompts by Learning Space.
from .acu_learning_prompts import task_prompt_for_space as _acu_task_prompt_for_space

_acu_original_task_system_prompt = TaskPrompt.system_prompt


def _acu_space_bound_task_system_prompt(cls, learning_space_id=None) -> str:
    return _acu_task_prompt_for_space(
        _acu_original_task_system_prompt(), learning_space_id
    )


TaskPrompt.system_prompt = classmethod(_acu_space_bound_task_system_prompt)
''',
)

append_once(
    PROMPT_ROOT / "skill_distillation.py",
    "ACU customization: select distillation prompts by Learning Space",
    '''

# ACU customization: select distillation prompts by Learning Space.
from .acu_learning_prompts import (
    distillation_prompt_for_space as _acu_distillation_prompt_for_space,
)

_acu_original_success_distillation_prompt = (
    SkillDistillationPrompt.success_distillation_prompt
)
_acu_original_failure_distillation_prompt = (
    SkillDistillationPrompt.failure_distillation_prompt
)


def _acu_space_bound_success_prompt(cls, learning_space_id=None) -> str:
    return _acu_distillation_prompt_for_space(
        _acu_original_success_distillation_prompt(), learning_space_id
    )


def _acu_space_bound_failure_prompt(cls, learning_space_id=None) -> str:
    return _acu_distillation_prompt_for_space(
        _acu_original_failure_distillation_prompt(), learning_space_id
    )


SkillDistillationPrompt.success_distillation_prompt = classmethod(
    _acu_space_bound_success_prompt
)
SkillDistillationPrompt.failure_distillation_prompt = classmethod(
    _acu_space_bound_failure_prompt
)
''',
)

append_once(
    PROMPT_ROOT / "skill_learner.py",
    "ACU customization: select Skill Learner prompts by Learning Space",
    '''

# ACU customization: select Skill Learner prompts by Learning Space.
from .acu_learning_prompts import (
    skill_learner_prompt_for_space as _acu_skill_learner_prompt_for_space,
)

_acu_original_skill_learner_system_prompt = SkillLearnerPrompt.system_prompt


def _acu_space_bound_skill_learner_system_prompt(
    cls, learning_space_id=None
) -> str:
    return _acu_skill_learner_prompt_for_space(
        _acu_original_skill_learner_system_prompt(), learning_space_id
    )


SkillLearnerPrompt.system_prompt = classmethod(
    _acu_space_bound_skill_learner_system_prompt
)
''',
)


# Every Acontext stage already carries learning_space_id. Pass it directly to
# the prompt selector instead of inferring learning behavior from message text.
replace_once(
    TASK_AGENT_PATH,
    "            system_prompt=TaskPrompt.system_prompt(),\n",
    "            system_prompt=TaskPrompt.system_prompt(learning_space_id),\n",
)
replace_once(
    DISTILL_CONTROLLER_PATH,
    "        distill_system_prompt = SkillDistillationPrompt.success_distillation_prompt()\n",
    "        distill_system_prompt = (\n"
    "            SkillDistillationPrompt.success_distillation_prompt(learning_space_id)\n"
    "        )\n",
)
replace_once(
    DISTILL_CONTROLLER_PATH,
    "        distill_system_prompt = SkillDistillationPrompt.failure_distillation_prompt()\n",
    "        distill_system_prompt = (\n"
    "            SkillDistillationPrompt.failure_distillation_prompt(learning_space_id)\n"
    "        )\n",
)
replace_once(
    SKILL_AGENT_PATH,
    "                system_prompt=SkillLearnerPrompt.system_prompt(),\n",
    "                system_prompt=SkillLearnerPrompt.system_prompt(learning_space_id),\n",
)

# Film distillation has a structured claim tool. Ordinary Space calls retain
# the upstream success, factual, failure, and skip tools.
append_once(
    DISTILL_TOOL_PATH,
    "ACU customization: structured film LearningClaim output",
    '''

# ACU customization: structured film LearningClaim output.
from ...prompt.acu_learning_prompts import (
    FILM_DISTILL_TOOL_FUNCTION as _ACU_FILM_DISTILL_TOOL_FUNCTION,
)

DISTILL_FILM_TOOL = ToolSchema(function=_ACU_FILM_DISTILL_TOOL_FUNCTION)
_acu_original_extract_distillation_result = extract_distillation_result


def extract_distillation_result(llm_return: LLMResponse) -> Result[DistillationOutcome]:
    if (
        not llm_return.tool_calls
        or llm_return.tool_calls[0].function is None
        or llm_return.tool_calls[0].function.name != "report_film_learning_claims"
    ):
        return _acu_original_extract_distillation_result(llm_return)

    args = llm_return.tool_calls[0].function.arguments
    experience_id = args.get("experience_id")
    evidence_summary = args.get("evidence_summary")
    claims = args.get("claims")
    if not isinstance(experience_id, str) or not experience_id.strip():
        return Result.reject("Missing required field: experience_id")
    if not isinstance(evidence_summary, str) or not evidence_summary.strip():
        return Result.reject("Missing required field: evidence_summary")
    if not isinstance(claims, list) or not claims:
        return Result.reject("Missing required field: claims")

    required_fields = (
        "topic",
        "applies_when",
        "prefer",
        "avoid",
        "why",
        "example_ref",
    )
    lines = [
        "private_acu_learning_kind: film_preference_v1",
        "## Film Learning Claims",
        f"**Experience ID:** {experience_id}",
        f"**Evidence Summary:** {evidence_summary}",
    ]
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            return Result.reject(f"Claim {index} must be an object")
        for field in required_fields:
            if not isinstance(claim.get(field), str):
                return Result.reject(f"Claim {index} missing required field: {field}")
        lines.extend(
            [
                f"### Claim {index}",
                f"**Topic:** {claim['topic']}",
                f"**Applies When:** {claim['applies_when']}",
                f"**Prefer:** {claim['prefer']}",
                f"**Avoid:** {claim['avoid']}",
                f"**Why:** {claim['why']}",
                f"**Example Ref:** {claim['example_ref']}",
            ]
        )

    return Result.resolve(
        DistillationOutcome(
            is_worth_learning=True,
            distilled_text="\\n".join(lines),
        )
    )
''',
)
replace_once(
    DISTILL_CONTROLLER_PATH,
    "    DISTILL_FAILURE_TOOL,\n"
    "    extract_distillation_result,\n",
    "    DISTILL_FAILURE_TOOL,\n"
    "    DISTILL_FILM_TOOL,\n"
    "    extract_distillation_result,\n",
)
replace_once(
    DISTILL_CONTROLLER_PATH,
    "from ...llm.prompt.skill_distillation import SkillDistillationPrompt\n",
    "from ...llm.prompt.skill_distillation import SkillDistillationPrompt\n"
    "from ...llm.prompt.acu_learning_prompts import is_film_space\n",
)
replace_once(
    DISTILL_CONTROLLER_PATH,
    "    if finished_task.status == TaskStatus.SUCCESS:\n"
    "        tools = [\n"
    "            DISTILL_SKIP_TOOL.model_dump(),\n"
    "            DISTILL_SUCCESS_TOOL.model_dump(),\n"
    "            DISTILL_FACTUAL_TOOL.model_dump(),\n"
    "        ]\n"
    "        distill_system_prompt = (\n"
    "            SkillDistillationPrompt.success_distillation_prompt(learning_space_id)\n"
    "        )\n"
    "    else:\n"
    "        tools = [DISTILL_FAILURE_TOOL.model_dump()]\n"
    "        distill_system_prompt = (\n"
    "            SkillDistillationPrompt.failure_distillation_prompt(learning_space_id)\n"
    "        )\n",
    "    if is_film_space(learning_space_id):\n"
    "        tools = [DISTILL_FILM_TOOL.model_dump()]\n"
    "        distill_system_prompt = (\n"
    "            SkillDistillationPrompt.failure_distillation_prompt(learning_space_id)\n"
    "        )\n"
    "    elif finished_task.status == TaskStatus.SUCCESS:\n"
    "        tools = [\n"
    "            DISTILL_SKIP_TOOL.model_dump(),\n"
    "            DISTILL_SUCCESS_TOOL.model_dump(),\n"
    "            DISTILL_FACTUAL_TOOL.model_dump(),\n"
    "        ]\n"
    "        distill_system_prompt = (\n"
    "            SkillDistillationPrompt.success_distillation_prompt(learning_space_id)\n"
    "        )\n"
    "    else:\n"
    "        tools = [DISTILL_FAILURE_TOOL.model_dump()]\n"
    "        distill_system_prompt = (\n"
    "            SkillDistillationPrompt.failure_distillation_prompt(learning_space_id)\n"
    "        )\n",
)


# Explicit Private ACU learning messages are already complete learning units.
# Publish one synthetic failed task and skip the generic Task Agent loop.
agent_source = TASK_AGENT_PATH.read_text(encoding="utf-8")
loop_marker = "    while already_iterations < max_iterations:\n"
if "ACU customization: dispatch one explicit learning task" in agent_source:
    raise RuntimeError("ACU pending-task learning patch already exists")
if loop_marker not in agent_source:
    raise RuntimeError("Acontext task agent loop marker is unavailable")

explicit_learning_patch = """    # ACU customization: dispatch one explicit learning task.
    _acu_learning_signal = any(
        marker in message.to_string({}, truncate_chars=2048)
        for message in messages
        for marker in (
            "learning_trigger: user_dissatisfaction",
            "private_acu_learning_kind: film_preference_v1",
        )
    )
    if _acu_learning_signal and learning_space_id is not None:
        async with DB_CLIENT.get_session_context() as _acu_db_session:
            _acu_result = await TD.fetch_current_tasks(
                _acu_db_session, session_id
            )
            _acu_tasks, _acu_eil = _acu_result.unpack()
            if _acu_eil:
                return Result.reject(str(_acu_eil))
            _acu_insert_result = await TD.insert_task(
                _acu_db_session,
                project_id,
                session_id,
                len(_acu_tasks),
                {
                    "task_description": (
                        "Private ACU explicit preference learning"
                    )
                },
                status="failed",
            )
            _acu_task, _acu_insert_eil = _acu_insert_result.unpack()
            if _acu_insert_eil or _acu_task is None:
                return Result.reject(str(_acu_insert_eil))
            await TD.append_messages_to_task(
                _acu_db_session,
                [message.message_id for message in messages],
                _acu_task.id,
            )
        try:
            await publish_mq(
                EX.learning_skill,
                RK.learning_skill_distill,
                SkillLearnTask(
                    project_id=project_id,
                    session_id=session_id,
                    task_id=_acu_task.id,
                ).model_dump_json(),
            )
        except Exception:
            LOG.error(
                "task_agent.publish_learning_failed",
                task_id=str(_acu_task.id),
            )
            return Result.reject("Failed to publish explicit Private ACU learning")
        wide["agent_iterations"] = 0
        wide["llm_calls"] = 0
        wide["tools_called"] = []
        wide["task_count"] = 1
        return Result.resolve(None)

"""
TASK_AGENT_PATH.write_text(
    agent_source.replace(loop_marker, explicit_learning_patch + loop_marker, 1),
    encoding="utf-8",
)
