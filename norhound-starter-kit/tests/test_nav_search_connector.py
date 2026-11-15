"""Tests for the NAV arbeidsplassen live-search job connector.

The connector searches the public stillinger API per legal name and publishes
an ad only when the ad's detail record carries the exact organisation number
of the profile. Two failure modes matter more than the happy path:

* arbeidsplassen.nav.no answers unauthenticated bulk search with HTTP 429.
  A refused request proves nothing about whether the company is hiring, so it
  must never be written to the cache as "no ads" — a later run would then
  never retry that company.
* a same-name employer with a different organisation number is a different
  legal entity and must not be published.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.run_nav_search_connector import (  # noqa: E402
    SearchUnavailable,
    fetch_company,
    names_match,
)

ORG = "972105902"
NAME = "TORSBYGG AS"


def profile() -> dict:
    return {"organisation_number": ORG, "name": NAME}


def search_hit(uuid: str = "abc-123", employer: str = NAME) -> dict:
    return {"uuid": uuid, "employer": {"name": employer}, "title": "Økonomimedarbeider"}


def ad_detail(uuid: str = "abc-123", orgnr: str = ORG) -> dict:
    return {
        "uuid": uuid,
        "title": "Økonomimedarbeider",
        "published": "2026-11-01T09:00:00+01:00",
        "expires": "2026-11-30T23:59:00+01:00",
        "employer": {"name": NAME, "orgnr": orgnr},
        "locationList": [{"city": "Ågotnes"}],
        "properties": {"applicationurl": "https://example.invalid/apply"},
    }


class SearchUnavailableTests(unittest.TestCase):
    def test_a_refused_search_is_never_cached_as_zero_ads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)

            def refuse(url, timeout=25):
                raise SearchUnavailable("HTTP 429 for search")

            with mock.patch("scripts.run_nav_search_connector.get_json", refuse):
                rows, status = fetch_company(ORG, profile(), cache)

            self.assertEqual(rows, [])
            self.assertEqual(status["status"], "search_unavailable")
            self.assertFalse(
                (cache / f"{ORG}.json").exists(),
                "a rate-limited request must not be cached as 'no ads'",
            )

    def test_a_refused_ad_detail_is_never_cached_as_zero_ads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)

            def refuse_detail(url, timeout=25):
                if "api/search" in url:
                    return {"content": [search_hit()]}
                raise SearchUnavailable("HTTP 429 for detail")

            with mock.patch("scripts.run_nav_search_connector.get_json", refuse_detail):
                rows, status = fetch_company(ORG, profile(), cache)

            self.assertEqual(rows, [])
            self.assertEqual(status["status"], "search_unavailable")
            self.assertFalse((cache / f"{ORG}.json").exists())

    def test_a_cached_search_is_reused_without_touching_the_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / f"{ORG}.json").write_text("[]", encoding="utf-8")

            def explode(url, timeout=25):
                raise AssertionError("cached company must not hit the network")

            with mock.patch("scripts.run_nav_search_connector.get_json", explode):
                rows, status = fetch_company(ORG, profile(), cache)

            self.assertEqual(rows, [])
            self.assertEqual(status["status"], "no_confirmed_ads")


class IdentityGateTests(unittest.TestCase):
    def test_a_same_name_employer_with_a_different_org_number_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)

            def responses(url, timeout=25):
                if "api/search" in url:
                    return {"content": [search_hit()]}
                return ad_detail(orgnr="999999999")

            with mock.patch("scripts.run_nav_search_connector.get_json", responses):
                rows, status = fetch_company(ORG, profile(), cache)

            self.assertEqual(rows, [])
            self.assertEqual(status["ads"], 0)

    def test_a_confirmed_ad_is_published_as_a_job_board_posting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)

            def responses(url, timeout=25):
                if "api/search" in url:
                    return {"content": [search_hit()]}
                return ad_detail()

            with mock.patch("scripts.run_nav_search_connector.get_json", responses):
                rows, status = fetch_company(ORG, profile(), cache)

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["organisation_number"], ORG)
            self.assertEqual(row["signal_type"], "job_posting")
            self.assertEqual(row["platform"], "job_board")
            self.assertTrue(row["exact_entity"])
            self.assertIn(ORG, json.dumps(row["identity_proof"]))
            self.assertEqual(row["source_url"], "https://arbeidsplassen.nav.no/stillinger/stilling/abc-123")
            self.assertEqual(row["observed_at"], "2026-11-01")
            self.assertEqual(status["ads"], 1)

    def test_the_legal_form_token_does_not_block_a_match(self) -> None:
        self.assertTrue(names_match("Torsbygg AS", "Torsbygg"))
        self.assertTrue(names_match("Torsbygg AS", "Torsbygg AS, Ågotnes"))
        self.assertFalse(names_match("Torsbygg AS", "Torsbygg Eiendom AS"))


if __name__ == "__main__":
    unittest.main()
