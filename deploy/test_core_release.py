import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

import core_release
from core_release import production_projection, validate_config
from learning_canary import validate_ledger


CONFIG = {
    "llm_simple_model": "gpt-6.1-sol",
    "llm_openai_completion_kwargs": {"reasoning_effort": "medium"},
}


class CoreModelReleaseTest(unittest.TestCase):
    def test_checked_in_config_has_only_model_and_medium(self):
        self.assertEqual(yaml.safe_load(
            Path(__file__).with_name("core-config.yaml").read_text()
        ), CONFIG)

    def test_projection_changes_only_core_default_model(self):
        base = {"services": {
            "core": {"environment": {"LLM_SIMPLE_MODEL": "gpt-5.6-sol", "LLM_API_KEY": "${TOKEN}"}},
            "api": {"environment": {"CORE_BASE_URL": "http://core:8000"}},
        }}
        original = copy.deepcopy(base)
        projected = production_projection(base, CONFIG)
        self.assertEqual(base, original)
        self.assertEqual(projected["services"]["api"], original["services"]["api"])
        self.assertEqual(projected["services"]["core"]["environment"]["LLM_API_KEY"], "${TOKEN}")
        self.assertEqual(projected["services"]["core"]["environment"]["LLM_SIMPLE_MODEL"], "gpt-6.1-sol")

    def test_incompatible_parameters_fail_before_rollout(self):
        for field, value in (
            ("temperature", 0.3), ("extra_body", {"thinking": {"type": "disabled"}}),
            ("reasoning_effort", "none"),
        ):
            config = copy.deepcopy(CONFIG)
            config["llm_openai_completion_kwargs"][field] = value
            with self.assertRaises(ValueError):
                validate_config(config)

    def test_different_model_is_not_silently_accepted(self):
        config = copy.deepcopy(CONFIG)
        config["llm_simple_model"] = "gpt-6-sol"
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_canary_requires_all_three_actual_worker_stages(self):
        rows = [{"prompt_id": prompt, "model": "gpt-6.1-sol", "execution_profile_id": "profile"}
                for prompt in ("agent.task", "distill.skill_learner", "agent.skill_learner")]
        validate_ledger(rows)
        for invalid in ([], rows[:-1], [{**row, "model": "gpt-5.6-sol"} for row in rows],
                        [{**row, "execution_profile_id": None} for row in rows]):
            with self.assertRaises(RuntimeError):
                validate_ledger(invalid)

    def test_failed_core_replacement_restores_exact_old_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "production-compose.yaml"
            runtime = root / "production-config.yaml"
            old_base = b"old production compose\n"
            old_config = b"old production config\n"
            candidate_config = yaml.safe_dump(CONFIG).encode()
            base.write_bytes(old_base)
            runtime.write_bytes(old_config)
            for filename, content in {
                "compose.before.yaml": old_base, "config.before.yaml": old_config,
                "compose.candidate.yaml": b"new compose\n", "core-config.yaml": candidate_config,
                "core-image.yaml": b"frozen image\n",
            }.items():
                (root / filename).write_bytes(content)
            (root / "manifest.json").write_text(json.dumps({
                "coreId": "old-id", "baseHash": core_release.digest(old_base),
                "oldConfigHash": core_release.digest(old_config),
                "configHash": core_release.digest(candidate_config),
            }))
            (root / "canary-success.json").write_text(json.dumps({
                "model": "gpt-6.1-sol", "reasoningEffort": "medium",
            }))
            calls = []

            def execute(args, **_):
                calls.append(args)
                if len(calls) == 1:
                    raise RuntimeError("simulated replacement failure")
                return ""

            with patch.object(core_release, "BASE_COMPOSE", base), \
                    patch.object(core_release, "RUNTIME_CONFIG", runtime), \
                    patch.object(core_release, "verify_protected"), \
                    patch.object(core_release, "inspect", return_value={"Id": "old-id"}), \
                    patch.object(core_release, "wait_idle"), \
                    patch.object(core_release, "command", side_effect=execute):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    core_release.apply(root)
            self.assertEqual(base.read_bytes(), old_base)
            self.assertEqual(runtime.read_bytes(), old_config)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(args[-1] == "core" and "--no-deps" in args for args in calls))
            self.assertEqual(json.loads((root / "status.json").read_text())["status"], "rolled_back")

    def test_unreadable_queue_inventory_prevents_replacement(self):
        with patch.object(core_release, "command", return_value="unavailable"):
            with self.assertRaisesRegex(RuntimeError, "inventory"):
                core_release.wait_idle()


if __name__ == "__main__":
    unittest.main()
