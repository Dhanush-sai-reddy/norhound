from __future__ import annotations

import unittest

from scripts.extract_sitemap_pages import parse_sitemap, select_pages


def _sitemap_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.test/om-oss</loc><lastmod>2025-01-15T10:00:00+00:00</lastmod></url>
  <url><loc>https://example.test/nyheter</loc><lastmod>2026-09-01</lastmod></url>
  <url><loc>https://example.test/kontakt</loc></url>
</urlset>"""


def _profile():
    return {
        "organisation_number": "810034882",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://www.example.test/",
                "retrieved_at": "2026-09-22T00:00:00Z",
                "content_sha256": "e" * 64,
                "value": {
                    "identity_assessment": {"publishable": True, "score": 1.0, "method": "exact_domain+official"},
                    "final_url": "https://www.example.test/",
                },
            }
        },
    }


class SitemapPagesTests(unittest.TestCase):
    def test_parse_extracts_locs_and_lastmods(self):
        pages = parse_sitemap(_sitemap_xml())
        self.assertEqual(pages["https://example.test/om-oss"]["lastmod"], "2025-01-15")
        self.assertEqual(pages["https://example.test/nyheter"]["lastmod"], "2026-09-01")

    def test_page_without_lastmod_kept_but_unverifiable(self):
        pages = parse_sitemap(_sitemap_xml())
        self.assertIsNone(pages["https://example.test/kontakt"]["lastmod"])

    def test_select_keeps_newest_dated_only(self):
        pages = parse_sitemap(_sitemap_xml())
        selected = select_pages(pages, limit=1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][1]["lastmod"], "2026-09-01")

    def test_no_dated_pages_selects_nothing(self):
        pages = parse_sitemap(_sitemap_xml())
        del pages["https://example.test/om-oss"]["lastmod"]
        del pages["https://example.test/nyheter"]["lastmod"]
        self.assertEqual(select_pages(pages, limit=10), [])

    def test_malformed_xml_returns_empty(self):
        self.assertEqual(parse_sitemap("<not-xml"), {})


if __name__ == "__main__":
    unittest.main()