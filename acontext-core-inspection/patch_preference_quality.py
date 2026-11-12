"""Apply a guarded overlay to the reviewed, already-patched Core baseline."""
from pathlib import Path

ROOT = Path("/app/acontext_core")


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"Preference overlay baseline mismatch: {path}")
    path.write_text(text.replace(old, new, 1))


controller = ROOT / "service/controller/skill_learner.py"
replace(controller,
        "from ...llm.prompt.acu_learning_prompts import is_film_space",
        "from ...llm.prompt.acu_learning_prompts import is_film_space, ACCOUNT_ELEMENTS_PROMPT\n"
        "from ...llm.prompt.preference_quality import ELEMENT_TOOL\n"
        "from ...schema.llm import ToolSchema")
replace(controller,
        "    elif finished_task.status == TaskStatus.SUCCESS:",
        "    elif learning_space_id:\n"
        "        tools = [DISTILL_SKIP_TOOL.model_dump(), ToolSchema(function=ELEMENT_TOOL).model_dump()]\n"
        "        distill_system_prompt = ACCOUNT_ELEMENTS_PROMPT\n"
        "    elif finished_task.status == TaskStatus.SUCCESS:")
replace(controller, "        tools = [DISTILL_FAILURE_TOOL.model_dump()]",
        "        tools = [DISTILL_SKIP_TOOL.model_dump(), DISTILL_FAILURE_TOOL.model_dump()]")
replace(controller, "        include_images=is_film_space(learning_space_id),",
        "        include_images=True,")

distill = ROOT / "llm/tool/skill_learner_lib/distill.py"
with distill.open("a") as output:
    output.write('''

# ACU preference elements retain the existing queue payload and result type.
from ...prompt.preference_quality import format_elements
_acu_elements_previous_extract = extract_distillation_result
def extract_distillation_result(llm_return):
    calls = llm_return.tool_calls
    if calls and calls[0].function and calls[0].function.name == "report_preference_elements":
        try:
            return Result.resolve(DistillationOutcome(
                is_worth_learning=True,
                distilled_text=format_elements(calls[0].function.arguments),
            ))
        except ValueError as error:
            return Result.reject(str(error))
    return _acu_elements_previous_extract(llm_return)
''')

prompt = ROOT / "llm/prompt/skill_distillation.py"
replace(prompt,
        '        for m in task_messages:\n'
        '            messages_section += f"{m.to_string(tool_mappings, truncate_chars=512)}\\n"',
        '        from .preference_quality import evidence_context\n'
        '        messages_section += evidence_context(task_messages)')

# Account budgets are real tool budgets, not just suggestions to the model.
agent = ROOT / "llm/agent/skill_learner.py"
replace(agent, "FILM_MAX_SKILL_WRITES if is_film_space(learning_space_id) else None",
        "FILM_MAX_SKILL_WRITES if is_film_space(learning_space_id) else 6")
replace(agent, "FILM_MAX_NEW_SKILLS if is_film_space(learning_space_id) else None",
        "FILM_MAX_NEW_SKILLS if is_film_space(learning_space_id) else 4")
replace(agent, "            already_iterations += 1\n",
        "            already_iterations += 1\n"
        "            if already_iterations >= max_iterations:\n"
        "                raise RuntimeError('Preference writer iteration budget exhausted; completion not established')\n")

ctx = ROOT / "llm/tool/skill_learner_lib/ctx.py"
replace(ctx, "    if ctx.max_skill_writes is None or skill_name in ctx.skill_write_names:\n",
        "    existing = ctx.skills.get(skill_name)\n"
        "    if existing and existing.description.startswith('[ACU_PREFERENCE_DISABLED]'):\n"
        "        return 'This preference was disabled by its owner; do not modify or recreate it.'\n"
        "    if ctx.max_skill_writes is None or skill_name in ctx.skill_write_names:\n")

# Both explicit signals use the same evidence-preserving distiller. The ordinary
# Task Agent otherwise shortens each message to 1024 characters before extraction.
task = ROOT / "llm/agent/task.py"
replace(task, '            "learning_trigger: user_dissatisfaction",',
        '            "learning_trigger: user_dissatisfaction",\n'
        '            "learning_trigger: explicit_user_preference",')
replace(task, '                status="failed",',
        '                status=("success" if any("learning_trigger: explicit_user_preference"\n'
        '                    in m.to_string({}, truncate_chars=2048) for m in messages) else "failed"),')
