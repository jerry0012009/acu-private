from pathlib import Path


PROMPT_ROOT = Path("/app/acontext_core/llm/prompt")
LANGUAGE_POLICY = (
    "Use the user's dominant language for distilled learning and all learned "
    "Skill descriptions and content. Preserve code and machine-readable identifiers."
)

PATCHES = {
    "skill_learner.py": f'''

# ACU customization: keep learned Skills in the user's dominant language.
_acu_original_system_prompt = SkillLearnerPrompt.system_prompt


def _acu_language_aware_system_prompt(cls) -> str:
    return _acu_original_system_prompt() + """

## Skill Language
{LANGUAGE_POLICY}
"""


SkillLearnerPrompt.system_prompt = classmethod(_acu_language_aware_system_prompt)
''',
    "skill_distillation.py": f'''

# ACU customization: carry the user's dominant language into Skill learning.
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
"""


def _acu_language_aware_failure_prompt(cls) -> str:
    return _acu_original_failure_distillation_prompt() + """

## Skill Language
{LANGUAGE_POLICY}
"""


SkillDistillationPrompt.success_distillation_prompt = classmethod(
    _acu_language_aware_success_prompt
)
SkillDistillationPrompt.failure_distillation_prompt = classmethod(
    _acu_language_aware_failure_prompt
)
''',
}


for filename, patch in PATCHES.items():
    path = PROMPT_ROOT / filename
    source = path.read_text(encoding="utf-8")
    if "## Skill Language" in source:
        raise RuntimeError(f"Skill language policy already exists in {filename}")
    path.write_text(source.rstrip() + patch, encoding="utf-8")
