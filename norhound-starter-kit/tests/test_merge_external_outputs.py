"""The merge is the step that decides what the corpus contains.

Two properties matter and neither is obvious from the code:

* A row that has a retrieval time but no observation date gets one. A fact
  with no date cannot be shown to have been observed on any day, and 30.6% of
  the rows in the 16 Nov corpus had no `observed_at` because the merge read
  the raw connector files rather than the consolidated file.
* The merge keeps the first row it sees for an id. A label row and its
  observation share an id, so merging a derived label file back into the
  corpus can displace the observation it belongs to. The caller must therefore
  pass only real connector outputs.
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

from scripts import merge_external_outputs as merge  # noqa: E402


def _observation(**overrides) -> dict:
    base = {
        "id": "obs-1",
        "organisation_number": "810034882",
        "platform": "company_site",
        "signal_type": "news_item",
        "source_url": "https://example.no/nyheter/",
        "retrieved_at": "2026-11-16T15:19:00.613969Z",
        "evidence_span": "Example AS",
        "content_sha256": "a" * 64,
    }
    base.update(overrides)
    return base


def _write(directory: Path, name: str, rows: list[dict]) -> Path:
    path = directory / name
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


class ObservedAtStampingTests(unittest.TestCase):
    def test_a_row_without_a_date_gets_the_retrieval_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _write(Path(tmp), "batch.activity.jsonl", [_observation()])
            rows, report = merge.merge_observations(
                [source], stamp_observed_at=True
            )
        self.assertEqual(rows[0]["observed_at"], "2026-11-16")
        self.assertEqual(report["observed_at_stamped"], 1)

    def test_an_existing_date_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _write(
                Path(tmp),
                "batch.activity.jsonl",
                [_observation(observed_at="2024-01-05")],
            )
            rows, report = merge.merge_observations(
                [source], stamp_observed_at=True
            )
        self.assertEqual(rows[0]["observed_at"], "2024-01-05")
        self.assertEqual(report["observed_at_stamped"], 0)

    def test_without_the_flag_nothing_is_stamped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _write(Path(tmp), "batch.activity.jsonl", [_observation()])
            rows, report = merge.merge_observations([source])
        self.assertNotIn("observed_at", rows[0])
        self.assertEqual(report["observed_at_stamped"], 0)


class MergeInputTests(unittest.TestCase):
    def test_the_first_row_for_an_id_wins(self) -> None:
        """This is why a derived label file must never be merged back in."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            observation = _write(directory, "batch.activity.jsonl", [_observation()])
            label = _write(
                directory,
                "batch.labels.jsonl",
                [{"id": "obs-1", "exact_entity": 1, "organisation_number": "810034882"}],
            )
            rows, _ = merge.merge_observations([observation, label])
            rows_reversed, _ = merge.merge_observations([label, observation])
        self.assertEqual(rows[0]["signal_type"], "news_item")
        # The order decides which row survives, and a label row has no
        # source_url, so the observation is lost.
        self.assertNotIn("signal_type", rows_reversed[0])

    def test_excluded_hosts_never_reach_the_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _write(
                Path(tmp),
                "batch.activity.jsonl",
                [_observation(source_url="https://www.proff.no/bedrift/x")],
            )
            rows, report = merge.merge_observations(
                [source], {"proff.no"}, stamp_observed_at=True
            )
        self.assertEqual(rows, [])
        self.assertEqual(report["rows_excluded"], 1)


if __name__ == "__main__":
    unittest.main()
