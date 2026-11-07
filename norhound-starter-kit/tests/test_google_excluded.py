"""No Google observation may be published: the run must be keyless and ToS-clean.

The shipped corpus carried 2,497 published observations whose `source_url` is
`www.google.com`:

* 1,897 rows from the **Google Places API**, which requires an API key. A
  submission that must run end to end without a key cannot reproduce or
  re-verify them, and a claim backed by a credential nobody can supply is not
  evidence a reviewer can check.
* 600 rows scraped from **Google Maps** map pages. Google's Terms of Service
  prohibit automated access to that content, and the challenge's source policy
  admits only robots- and ToS-permitted sources.

Both are Google Maps data reached by a route the rules forbid, so the whole
host is excluded by default, the same way `proff.no` is. The cost is real and
is measured in `docs/evidence/keyless-google-exclusion-2026-11-07.md`: the
reviews, ratings and sentiment families fall back to the keyless ceiling, and
the official recall rubric does not score those families at all.
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

from norway_company_agent.source_rights import DEFAULT_EXCLUDED_HOSTS, excluded_host_for  # noqa: E402
from scripts.run_external_pipeline import consolidate_observations  # noqa: E402


class GoogleIsExcludedTests(unittest.TestCase):
    def test_google_is_in_the_default_excluded_hosts(self) -> None:
        self.assertIn("google.com", DEFAULT_EXCLUDED_HOSTS)

    def test_google_maps_urls_are_excluded_by_default(self) -> None:
        for url in (
            "https://www.google.com/maps/place/Firma/@59.9,10.7",
            "https://www.google.com/maps?cid=123",
            "https://maps.google.com/?q=996493660",
        ):
            self.assertTrue(excluded_host_for(url), url)

    def test_other_google_owned_hosts_are_not_silently_excluded(self) -> None:
        """Only the Maps/Places host is excluded; unrelated Google hosts are not."""
        self.assertFalse(excluded_host_for("https://www.googleusercontent.com/x"))
        self.assertFalse(excluded_host_for("https://notgoogle.com/x"))

    def test_google_rows_are_dropped_by_the_default_consolidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jsonl"
            source.write_text(
                "".join(
                    json.dumps(row)
                    + "\n"
                    for row in [
                        {
                            "id": "gplaces-1",
                            "organisation_number": "996493660",
                            "signal_type": "review_summary",
                            "source_url": "https://www.google.com/maps/place/Firma",
                            "retrieved_at": "2026-10-04T10:00:00Z",
                        },
                        {
                            "id": "keep-1",
                            "organisation_number": "996493660",
                            "signal_type": "profile_metrics",
                            "source_url": "https://www.fagfolkguiden.no/bedrift/996493660",
                            "retrieved_at": "2026-10-04T10:00:00Z",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            consolidated, excluded = consolidate_observations([source], DEFAULT_EXCLUDED_HOSTS)
            self.assertEqual([row["id"] for row in consolidated], ["keep-1"])
            self.assertEqual(excluded, {"google.com": 1})


if __name__ == "__main__":
    unittest.main()
