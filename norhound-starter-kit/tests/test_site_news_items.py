"""One dated news item per captured news page, not one per company.

The recall proxy counts dated news claims, and the shipped corpus published a
single dated observation per company: the deepest captured news page. The rest
of the captured pages were thrown away — 1,232 news-path pages across 218
companies, of which 85 companies got a dated claim. A live sample of those
pages showed that half of them carry a machine-readable publication timestamp
in their markup, which is a fact a reviewer can verify from the page.

These tests pin the rules that turn the captured pages into claims:

* every captured news page with a machine-readable publication timestamp is
  its own dated observation,
* an additional page whose only date is mined from prose is not published (a
  mined date can be a copyright year or a date mentioned in passing, not the
  publication date),
* an undated navigation page is never published as padding,
* the number of dated items per company is bounded.
"""

from __future__ import annotations

import unittest

from scripts.extract_company_site_news import (
    MAX_DATED_ITEMS,
    MAX_NEWS_PAGES,
    candidate_pages,
    observations,
    sitemap_candidates,
)


def _profile(pages):
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
                    "pages": pages,
                },
            }
        },
    }


def _page(url, title="Nyheter", excerpt=""):
    return {"url": url, "title": title, "main_text_excerpt": excerpt, "content_sha256": "b" * 64}


# A publication timestamp stated by the markup: the machine-readable class.
MACHINE_READABLE = (
    '<html><head><meta property="article:published_time" content="2026-10-05T08:00:00+02:00">'
    "</head><body><p>Tekst</p></body></html>"
)
# A date in the prose only: the mined class, reserved for the primary page.
MINED_ONLY = "<html><body><p>Publisert 12. oktober 2026</p></body></html>"
NO_DATE = "<html><body><p>Velkommen til nyhetene</p></body></html>"


class SiteNewsItemTests(unittest.TestCase):
    def test_every_dated_page_becomes_its_own_observation(self):
        profile = _profile([
            _page("https://www.example.test/nyheter/2026/oktober/a", "Artikkel A"),
            _page("https://www.example.test/nyheter/2026/oktober/b", "Artikkel B"),
        ])
        fetched = {
            "https://www.example.test/nyheter/2026/oktober/a": MACHINE_READABLE,
            "https://www.example.test/nyheter/2026/oktober/b": MACHINE_READABLE,
        }
        rows = observations(profile, fetched=fetched)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [row["source_url"] for row in rows],
            ["https://www.example.test/nyheter/2026/oktober/a",
             "https://www.example.test/nyheter/2026/oktober/b"],
        )
        for row in rows:
            self.assertEqual(row["observed_at"], "2026-10-05T08:00:00+02:00")
            self.assertEqual(row["signal_type"], "public_post")

    def test_an_additional_page_needs_a_machine_readable_date(self):
        profile = _profile([
            _page("https://www.example.test/nyheter/2026/oktober/a", "Artikkel A"),
            _page("https://www.example.test/nyheter/2026/oktober/b", "Artikkel B"),
        ])
        fetched = {
            "https://www.example.test/nyheter/2026/oktober/a": MACHINE_READABLE,
            "https://www.example.test/nyheter/2026/oktober/b": MINED_ONLY,
        }
        rows = observations(profile, fetched=fetched)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_url"], "https://www.example.test/nyheter/2026/oktober/a")

    def test_an_undated_page_is_never_padded(self):
        profile = _profile([
            _page("https://www.example.test/nyheter/2026/oktober/a", "Artikkel A"),
            _page("https://www.example.test/nyheter/2026/oktober/b", "Artikkel B"),
            _page("https://www.example.test/nyheter", "Nyheter", "Velkommen"),
        ])
        fetched = {
            "https://www.example.test/nyheter/2026/oktober/a": NO_DATE,
            "https://www.example.test/nyheter/2026/oktober/b": NO_DATE,
            "https://www.example.test/nyheter": NO_DATE,
        }
        rows = observations(profile, fetched=fetched)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("observed_at", rows[0])

    def test_the_primary_page_keeps_its_mined_date(self):
        profile = _profile([_page("https://www.example.test/nyheter/2026/oktober/a", "Artikkel A")])
        rows = observations(profile, fetched={"https://www.example.test/nyheter/2026/oktober/a": MINED_ONLY})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["observed_at"], "2026-10-12")

    def test_the_number_of_dated_items_is_bounded(self):
        pages = [_page(f"https://www.example.test/nyheter/2026/oktober/{index}", f"Artikkel {index}")
                 for index in range(MAX_NEWS_PAGES + 5)]
        profile = _profile(pages)
        fetched = {page["url"]: MACHINE_READABLE for page in pages}
        rows = observations(profile, fetched=fetched)
        dated = [row for row in rows if row.get("observed_at")]
        self.assertLessEqual(len(dated), MAX_DATED_ITEMS)

    def test_only_the_bounded_number_of_pages_is_considered(self):
        pages = [_page(f"https://www.example.test/nyheter/2026/oktober/{index}", f"Artikkel {index}")
                 for index in range(MAX_NEWS_PAGES + 5)]
        profile = _profile(pages)
        self.assertEqual(len(candidate_pages(profile)), MAX_NEWS_PAGES)

    def test_the_retained_body_is_bounded(self):
        profile = _profile([_page("https://www.example.test/nyheter/2026/oktober/a", "Artikkel A")])
        body = "<p>" + ("x" * 50_000) + "</p>"
        rows = observations(profile, fetched={"https://www.example.test/nyheter/2026/oktober/a": body})
        self.assertLessEqual(len(rows[0]["metrics"]["body_excerpt"]), 5000)

    def test_a_site_that_is_not_publishable_publishes_nothing(self):
        profile = _profile([_page("https://www.example.test/nyheter/2026/oktober/a", "Artikkel A")])
        profile["evidence"]["website"]["value"]["identity_assessment"] = {"publishable": False}
        self.assertEqual(observations(profile, fetched={}), [])


def _sitemap_row(url, lastmod="2026-10-05", org="810034882"):
    return {
        "organisation_number": org,
        "platform": "company_site",
        "signal_type": "sitemap_page",
        "source_url": "https://www.example.test/",
        "metrics": {"page_url": url, "lastmod": lastmod},
    }


class SitemapNewsTests(unittest.TestCase):
    """The site's own sitemap lists news pages the bounded crawl never reached.

    586 news-path URLs over 89 companies sit in the sitemaps of the shipped
    corpus, and 48 of those companies publish no news fact at all. A sitemap
    entry is the site's own statement that the page exists and when it last
    changed, so it is a candidate page like any other.
    """

    def test_sitemap_news_page_becomes_a_dated_item(self):
        profile = _profile([_page("https://www.example.test/nyheter", "Nyheter", "Velkommen")])
        url = "https://www.example.test/nyheter/2026/oktober/gul-middag"
        rows = observations(
            profile,
            fetched={url: MACHINE_READABLE},
            sitemap=[_sitemap_row(url)],
        )
        self.assertEqual(len(rows), 2)
        dated = [row for row in rows if row.get("observed_at") == "2026-10-05T08:00:00+02:00"]
        self.assertEqual(len(dated), 1)
        self.assertEqual(dated[0]["source_url"], url)
        self.assertEqual(dated[0]["signal_type"], "public_post")

    def test_sitemap_page_outside_the_verified_domain_is_ignored(self):
        profile = _profile([_page("https://www.example.test/nyheter", "Nyheter", "Velkommen")])
        url = "https://other.test/nyheter/2026/oktober/gul-middag"
        rows = observations(
            profile,
            fetched={url: MACHINE_READABLE},
            sitemap=[_sitemap_row(url)],
        )
        self.assertEqual([row["source_url"] for row in rows], ["https://www.example.test/nyheter"])

    def test_candidate_cap_is_24(self):
        pages = [_page(f"https://www.example.test/nyheter/2026/oktober/{index}", f"Artikkel {index}")
                 for index in range(MAX_NEWS_PAGES + 5)]
        profile = _profile(pages)
        self.assertEqual(len(candidate_pages(profile)), MAX_NEWS_PAGES)
        self.assertEqual(MAX_NEWS_PAGES, 24)

    def test_an_additional_sitemap_page_still_needs_a_machine_readable_date(self):
        profile = _profile([_page("https://www.example.test/nyheter", "Nyheter", "Velkommen")])
        url = "https://www.example.test/nyheter/2026/oktober/gul-middag"
        rows = observations(
            profile,
            fetched={url: MINED_ONLY},
            sitemap=[_sitemap_row(url)],
        )
        self.assertEqual([row["source_url"] for row in rows], ["https://www.example.test/nyheter"])

    def test_sitemap_candidates_carry_the_sitemap_date(self):
        profile = _profile([])
        url = "https://www.example.test/nyheter/2026/oktober/gul-middag"
        candidates = sitemap_candidates(profile, [_sitemap_row(url, lastmod="2026-10-07")])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["url"], url)
        self.assertEqual(candidates[0]["lastmod"], "2026-10-07")


if __name__ == "__main__":
    unittest.main()
