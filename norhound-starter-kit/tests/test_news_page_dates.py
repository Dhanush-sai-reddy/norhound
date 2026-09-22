from __future__ import annotations

import unittest

from scripts.extract_company_site_news import date_from_page_body, fetch_dated_observation


def _profile():
    return {
        "organisation_number": "810034882",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://www.example.test/",
                "retrieved_at": "2026-09-22T00:00:00Z",
                "content_sha256": "f" * 64,
                "value": {
                    "identity_assessment": {"publishable": True, "score": 1.0, "method": "exact_domain+official"},
                    "final_url": "https://www.example.test/",
                    "pages": [{
                        "url": "https://www.example.test/nyheter/2026/nytt-ar",
                        "title": "Nytt år hos oss",
                        "main_text_excerpt": "Vi er i gang med nye prosjekter og gleder oss.",
                        "content_sha256": "g" * 64,
                    }],
                },
            }
        },
    }


class NewsPageDatesTests(unittest.TestCase):
    def test_date_from_iso_in_body(self):
        body = "<html><h1>Nytt år</h1><time datetime=\"2026-09-01\">1. september 2026</time><p>Tekst</p></html>"
        self.assertEqual(date_from_page_body(body), "2026-09-01")

    def test_date_from_norwegian_month_in_body(self):
        body = "…avsluttet 14. mars 2026 …"
        self.assertEqual(date_from_page_body(body), "2026-03-14")

    def test_no_date_returns_none(self):
        self.assertIsNone(date_from_page_body("<html>ingen dato her</html>"))

    def test_fetch_attaches_observed_at(self):
        obs = fetch_dated_observation(_profile(), body="<p>publisert 2026-08-01</p>")
        self.assertIsNotNone(obs)
        self.assertEqual(obs["observed_at"], "2026-08-01")
        self.assertEqual(obs["signal_type"], "public_post")

    def test_fetch_without_date_returns_base_untouched(self):
        obs = fetch_dated_observation(_profile(), body="<p>ingen dato</p>")
        self.assertIsNotNone(obs)
        self.assertNotIn("observed_at", obs)

    def test_ungated_site_returns_none(self):
        profile = _profile()
        profile["evidence"]["website"]["value"]["identity_assessment"] = {"publishable": False, "score": 0.2}
        self.assertIsNone(fetch_dated_observation(profile, body="<p>2026-08-01</p>"))


if __name__ == "__main__":
    unittest.main()