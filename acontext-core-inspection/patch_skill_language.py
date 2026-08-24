from pathlib import Path


PROMPT_ROOT = Path("/app/acontext_core/llm/prompt")
LANGUAGE_POLICY = (
    "Use the user's dominant language for distilled learning and all learned "
    "preference descriptions and content. Preserve code and machine-readable identifiers."
)

ACU_TASK_POLICY = """

## ACU Preference Learning
When the input contains `learning_trigger: user_dissatisfaction`, this is an
explicit signal that the user has rejected, corrected, or redirected the
previous direction from a user-experience perspective.

- Do not wait for the task to become technically complete before recording the
  learning signal.
- Treat a pending or running task with this signal as an experience that needs
  learning. Link the relevant messages, record the user's contextual
  correction, and let the ACU adapter dispatch it for preference distillation.
- This is not permission to invent a long-term preference from one ambiguous
  sentence. Prefer evidence about the user's goal, current stage, trade-off,
  rejected alternative, and reason.
- Do not turn the signal into a generic technical SOP.
"""

ACU_DISTILLATION_POLICY = """

## ACU Trajectory Preference Distillation
When the input contains `learning_trigger: user_dissatisfaction`, distill the
user-experience difference rather than a technical implementation recipe.

Identify, when supported by the evidence:
- the user's goal, stage, and concrete situation;
- what direction the agent took and what direction the user wanted instead;
- what user characteristic or preference is revealed in that situation;
- why the user preferred one option over the alternative;
- a generalized trajectory rule describing when this preference should be
  recalled in future work.

The useful abstraction is:
`situation -> user preference/characteristic -> reason/trade-off -> reusable reminder`.
Do not over-generalize from a single fact or turn the result into a task log.
Keep the exact `experience_id` from the ACU learning signal in the distilled
result, preferably in `applies_when`, so the Skill Agent can preserve evidence.
If the evidence does not support a reusable preference, skip learning.
"""

ACU_SKILL_POLICY = """

## ACU Preference Documents
For ACU dissatisfaction contexts, learned Skills are concise user-preference
documents, not a technical SOP library.

Each preference document must stay within 1500 characters and contain:

```markdown
---
name: "preference-title"
description: "Short description of the preference."
type: user_preference
experience_id: exp-...
related_experience_ids:
  - exp-...
---

# Preference title

## Description
Short description of the preference.

## Why
The situation, user characteristic or preference, and reason for the choice.

## Advisor guidance
The short reminder to use when a similar trajectory appears.
```

Before creating or updating a document, inspect related existing Skills. Treat
the whole learning space as one evolving user-preference picture:

- Prefer updating a related preference over creating a duplicate.
- Generalize from the situation and reason, not from a one-off implementation.
- When preferences conflict, first test whether they are conditional on
  different goals, stages, risk levels, or contexts; merge those conditions
  into one coherent preference when possible.
- If the user genuinely changed preference, revise the old document rather than
  appending contradictory entries. Preserve only a small number of relevant
  related experience IDs.
- Remove obsolete or duplicated entries from the document while keeping it
  under the character limit.
- Do not infer a personality trait without evidence and do not create a
  separate profile database.
"""

PATCHES = {
    "task.py": f'''

# ACU customization: allow explicit dissatisfaction to enter preference learning.
_acu_original_task_system_prompt = TaskPrompt.system_prompt


def _acu_preference_task_system_prompt(cls) -> str:
    return _acu_original_task_system_prompt() + """{ACU_TASK_POLICY}
"""


TaskPrompt.system_prompt = classmethod(_acu_preference_task_system_prompt)
''',
    "skill_distillation.py": f'''

# ACU customization: distill trajectory preferences instead of technical SOPs.
_acu_original_success_distillation_prompt = (
    SkillDistillationPrompt.success_distillation_prompt
)
_acu_original_failure_distillation_prompt = (
    SkillDistillationPrompt.failure_distillation_prompt
)


def _acu_language_aware_success_prompt(cls) -> str:
    return _acu_original_success_distillation_prompt() + """
## Skill Language
{LANGUAGE_POLICY}
{ACU_DISTILLATION_POLICY}
"""


def _acu_language_aware_failure_prompt(cls) -> str:
    return _acu_original_failure_distillation_prompt() + """
## Skill Language
{LANGUAGE_POLICY}
{ACU_DISTILLATION_POLICY}
"""


SkillDistillationPrompt.success_distillation_prompt = classmethod(
    _acu_language_aware_success_prompt
)
SkillDistillationPrompt.failure_distillation_prompt = classmethod(
    _acu_language_aware_failure_prompt
)
''',
    "skill_learner.py": f'''

# ACU customization: store concise, contextual user preferences.
_acu_original_system_prompt = SkillLearnerPrompt.system_prompt


def _acu_preference_skill_system_prompt(cls) -> str:
    return _acu_original_system_prompt() + """
## Skill Language
{LANGUAGE_POLICY}
{ACU_SKILL_POLICY}
"""


SkillLearnerPrompt.system_prompt = classmethod(_acu_preference_skill_system_prompt)
''',
}


for filename, patch in PATCHES.items():
    path = PROMPT_ROOT / filename
    source = path.read_text(encoding="utf-8")
    if "## Skill Language" in source:
        raise RuntimeError(f"ACU prompt patch already exists in {filename}")
    path.write_text(source.rstrip() + patch, encoding="utf-8")


# Acontext only publishes task distillation for success/failed tasks. When ACU
# has already classified the user input as dissatisfaction, make non-terminal
# tasks eligible for the existing failure-distillation pipeline. This keeps the
# change inside the wrapper and does not add a new queue or persistence model.
AGENT_TASK_PATH = Path("/app/acontext_core/llm/agent/task.py")
agent_source = AGENT_TASK_PATH.read_text(encoding="utf-8")
marker = "        if _pending_learning_task_ids and learning_space_id is not None:\n"
if "ACU customization: dispatch dissatisfaction for pending tasks" in agent_source:
    raise RuntimeError("ACU pending-task learning patch already exists")
if marker not in agent_source:
    raise RuntimeError("Acontext task agent publish marker is unavailable")
loop_marker = "    while already_iterations < max_iterations:\n"
if loop_marker not in agent_source:
    raise RuntimeError("Acontext task agent loop marker is unavailable")
agent_source = agent_source.replace(
    loop_marker,
    "    _acu_dissatisfaction_dispatched = False\n" + loop_marker,
    1,
)

pending_learning_patch = """        # ACU customization: dispatch dissatisfaction for pending tasks.
        _acu_dissatisfaction_signal = any(
            "learning_trigger: user_dissatisfaction"
            in message.to_string({}, truncate_chars=2048)
            for message in messages
        )
        if (
            _acu_dissatisfaction_signal
            and learning_space_id is not None
            and not _acu_dissatisfaction_dispatched
        ):
            async with DB_CLIENT.get_session_context() as _acu_db_session:
                _acu_result = await TD.fetch_current_tasks(
                    _acu_db_session, session_id
                )
                _acu_tasks, _acu_eil = _acu_result.unpack()
                _acu_planning_result = await TD.fetch_planning_task(
                    _acu_db_session, session_id
                )
                _acu_planning_task, _acu_planning_eil = _acu_planning_result.unpack()
                if not _acu_eil and not _acu_planning_eil:
                    _acu_candidates = list(_acu_tasks)
                    if _acu_planning_task is not None:
                        _acu_candidates.append(_acu_planning_task)
                    _acu_learning_candidates = [
                        _acu_task
                        for _acu_task in _acu_candidates
                        if _acu_task.raw_message_ids
                        and getattr(_acu_task.status, "value", _acu_task.status)
                        not in ("success", "failed")
                    ]
                    if not _acu_learning_candidates:
                        # Distillation's existing loader only includes ordinary
                        # tasks, so use one ordinary failed task as the smallest
                        # bridge for a fresh dissatisfaction-only session.
                        _acu_insert_result = await TD.insert_task(
                            _acu_db_session,
                            project_id,
                            session_id,
                            len(_acu_tasks),
                            {
                                "task_description": (
                                    "user experience feedback requiring "
                                    "preference learning"
                                )
                            },
                            status="failed",
                        )
                        _acu_fallback_task, _acu_insert_eil = (
                            _acu_insert_result.unpack()
                        )
                        if not _acu_insert_eil and _acu_fallback_task is not None:
                            _acu_message_ids = [
                                message.message_id for message in messages
                            ]
                            await TD.append_messages_to_task(
                                _acu_db_session,
                                _acu_message_ids,
                                _acu_fallback_task.id,
                            )
                            _acu_candidates = [_acu_fallback_task]
                            _acu_learning_candidates = [_acu_fallback_task]
                    for _acu_task in _acu_candidates:
                        _acu_status = getattr(_acu_task.status, "value", _acu_task.status)
                        if (
                            _acu_status not in ("success", "failed")
                            and _acu_task.raw_message_ids
                        ):
                            await TD.update_task(
                                _acu_db_session, _acu_task.id, status="failed"
                            )
                            if _acu_task.id not in _pending_learning_task_ids:
                                _pending_learning_task_ids.append(_acu_task.id)
                    if _acu_learning_candidates:
                        for _acu_task in _acu_learning_candidates:
                            if _acu_task.id not in _pending_learning_task_ids:
                                _pending_learning_task_ids.append(_acu_task.id)
                    _acu_dissatisfaction_dispatched = bool(_acu_learning_candidates)

        if _acu_dissatisfaction_signal:
            # Do not also send this context through Acontext's generic
            # submit_user_preference shortcut; the failure distillation path
            # is the ACU preference-learning path for this signal.
            _pending_preferences.clear()

"""
AGENT_TASK_PATH.write_text(
    agent_source.replace(marker, pending_learning_patch + marker, 1),
    encoding="utf-8",
)
