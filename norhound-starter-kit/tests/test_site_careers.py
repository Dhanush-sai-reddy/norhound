from __future__ import annotations

import unittest

from scripts.extract_company_site_careers import observation


def _profile(pages, publishable=True):
    return {
        "organisation_number": "810034882",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://example.test/",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "value": {
                    "identity_assessment": {"publishable": publishable},
                    "pages": pages,
                },
            }
        },
    }


def _page(url, title="Jobs"):
    return {"url": url, "title": title, "content_sha256": "b" * 64}


class SiteCareersTests(unittest.TestCase):
    def test_careers_page_emits_hiring_signal(self):
        obs = observation(_profile([_page("https://example.test/karriere", "Ledige stillinger")]))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["signal_type"], "careers_page")
        self.assertTrue(obs["exact_entity"])
        self.assertEqual(obs["source_url"], "https://example.test/karriere")

    def test_no_careers_path_emits_nothing(self):
        self.assertIsNone(observation(_profile([_page("https://example.test/om-oss", "Om oss")])))

    def test_ungated_site_emits_nothing(self):
        obs = observation(_profile([_page("https://example.test/karriere")], publishable=False))
        self.assertIsNone(obs)

    def test_careers_observation_is_deterministic(self):
        profile = _profile([_page("https://example.test/careers")])
        self.assertEqual(observation(profile), observation(_profile([_page("https://example.test/careers")])))


if __name__ == "__main__":
    unittest.main()
