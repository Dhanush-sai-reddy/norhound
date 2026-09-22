from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.refresh import attach_refresh


def _envelope(org="810034882", employees=11):
    return {
        "run_id": "new-001",
        "organisation_number": org,
        "state": "complete",
        "profile": {
            "organisation_number": org,
            "name": "SANDNES ELEKTRISKE AS",
            "employees": employees,
            "evidence": {
                "registry": {"status": "available", "source_url": "https://example.test/reg", "retrieved_at": "2026-09-14T00:00:00Z", "content_sha256": "a" * 64},
            },
        },
    }


class RefreshAttachTests(unittest.TestCase):
    def test_identical_envelopes_have_no_changes(self):
        out = attach_refresh([_envelope()], [_envelope()], "new-001")
        self.assertEqual(out[0]["changes"], [])
        self.assertFalse(out[0]["refresh"]["baseline"])

    def test_changed_field_carries_old_and_new_values(self):
        out = attach_refresh([_envelope(employees=12)], [_envelope(employees=11)], "new-001")
        changes = out[0]["changes"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["field"], "registry.employees")
        self.assertEqual(changes[0]["old_value"], 11)
        self.assertEqual(changes[0]["new_value"], 12)
        self.assertIn("old_content_sha256", changes[0])
        self.assertIn("new_content_sha256", changes[0])

    def test_new_company_is_baseline_not_change(self):
        out = attach_refresh([_envelope()], [], "new-001")
        self.assertEqual(out[0]["changes"], [])
        self.assertTrue(out[0]["refresh"]["baseline"])

    def test_previous_run_id_recorded(self):
        prev = [_envelope()]
        prev[0]["run_id"] = "old-009"
        out = attach_refresh([_envelope()], prev, "new-001")
        self.assertEqual(out[0]["refresh"]["previous_run_id"], "old-009")

    def test_input_envelopes_not_mutated(self):
        current = [_envelope()]
        attach_refresh(current, [_envelope()], "new-001")
        self.assertNotIn("changes", current[0])
        self.assertNotIn("refresh", current[0])


if __name__ == "__main__":
    unittest.main()
