"""Tests for merging external observation outputs, including rights-based host exclusion.

Some collected sources cannot be re-verified afterwards: ``proff.no`` now
answers every request with a CloudFront 403, so neither its robots.txt nor its
pages can be re-checked, and the collected rows carry third-party financial
values that are not copied from an official register. Those rows must not be
published, so the merge step can exclude them by host and report what it
dropped.
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

from scripts.merge_external_outputs import merge_observations  # noqa: E402


def row(identifier: str, source_url: str) -> dict:
    return {
        "id": identifier,
        "organisation_number": "916498721",
        "platform": "company_directory",
        "signal_type": "profile_metrics",
        "source_url": source_url,
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
    }


class MergeExclusionTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, rows: list[dict]) -> Path:
        path = directory / name
        path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
            encoding="utf-8",
        )
        return path

    def test_excluded_host_rows_are_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = self._write(
                base,
                "source.jsonl",
                [
                    row("proff-a", "https://www.proff.no/bedrift/916498721"),
                    row("proff-b", "https://proff.no/bedrift/916498721"),
                    row("keep", "https://purehelp.no/company/NO/916498721"),
                ],
            )
            merged, report = merge_observations([source], exclude_hosts={"proff.no"})
            self.assertEqual([item["id"] for item in merged], ["keep"])
            self.assertEqual(report["excluded_hosts"], {"proff.no": 2})

    def test_without_exclusions_every_row_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = self._write(
                base,
                "source.jsonl",
                [
                    row("proff-a", "https://www.proff.no/bedrift/916498721"),
                    row("keep", "https://purehelp.no/company/NO/916498721"),
                ],
            )
            merged, report = merge_observations([source], exclude_hosts=set())
            self.assertEqual(len(merged), 2)
            self.assertEqual(report["excluded_hosts"], {})

    def test_first_input_wins_on_id_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = self._write(base, "first.jsonl", [row("same", "https://a.example/x")])
            second = self._write(base, "second.jsonl", [row("same", "https://b.example/x")])
            merged, report = merge_observations([first, second], exclude_hosts=set())
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]["source_url"], "https://a.example/x")
            self.assertEqual(report["duplicates_dropped"], 1)

    def test_excluded_hosts_are_reported_in_the_merge_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = self._write(
                base,
                "source.jsonl",
                [row("proff-a", "https://www.proff.no/bedrift/916498721")],
            )
            _, report = merge_observations([source], exclude_hosts={"proff.no"})
            self.assertEqual(report["excluded_host_list"], ["proff.no"])
            self.assertEqual(report["rows_excluded"], 1)

    def test_duplicate_claims_keep_the_latest_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            older = row("ar-old", "https://data.brreg.no/regnskap/2025")
            older["signal_type"] = "workforce_snapshot"
            older["effective_at"] = "2025"
            older["retrieved_at"] = "2026-10-08T17:15:01Z"
            older["evidence_span"] = "Selskapet har 4 ansatte"
            older["metrics"] = {"workforce_value": 4}
            newer = dict(older)
            newer["id"] = "ar-new"
            newer["retrieved_at"] = "2026-10-28T06:24:48Z"
            newer["content_sha256"] = "different-bytes-same-claim"
            source = self._write(base, "source.jsonl", [older, newer])
            merged, report = merge_observations([source], exclude_hosts=set(), dedupe_latest=True)
            self.assertEqual([item["id"] for item in merged], ["ar-new"])
            self.assertEqual(report["duplicate_claims_dropped"], 1)

    def test_same_source_with_different_claims_is_never_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = row("a", "https://data.brreg.no/enheter/916498721")
            first["signal_type"] = "registry_update"
            first["evidence_span"] = "Navn endret til A AS"
            first["metrics"] = {"field": "navn", "value": "A AS"}
            first["retrieved_at"] = "2026-10-08T17:15:01Z"
            second = dict(first)
            second["id"] = "b"
            second["evidence_span"] = "Adresse endret til Oslo"
            second["metrics"] = {"field": "adresse", "value": "Oslo"}
            source = self._write(base, "source.jsonl", [first, second])
            merged, report = merge_observations([source], exclude_hosts=set(), dedupe_latest=True)
            self.assertEqual(len(merged), 2)
            self.assertEqual(report["duplicate_claims_dropped"], 0)

    def test_different_claims_are_never_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = row("a", "https://data.brreg.no/regnskap/2025")
            first["signal_type"] = "workforce_snapshot"
            first["effective_at"] = "2025"
            first["retrieved_at"] = "2026-10-08T17:15:01Z"
            second = dict(first)
            second["id"] = "b"
            second["source_url"] = "https://data.brreg.no/regnskap/2024"
            second["effective_at"] = "2024"
            source = self._write(base, "source.jsonl", [first, second])
            merged, report = merge_observations([source], exclude_hosts=set(), dedupe_latest=True)
            self.assertEqual(len(merged), 2)
            self.assertEqual(report["duplicate_claims_dropped"], 0)


if __name__ == "__main__":
    unittest.main()
