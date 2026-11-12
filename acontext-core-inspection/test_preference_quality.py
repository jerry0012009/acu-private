import unittest
import json
from types import SimpleNamespace
from preference_quality import evidence_context, format_elements


class PreferenceQualityTest(unittest.TestCase):
    def message(self, text):
        return SimpleNamespace(to_string=lambda mapping, truncate_chars: text if truncate_chars is None else text[:truncate_chars])

    def test_evidence_after_512_survives(self):
        text = "header" * 400 + "USER_CHOSE_B" + "tail" * 2000
        self.assertEqual(evidence_context([self.message(text)]), text)

    def test_native_roles_preserved_and_serialized_pixels_not_reinterpreted(self):
        text = "signal\n## Native request JSON\n" + json.dumps({"messages": [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,SECRETPIXELS"}},
                                          {"type": "text", "text": "Prefer this composition"}]},
            {"role": "assistant", "content": "Generated opinion, not user preference"},
        ]})
        result = evidence_context([self.message(text)])
        self.assertNotIn("SECRETPIXELS", result)
        self.assertIn('"role": "assistant"', result)
        self.assertIn("Prefer this composition", result)

    def test_over_budget_is_explicit_and_preserves_recent_evidence(self):
        text = "SOURCE" + "x" * 4000 + "LATEST_CHOICE"
        result = evidence_context([self.message(text)], limit=1000)
        self.assertTrue(result.startswith("SOURCE"))
        self.assertTrue(result.endswith("LATEST_CHOICE"))
        self.assertIn("INCOMPLETE CONTEXT", result)

    def test_multiple_independent_elements_and_source_required(self):
        element = dict(title="Report order", applies_when="Work reports", prefer="Conclusions first",
                       avoid="", exceptions="", why="", evidence="user quote; exp-1", origin="explicit")
        result = format_elements({"elements": [element, {**element, "title": "Visual taste"}]})
        self.assertEqual(result.count("### Preference Element"), 2)
        with self.assertRaises(ValueError):
            format_elements({"elements": [{**element, "evidence": ""}]})
        with self.assertRaises(ValueError):
            format_elements({"elements": [element] * 9})


if __name__ == "__main__":
    unittest.main()
