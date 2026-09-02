import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from acu_learning_prompts import (
    FILM_SPACE_ENV,
    FILM_MAX_NEW_SKILLS,
    FILM_MAX_SKILL_WRITES,
    account_prompt_examples,
    distillation_prompt_for_space,
    film_prompt_cards,
    is_film_space,
    skill_learner_prompt_for_space,
    task_prompt_for_space,
)
from patch_film_multimodal_distillation import build_film_distillation_content


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

    def test_other_spaces_use_independent_chinese_account_prompts(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            prompts = (
                task_prompt_for_space("BASE TASK", "ordinary-space"),
                distillation_prompt_for_space("BASE DISTILL", "ordinary-space"),
                skill_learner_prompt_for_space("BASE SKILL", "ordinary-space"),
            )

        self.assertNotIn("BASE DISTILL", prompts[1])
        self.assertNotIn("BASE SKILL", prompts[2])
        self.assertIn("任务整理 Agent", prompts[0])
        self.assertIn("可迁移", prompts[1])
        self.assertIn("可迁移", prompts[2])
        self.assertIn("中文", prompts[1])
        self.assertIn("中文", prompts[2])
        self.assertNotIn("影视团队", prompts[1])
        self.assertNotIn("影视团队", prompts[2])

    def test_film_prompt_cards_show_only_executed_learning_stages(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            cards = film_prompt_cards()

        self.assertEqual(
            [card["stage"] for card in cards],
            ["distillation", "skill_learner"],
        )
        self.assertTrue(all(card["language"] == "zh-CN" for card in cards))
        self.assertTrue(all(card["content"] for card in cards))
        self.assertTrue(all(card["examples"] for card in cards))
        self.assertEqual(cards[0]["examples"][0]["origin"], "reference_fixture")
        self.assertEqual(
            cards[0]["examples"][0]["material"]["images"][0]["mimeType"],
            "image/jpeg",
        )
        self.assertEqual(cards[0]["examples"][0]["artifact"]["format"], "json")
        self.assertIn("表达目标", cards[0]["content"])
        self.assertIn("可迁移的导演语言原则", cards[0]["content"])
        self.assertNotIn("film-task", {card["id"] for card in cards})

    def test_film_skill_learner_uses_runtime_catalog_and_limits_writes(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            prompt = skill_learner_prompt_for_space("BASE SKILL", FILM_SPACE_ID)

        self.assertIn("当前 Learning Space 实时提供的 Skill catalog", prompt)
        self.assertIn("每次最多更新 3 个", prompt)
        self.assertIn("最多创建 1 个 Skill", prompt)
        self.assertEqual(FILM_MAX_SKILL_WRITES, 3)
        self.assertEqual(FILM_MAX_NEW_SKILLS, 1)
        self.assertIn("不使用预设目录", prompt)
        self.assertNotIn("film-language-lighting", prompt)
        self.assertNotIn("film-language-color", prompt)

    def test_account_prompt_cards_have_text_and_artifact_examples(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            cards = [
                {
                    "examples": account_prompt_examples(stage),
                }
                for stage in ("task", "distillation", "skill_learner")
            ]

        self.assertTrue(all(card["examples"] for card in cards))
        self.assertEqual(cards[0]["examples"][0]["origin"], "reference_fixture")
        self.assertIn("text", cards[0]["examples"][0]["material"])
        self.assertEqual(cards[2]["examples"][0]["artifact"]["format"], "markdown")

    def test_account_prompts_require_portable_preference_abstraction(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            distillation = distillation_prompt_for_space(
                "BASE DISTILL", "ordinary-space"
            )
            learner = skill_learner_prompt_for_space("BASE SKILL", "ordinary-space")

        self.assertIn("任务事实", distillation)
        self.assertIn("用户偏好", distillation)
        self.assertIn("删除一次性名词", distillation)
        self.assertIn("另一项同类工作", distillation)
        self.assertIn("用户选择标准", learner)
        self.assertIn("标题和 description", learner)
        self.assertIn("没有稳定规则时不写入", learner)

    def test_effective_account_task_prompt_is_chinese_and_portable(self) -> None:
        with patch.dict(os.environ, {FILM_SPACE_ENV: FILM_SPACE_ID}, clear=False):
            prompt = task_prompt_for_space("IGNORED BASE", "ordinary-space")
        self.assertIn("Private ACU", prompt)
        self.assertIn("用户明确提出的独立请求", prompt)
        self.assertIn("不要在任务整理阶段自行生成偏好", prompt)
        self.assertNotIn("IGNORED BASE", prompt)

    def test_unconfigured_space_binding_never_selects_film_prompts(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_film_space(FILM_SPACE_ID))
            self.assertTrue(
                task_prompt_for_space("BASE TASK", FILM_SPACE_ID).startswith(
                    "BASE TASK"
                )
            )

    def test_film_distillation_binds_images_to_one_multimodal_message(self) -> None:
        content = build_film_distillation_content(
            "文本证据",
            [
                SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            type="text",
                            meta=None,
                        ),
                        SimpleNamespace(
                            type="image",
                            meta={
                                "url": "data:image/jpeg;base64,ZmFrZQ==",
                                "detail": "high",
                            },
                        ),
                    ]
                )
            ],
        )

        self.assertIsInstance(content, list)
        self.assertEqual(
            [item["type"] for item in content],
            ["text", "text", "image_url"],
        )
        self.assertEqual(
            content[-1]["image_url"],
            {
                "url": "data:image/jpeg;base64,ZmFrZQ==",
                "detail": "high",
            },
        )

    def test_film_distillation_without_images_keeps_text_input(self) -> None:
        self.assertEqual(
            build_film_distillation_content("文本证据", []),
            "文本证据",
        )


if __name__ == "__main__":
    unittest.main()
