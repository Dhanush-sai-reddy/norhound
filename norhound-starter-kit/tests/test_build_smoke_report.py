"""Tests for the 100-company smoke-test report builder.

The smoke test is a submission deliverable, so "complete" must mean the
contract holds rather than "a file was written": every requested organisation
has exactly one envelope, every `available` claim resolves to an evidence
record, and that record carries a source URL and a retrieval time. Explicit
absence states (`not_available`, `blocked`, `failed`) carry no evidence by
design and must not be counted as failures.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.build_smoke_report import build  # noqa: E402


def envelope(org: str, *, evidence_ids=("ev-1",), availability: str = "available") -> dict:
    return {
        "organisation_number": org,
        "claims": [
            {
                "field": "employees",
                "family": "workforce",
                "value": 12,
                "availability": availability,
                "evidence_ids": list(evidence_ids),
            }
        ],
        "evidence": [
            {
                "id": "ev-1",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/999888777",
                "retrieved_at": "2026-11-16T10:00:00Z",
                "content_sha256": "a" * 64,
                "extraction_method": "official_api_field",
            }
        ],
    }


class SmokeReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.run_dir = self.root / "run"
        self.run_dir.mkdir()
        self.out = self.root / "smoke"

    def write_run(self, orgs: list[str], envelopes: list[dict]) -> None:
        with (self.run_dir / "entry.jsonl").open("w", encoding="utf-8") as handle:
            for org in orgs:
                handle.write(json.dumps({"organisation_number": org}) + "\n")
        with (self.run_dir / "envelopes-final.jsonl").open("w", encoding="utf-8") as handle:
            for row in envelopes:
                handle.write(json.dumps(row) + "\n")

    def test_complete_run_passes(self) -> None:
        orgs = ["900000001", "900000002"]
        self.write_run(orgs, [envelope(org) for org in orgs])
        report = build(self.run_dir, 100, self.out)
        self.assertTrue(report["complete"])
        self.assertEqual((report["requested"], report["returned"]), (2, 2))

    def test_missing_organisation_is_reported(self) -> None:
        self.write_run(["900000001", "900000002"], [envelope("900000001")])
        report = build(self.run_dir, 100, self.out)
        self.assertFalse(report["complete"])
        self.assertEqual(report["missing"], ["900000002"])

    def test_available_claim_with_dangling_evidence_is_incomplete(self) -> None:
        self.write_run(["900000001"], [envelope("900000001", evidence_ids=("ev-missing",))])
        report = build(self.run_dir, 100, self.out)
        self.assertFalse(report["complete"])
        self.assertIn("900000001", report["incomplete"])

    def test_absence_states_need_no_evidence(self) -> None:
        self.write_run(
            ["900000001"],
            [envelope("900000001", evidence_ids=(), availability="not_available")],
        )
        report = build(self.run_dir, 100, self.out)
        self.assertTrue(report["complete"])
        self.assertNotIn("900000001", report["incomplete"])

    def test_selection_is_deterministic_and_capped(self) -> None:
        orgs = ["900000003", "900000001", "900000002"]
        self.write_run(orgs, [envelope(org) for org in orgs])
        report = build(self.run_dir, 2, self.out)
        self.assertEqual([row["organisation_number"] for row in report["per_company"]], ["900000001", "900000002"])


if __name__ == "__main__":
    unittest.main()
