"""The registry-site promotion must not corrupt the profile JSONL it writes.

`str.splitlines()` treats U+2028 (LINE SEPARATOR) and U+2029 (PARAGRAPH
SEPARATOR) as line breaks. A profile whose legal name contains one of them
therefore splits into two fragments and every downstream reader raises
`JSONDecodeError`. The promotion re-serialises the profile with
`ensure_ascii=False`, which turns the source file's escaped `\u2028` back into
a raw separator, so the promoted file must escape it again on the way out.
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

from scripts.promote_registry_declared_sites import promote, write_profiles  # noqa: E402


def _profile(name: str = "SKOG\u2028BRYGG AS") -> dict:
    return {
        "organisation_number": "123456789",
        "name": name,
        "website": "skogbrygg.no",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://skogbrygg.no/",
                "content_sha256": "a" * 64,
                "value": {
                    "final_url": "https://skogbrygg.no/",
                    "registered_domain": "skogbrygg.no",
                    "title": "Skogbrygg",
                    "main_text_excerpt": "Skogbrygg lager øl.",
                    "identity_assessment": {"publishable": False, "score": 0.3, "matched_tokens": ["skogbrygg"]},
                },
            },
            "registry": {"value": {"hjemmeside": "skogbrygg.no"}, "source_url": "https://data.brreg.no/x", "retrieved_at": "2026-11-06T00:00:00Z"},
        },
    }


class WriteProfilesTests(unittest.TestCase):
    def test_written_profiles_have_no_raw_line_separators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "profiles.jsonl"
            write_profiles(output, [_profile()])
            raw = output.read_text(encoding="utf-8")
            self.assertNotIn("\u2028", raw)
            self.assertNotIn("\u2029", raw)

    def test_written_profiles_round_trip_through_splitlines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "profiles.jsonl"
            write_profiles(output, [_profile()])
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "SKOG\u2028BRYGG AS")


class PromotePreservesNameTests(unittest.TestCase):
    def test_promotion_keeps_the_separator_in_the_legal_name(self) -> None:
        profile = _profile()
        promote(profile, {"skogbrygg.no": "123456789"}, "2026-11-07")
        self.assertEqual(profile["name"], "SKOG\u2028BRYGG AS")


if __name__ == "__main__":
    unittest.main()
