import unittest
from preference_document import preference_fields, patch_preference

DOCUMENT = """---
name: reports
description: Concise reports
related_experience_ids: [original]
---
# Reports
## Applies When
Weekly reports
## Prefer
Conclusions first, except for legal reports.
## Exceptions
Legal reports retain full rationale.
## Evidence
Original user quotation.
## Advisor guidance
Preserve legal context.
"""


class PreferenceDocumentTests(unittest.TestCase):
    def test_edit_keeps_untouched_conditions_evidence_and_front_matter(self):
        result, changed = patch_preference(DOCUMENT, {"summary": "Clear reports", "scope": "Weekly reports"})
        self.assertEqual(changed, ["summary"])
        self.assertIn("except for legal reports", result)
        self.assertIn("Original user quotation.", result)
        self.assertIn("original", result)
        self.assertEqual(preference_fields(result)["exceptions"], "Legal reports retain full rationale.")

    def test_rule_edit_does_not_erase_exception(self):
        result, changed = patch_preference(DOCUMENT, {"rule": "Decisions first"})
        self.assertEqual(changed, ["rule"])
        self.assertEqual(preference_fields(result)["scope"], "Weekly reports")
        self.assertIn("Legal reports retain full rationale.", result)

    def test_missing_empty_and_unchanged_fields_are_distinct(self):
        self.assertEqual(patch_preference(DOCUMENT, {})[0], DOCUMENT)
        self.assertEqual(patch_preference(DOCUMENT, {"scope": "Weekly reports"})[1], [])
        self.assertEqual(preference_fields(patch_preference(DOCUMENT, {"exceptions": ""})[0])["exceptions"], "")

    def test_code_headings_are_not_sections(self):
        text = DOCUMENT + "\n```\n## Prefer\nnot a rule\n```\n"
        result, _ = patch_preference(text, {"rule": "New rule"})
        self.assertIn("## Prefer\nnot a rule", result)

    def test_ambiguous_duplicate_is_not_silently_removed(self):
        with self.assertRaises(ValueError):
            patch_preference(DOCUMENT + "\n## Prefer\nAnother rule\n", {"rule": "New rule"})

    def test_control_marker_is_not_shown_as_an_exception(self):
        text = DOCUMENT + "\n## Exceptions\nA specific exception\n<!-- preference-control: 2026-11-12 -->\n"
        self.assertNotIn("preference-control", preference_fields(text)["exceptions"])
