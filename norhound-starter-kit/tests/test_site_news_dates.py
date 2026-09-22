from __future__ import annotations

import unittest

from scripts.extract_company_site_news import find_dates, observation


def _profile(pages):
    return {
        "organisation_number": "810034882",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://example.test/",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "value": {
                    "identity_assessment": {"publishable": True},
                    "pages": pages,
                },
            }
        },
    }


def _page(url, title="Nyheter", excerpt=""):
    return {"url": url, "title": title, "main_text_excerpt": excerpt, "content_sha256": "b" * 64}


class SiteNewsDatesTests(unittest.TestCase):
    def test_iso_date_found(self):
        self.assertIn("2026-08-14", find_dates("Publisert 2026-08-14 av Ola"))

    def test_norwegian_month_date_found(self):
        self.assertIn("2026-09-14", find_dates("14. september 2026: åpning"))

    def test_numeric_date_found(self):
        self.assertIn("2026-09-14", find_dates("14.09.2026"))

    def test_no_date_is_empty(self):
        self.assertEqual(find_dates("Velkommen til våre sider"), [])

    def test_observation_carries_latest_date(self):
        profile = _profile([_page("https://example.test/nyheter", "Nyheter", "Sak fra 2026-08-14 og nyere 14. september 2026")])
        obs = observation(profile)
        self.assertEqual(obs["observed_at"], "2026-09-14")

    def test_observation_without_date_has_no_observed_at(self):
        profile = _profile([_page("https://example.test/nyheter", "Nyheter", "Velkommen")])
        obs = observation(profile)
        self.assertIsNotNone(obs)
        self.assertNotIn("observed_at", obs)


if __name__ == "__main__":
    unittest.main()
