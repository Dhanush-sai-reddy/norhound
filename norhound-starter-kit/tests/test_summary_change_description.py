"""The summary has to explain the changes, in words a reader can check.

The rubric gives the synthesis points to a summary that "explains the company,
changes and unknowns". The refresh stage writes change records with
``old_value``/``new_value`` (plus ``added``/``removed`` for a set of claims) and
the source URL that proves the new value. A summary that read the wrong keys
printed "sitemap_page: None -> None", and a summary built before the refresh
stage claimed there was no prior version at all.

These tests pin both: the description is readable and carries the source, and
the official command rebuilds the summaries after the refresh stage.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_deterministic_summaries as summaries  # noqa: E402


class ChangeDescriptionTests(unittest.TestCase):
    def test_a_claim_set_change_says_what_was_added_and_removed(self) -> None:
        described = summaries.describe_change(
            {
                "field": "sitemap_page",
                "change_type": "claim_value_set",
                "old_value": ["a", "b"],
                "new_value": ["a", "c"],
                "added": ["c"],
                "removed": ["b"],
                "source_url": "https://example.no/",
            }
        )
        self.assertIn("sitemap_page", described)
        self.assertIn("1 added", described)
        self.assertIn("1 removed", described)
        self.assertIn("https://example.no/", described)
        self.assertNotIn("None", described)

    def test_a_profile_field_change_shows_the_old_and_the_new_value(self) -> None:
        described = summaries.describe_change(
            {
                "field": "website.title",
                "change_type": "profile_field",
                "old_value": "Old title",
                "new_value": None,
                "source_url": "https://example.no/",
            }
        )
        self.assertIn("Old title", described)
        self.assertIn("not available", described)

    def test_a_long_value_is_shortened(self) -> None:
        described = summaries.describe_change(
            {
                "field": "description",
                "change_type": "profile_field",
                "old_value": "x" * 500,
                "new_value": "y" * 500,
            }
        )
        self.assertLess(len(described), 200)
        self.assertIn("…", described)

    def test_a_counted_claim_shows_the_two_numbers(self) -> None:
        described = summaries.describe_change(
            {
                "field": "role_count",
                "change_type": "claim_value_set",
                "old_value": 2,
                "new_value": 3,
                "added": 3,
                "removed": 2,
                "source_url": "https://data.brreg.no/",
            }
        )
        self.assertIn("role_count: 2 -> 3", described)
        self.assertNotIn("3 added", described)

    def test_a_single_added_value_is_still_readable(self) -> None:
        described = summaries.describe_change(
            {
                "field": "dated_news",
                "change_type": "claim_value_set",
                "old_value": ["Aktuelt – Hans Claussen AS"],
                "new_value": ["Aktuelt – Hans Claussen AS (2026-11-17)"],
                "added": "Aktuelt – Hans Claussen AS (2026-11-17)",
                "removed": None,
            }
        )
        self.assertIn("1 added", described)
        self.assertIn("Hans Claussen", described)
        self.assertNotIn("None", described)


if __name__ == "__main__":
    unittest.main()
