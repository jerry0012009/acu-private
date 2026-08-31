import os
import unittest
from unittest.mock import patch

from acu_learning_prompts import (
    FILM_SPACE_ENV,
    distillation_prompt_for_space,
    is_film_space,
    skill_learner_prompt_for_space,
    task_prompt_for_space,
)


FILM_SPACE_ID = "b938acba-ba53-48ab-8a6e-a148c6b8099c"


class LearningSpacePromptIsolationTest(unittest.TestCase):
    def test_film_space_uses_only_film_prompts(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            prompts = (
                task_prompt_for_space("BASE TASK", FILM_SPACE_ID),
                distillation_prompt_for_space("BASE DISTILL", FILM_SPACE_ID),
                skill_learner_prompt_for_space("BASE SKILL", FILM_SPACE_ID),
            )

        for prompt in prompts:
            self.assertNotIn("BASE ", prompt)
            self.assertNotIn("learning_trigger: user_dissatisfaction", prompt)
            self.assertNotIn("ACU Preference Documents", prompt)

    def test_other_spaces_keep_existing_private_acu_prompts(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            prompts = (
                task_prompt_for_space("BASE TASK", "ordinary-space"),
                distillation_prompt_for_space("BASE DISTILL", "ordinary-space"),
                skill_learner_prompt_for_space("BASE SKILL", "ordinary-space"),
            )

        self.assertTrue(prompts[0].startswith("BASE TASK"))
        self.assertTrue(prompts[1].startswith("BASE DISTILL"))
        self.assertTrue(prompts[2].startswith("BASE SKILL"))
        for prompt in prompts:
            self.assertNotIn("film-language-lighting", prompt)
            self.assertNotIn("film team's", prompt)

    def test_unconfigured_space_binding_never_selects_film_prompts(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_film_space(FILM_SPACE_ID))
            self.assertTrue(
                task_prompt_for_space("BASE TASK", FILM_SPACE_ID).startswith(
                    "BASE TASK"
                )
            )


if __name__ == "__main__":
    unittest.main()
