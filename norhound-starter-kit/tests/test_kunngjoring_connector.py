"""Tests for the BRREG Kunngjoringer (official announcements) connector.

The connector fetches one public page per organisation number and publishes the
dated announcements on it. The failure this guards against is an evidence
defect rather than a parsing bug: `retrieved_at` used to be a frozen literal
(2026-10-05T00:00:00Z), so 2,988 observations claimed a retrieval time six
weeks before the page was actually read. A retrieval time that is not the time
of the read is a fabricated field, so it must come from the read itself.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.run_kunngjoring_connector import fetch_org, parse_announcements  # noqa: E402

ORG = "898166422"

PAGE = """
<table>
<tr>
  <td><p>23.05.2026</p></td><td><p>&nbsp;</p></td>
  <td nowrap="true"><p><a href="hent_en.jsp?kid=20260000386507&amp;sokeverdi=898166422&amp;spraak=nb">Godkjente årsregnskap</a></p></td>
</tr>
</table>
"""


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def parse_one() -> dict:
    rows = parse_announcements(PAGE)
    assert rows, "fixture page must parse"
    return rows[0]


class ParseTests(unittest.TestCase):
    def test_announcement_is_parsed_with_its_publication_date(self) -> None:
        row = parse_one()
        self.assertEqual(row["date"], "2026-05-23")
        self.assertIn("Godkjente", row["title"])
        self.assertTrue(row["url"].startswith("https://w2.brreg.no/kunngjoring/hent_en.jsp?kid="))


class RetrievalTimeTests(unittest.TestCase):
    def test_retrieved_at_is_the_time_of_the_read(self) -> None:
        before = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=5)
        with mock.patch(
            "scripts.run_kunngjoring_connector.urllib.request.urlopen",
            return_value=FakeResponse(PAGE.encode("latin-1")),
        ):
            rows, retrieved_at = fetch_org(ORG)
        after = datetime.now(timezone.utc) + timedelta(seconds=5)

        self.assertTrue(rows)
        stamped = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        self.assertGreaterEqual(stamped, before)
        self.assertLessEqual(stamped, after)

    def test_no_frozen_timestamp_literal_survives(self) -> None:
        source = (ROOT / "scripts" / "run_kunngjoring_connector.py").read_text(encoding="utf-8")
        self.assertNotIn('"retrieved_at": "20', source)
        self.assertNotIn("retrieved_at\": \"20", source)


if __name__ == "__main__":
    unittest.main()
