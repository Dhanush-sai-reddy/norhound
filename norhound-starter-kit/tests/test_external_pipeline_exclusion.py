"""Tests for the external pipeline's observation consolidation.

Consolidation is the last point where every connector output becomes a
publishable observation, so it is also the point where a source whose rights
cannot be re-verified (proff.no) must be dropped.
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

from scripts.run_external_pipeline import consolidate_observations  # noqa: E402


class ConsolidateTests(unittest.TestCase):
    def test_rows_from_excluded_hosts_are_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.jsonl"
            rows = [
                {
                    "id": "proff-1",
                    "organisation_number": "996493660",
                    "signal_type": "review_summary",
                    "source_url": "https://www.proff.no/bedrift/996493660",
                    "retrieved_at": "2026-10-04T10:00:00Z",
                },
                {
                    "id": "purehelp-1",
                    "organisation_number": "996493660",
                    "signal_type": "profile_metrics",
                    "source_url": "https://purehelp.no/company/NO/996493660",
                    "retrieved_at": "2026-11-06T09:00:00Z",
                },
            ]
            source.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )
            consolidated, excluded = consolidate_observations([source], ["proff.no"])
            self.assertEqual([row["id"] for row in consolidated], ["purehelp-1"])
            self.assertEqual(excluded, {"proff.no": 1})

    def test_observation_date_is_derived_from_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "id": "purehelp-1",
                        "organisation_number": "996493660",
                        "signal_type": "profile_metrics",
                        "source_url": "https://purehelp.no/company/NO/996493660",
                        "retrieved_at": "2026-11-06T09:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            consolidated, _ = consolidate_observations([source], ["proff.no"])
            self.assertEqual(consolidated[0]["observed_at"], "2026-11-06")

    def test_existing_observation_date_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "id": "registry-1",
                        "organisation_number": "996493660",
                        "signal_type": "registry_update",
                        "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/996493660",
                        "retrieved_at": "2026-11-06T09:00:00Z",
                        "observed_at": "2026-01-31",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            consolidated, _ = consolidate_observations([source], ["proff.no"])
            self.assertEqual(consolidated[0]["observed_at"], "2026-01-31")


if __name__ == "__main__":
    unittest.main()
