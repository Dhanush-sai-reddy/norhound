"""A refresh run must report material changes and preserve earlier evidence.

The official brief requires every terminal envelope to carry "refresh metadata
and material changes since the previous run", and the official-run integrity
check requires "idempotent refresh with prior snapshots preserved":

  https://builderr.ai/starter-briefs/signalpost.md  (retrieved 2026-11-17)

These tests pin the three properties that decide whether a refresh is honest:
a real change is reported, an unchanged company reports nothing, and running
the stage again does not duplicate a change it already recorded.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts import attach_refresh_changes as refresh  # noqa: E402

ORG = "810034882"


def envelope(**overrides) -> dict:
    base = {
        "organisation_number": ORG,
        "run_id": "run-current",
        "run": {"run_id": "run-current", "started_at": "2026-11-18T10:00:00Z"},
        "profile": {
            "organisation_number": ORG,
            "name": "Example AS",
            "legal_form": "AS",
            "employees": 10,
            "municipality": "OSLO",
            "website": "example.no",
            "latest_submitted_accounts": "2025",
            "evidence": {},
        },
        "claims": [
            {
                "field": "official_website",
                "value": "https://example.no/",
                "availability": "available",
                "confidence": 0.99,
                "evidence_ids": ["ev-1"],
            }
        ],
        "evidence": [
            {
                "id": "ev-1",
                "source_url": "https://example.no/",
                "source_class": "company_owned",
                "retrieved_at": "2026-11-18T10:00:00Z",
                "content_sha256": "b" * 64,
                "claim_span": "Example AS",
            }
        ],
        "changes": [],
    }
    base.update(overrides)
    return base


class BaselineTests(unittest.TestCase):
    def test_a_first_run_is_a_baseline_with_no_changes(self) -> None:
        rows, report = refresh.attach([envelope()], [], "none.jsonl")
        self.assertEqual(rows[0]["changes"], [])
        self.assertTrue(rows[0]["refresh"]["baseline"])
        self.assertEqual(report["baselines"], 1)
        self.assertEqual(report["compared"], 0)


class ChangeDetectionTests(unittest.TestCase):
    def test_a_changed_claim_is_reported_with_its_evidence(self) -> None:
        current = envelope()
        current["claims"][0]["value"] = "https://example.no/new/"
        current["evidence"][0]["source_url"] = "https://example.no/new/"
        current["evidence"][0]["content_sha256"] = "c" * 64
        rows, report = refresh.attach([current], [envelope()], "prior.jsonl")
        changes = rows[0]["changes"]
        self.assertEqual(len(changes), 1)
        record = changes[0]
        self.assertEqual(record["field"], "official_website")
        self.assertEqual(record["old_value"], "https://example.no/")
        self.assertEqual(record["new_value"], "https://example.no/new/")
        self.assertEqual(record["source_url"], "https://example.no/new/")
        self.assertEqual(record["new_content_sha256"], "c" * 64)
        self.assertEqual(record["old_content_sha256"], "b" * 64)
        self.assertEqual(record["previous_run_id"], "run-current")
        self.assertEqual(report["changes_detected"], 1)

    def test_an_unchanged_company_reports_nothing(self) -> None:
        rows, report = refresh.attach([envelope()], [envelope()], "prior.jsonl")
        self.assertEqual(rows[0]["changes"], [])
        self.assertFalse(rows[0]["refresh"]["baseline"])
        self.assertEqual(report["changes_detected"], 0)

    def test_a_new_claim_is_a_material_change(self) -> None:
        current = envelope()
        current["claims"].append(
            {
                "field": "dated_news",
                "value": "2026-11-17: Opened a new office",
                "availability": "available",
                "confidence": 0.8,
                "evidence_ids": ["ev-2"],
            }
        )
        current["evidence"].append(
            {
                "id": "ev-2",
                "source_url": "https://example.no/nyheter/",
                "source_class": "company_owned",
                "retrieved_at": "2026-11-18T10:00:00Z",
                "content_sha256": "d" * 64,
                "claim_span": "Opened a new office",
            }
        )
        rows, _ = refresh.attach([current], [envelope()], "prior.jsonl")
        fields = {change["field"] for change in rows[0]["changes"]}
        self.assertIn("dated_news", fields)

    def test_a_registry_field_change_is_reported(self) -> None:
        current = envelope()
        current["profile"]["employees"] = 12
        rows, _ = refresh.attach([current], [envelope()], "prior.jsonl")
        changes = rows[0]["changes"]
        self.assertTrue(any(c["field"] == "registry.employees" for c in changes))

    def test_a_field_that_disappears_is_still_a_change(self) -> None:
        """A field the current run no longer publishes is a change, not a crash."""
        current = envelope()
        current["claims"] = []
        rows, _ = refresh.attach([current], [envelope()], "prior.jsonl")
        changes = rows[0]["changes"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["field"], "official_website")
        self.assertEqual(changes[0]["removed"], "https://example.no/")
        self.assertEqual(changes[0]["added"], [])


class HistoryAndIdempotencyTests(unittest.TestCase):
    def test_an_earlier_change_is_preserved_and_not_duplicated(self) -> None:
        prior = envelope()
        prior["run_id"] = "run-prior"
        prior["changes"] = [
            {
                "organisation_number": ORG,
                "field": "official_website",
                "change_type": "claim_value_set",
                "old_value": "https://old.no/",
                "new_value": "https://example.no/",
                "new_content_sha256": "b" * 64,
                "change_id": "abc123",
            }
        ]
        current = envelope()
        current["claims"][0]["value"] = "https://example.no/new/"
        current["evidence"][0]["source_url"] = "https://example.no/new/"
        current["evidence"][0]["content_sha256"] = "c" * 64
        rows, report = refresh.attach([current], [prior], "prior.jsonl")
        ids = [change["change_id"] for change in rows[0]["changes"]]
        self.assertIn("abc123", ids)
        self.assertEqual(len(ids), len(set(ids)), "a change must not be recorded twice")
        self.assertEqual(report["changes_preserved"], 1)

    def test_running_the_stage_again_changes_nothing(self) -> None:
        current = envelope()
        current["claims"][0]["value"] = "https://example.no/new/"
        current["evidence"][0]["source_url"] = "https://example.no/new/"
        current["evidence"][0]["content_sha256"] = "c" * 64
        once, _ = refresh.attach([current], [envelope()], "prior.jsonl")
        twice, report = refresh.attach(once, [envelope()], "prior.jsonl")
        self.assertEqual(
            [c["change_id"] for c in once[0]["changes"]],
            [c["change_id"] for c in twice[0]["changes"]],
        )
        self.assertEqual(report["changes_detected"], 0)
        self.assertEqual(len(twice[0]["changes"]), len(once[0]["changes"]))

    def test_evidence_behind_a_preserved_change_is_kept(self) -> None:
        prior = envelope()
        prior["run_id"] = "run-prior"
        prior["changes"] = [
            {
                "organisation_number": ORG,
                "field": "official_website",
                "change_type": "claim_value_set",
                "old_value": "https://old.no/",
                "new_value": "https://example.no/",
                "evidence_id": "ev-old",
                "change_id": "old123",
            }
        ]
        prior["evidence"] = [
            {
                "id": "ev-old",
                "source_url": "https://old.no/",
                "source_class": "company_owned",
                "retrieved_at": "2026-11-01T00:00:00Z",
                "content_sha256": "a" * 64,
                "claim_span": "Example AS",
            }
        ]
        current = envelope()
        rows, report = refresh.attach([current], [prior], "prior.jsonl")
        ids = {record["id"] for record in rows[0]["evidence"]}
        self.assertIn("ev-old", ids)
        preserved = [
            record
            for record in rows[0]["evidence"]
            if record.get("preserved_from_run") == "run-prior"
        ]
        self.assertEqual(len(preserved), 1)
        self.assertEqual(report["preserved_evidence_records"], 1)


if __name__ == "__main__":
    unittest.main()
