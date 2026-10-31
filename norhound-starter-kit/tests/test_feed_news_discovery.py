from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import validate_observation  # noqa: E402
from scripts import extract_company_feed_news as site_feed  # noqa: E402
from scripts import run_feed_news_connector as feed_connector  # noqa: E402
from scripts.extract_company_feed_news import collect_news_pages, feed_guesses_for  # noqa: E402

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Nyheter</title>
<item><title>Åpning av ny avdeling</title><link>https://example.test/nyheter/apning</link>
<pubDate>Tue, 02 Jan 2024 10:00:00 +0000</pubDate></item>
</channel></rss>"""

WEBSITE_VALUE = {
    "final_url": "https://example.test/",
    "identity_assessment": {"status": "exact", "publishable": True},
    "pages": [{"main_text_excerpt": "Velkommen til Example sin hjemmeside."}],
}


def _fetcher(mapping):
    def _fetch(url, timeout=15.0):
        return mapping.get(url), url

    return _fetch


class FeedNewsObservationTests(unittest.TestCase):
    def _observations(self, mapping, website_value=None):
        with patch.object(feed_connector, "fetch", _fetcher(mapping)):
            return feed_connector.observations_for_org(
                "923609016", website_value or dict(WEBSITE_VALUE)
            )

    def test_discovers_feed_linked_from_raw_homepage_html(self):
        homepage = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
        observations = self._observations(
            {
                "https://example.test/": homepage,
                "https://example.test/feed.xml": RSS,
            }
        )
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["effective_at"], "2024-01-02")
        self.assertEqual(observations[0]["source_url"], "https://example.test/nyheter/apning")

    def test_discovers_feed_when_type_attribute_precedes_rel(self):
        homepage = '<html><head><link type="application/atom+xml" rel="alternate" href="/atom.xml"></head></html>'
        observations = self._observations(
            {
                "https://example.test/": homepage,
                "https://example.test/atom.xml": RSS,
            }
        )
        self.assertEqual(len(observations), 1)

    def test_guesses_feed_paths_from_resolved_site_url(self):
        homepage = "<html><body>Ingen feed-lenke her</body></html>"
        observations = self._observations(
            {
                "https://example.test/": homepage,
                "https://example.test/feed/": RSS,
            }
        )
        self.assertEqual(len(observations), 1)

    def test_emitted_observation_is_publishable(self):
        homepage = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
        observations = self._observations(
            {
                "https://example.test/": homepage,
                "https://example.test/feed.xml": RSS,
            }
        )
        self.assertEqual(observations[0]["signal_type"], "public_post")
        self.assertEqual(validate_observation(observations[0]), [])

    def test_uncertain_identity_is_never_published(self):
        homepage = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
        website_value = dict(WEBSITE_VALUE)
        website_value["identity_assessment"] = {"status": "related_or_uncertain", "publishable": False}
        observations = self._observations(
            {
                "https://example.test/": homepage,
                "https://example.test/feed.xml": RSS,
            },
            website_value=website_value,
        )
        self.assertEqual(observations, [])


class NorwegianNewsTitleMatchTests(unittest.TestCase):
    def _index(self):
        from scripts.run_norwegian_news_rss_connector import build_name_index

        profiles = [
            {"organisation_number": "923609016", "name": "Example Kompani AS"},
            {"organisation_number": "924528037", "name": "Statkraft ASA"},
        ]
        return build_name_index(profiles)

    def test_matches_full_legal_name_in_title(self):
        from scripts.run_norwegian_news_rss_connector import match_company_in_title

        self.assertEqual(
            match_company_in_title("Example Kompani AS går med overskudd", self._index()),
            ["923609016"],
        )

    def test_matches_distinctive_short_name_in_title(self):
        from scripts.run_norwegian_news_rss_connector import match_company_in_title

        self.assertEqual(
            match_company_in_title("NVE truer Statkraft med tvangsmulkt", self._index()),
            ["924528037"],
        )

    def test_does_not_match_unrelated_title(self):
        from scripts.run_norwegian_news_rss_connector import match_company_in_title

        self.assertEqual(match_company_in_title("Helt annet selskap går med overskudd", self._index()), [])

    def test_iso_dates_are_parsed_not_only_rfc822(self):
        from scripts.run_norwegian_news_rss_connector import parse_date, parse_rfc822_date

        # the value is published as the source wrote it: a Zulu designator stays
        # Zulu, "+0000" becomes the ISO form of the same offset rather than Z, and
        # a non-UTC offset must survive untouched
        self.assertEqual(parse_date("2026-08-14T10:00:00Z"), "2026-08-14T10:00:00Z")
        self.assertEqual(parse_rfc822_date("Fri, 14 Aug 2026 10:00:00 +0000"), "2026-08-14T10:00:00+00:00")
        self.assertEqual(parse_rfc822_date("Wed, 22 Oct 2025 08:15:00 +0200"), "2025-10-22T08:15:00+02:00")


class DatedNewsPoolKeyTests(unittest.TestCase):
    """The verified-pool key is "<title> (<published datetime>)" with the source's own offset."""

    RSS_OFFSET = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Nyheter</title>
<item><title>Bedre sosial funksjon</title><link>https://example.test/nyheter/bedre</link>
<pubDate>Mon, 22 Sep 2025 20:00:00 +0200</pubDate></item>
</channel></rss>"""

    def test_offset_is_preserved_verbatim(self):
        self.assertEqual(feed_connector.normalize_datetime("2025-09-22T20:00:00+02:00"), "2025-09-22T20:00:00+02:00")
        self.assertEqual(feed_connector.normalize_datetime("Mon, 22 Sep 2025 20:00:00 +0200"), "2025-09-22T20:00:00+02:00")

    def test_naive_and_date_only_sources_get_no_invented_precision(self):
        self.assertEqual(feed_connector.normalize_datetime("2026-10-13T14:53:25"), "2026-10-13T14:53:25")
        self.assertEqual(feed_connector.normalize_datetime("2026-10-13"), "2026-10-13")
        self.assertIsNone(feed_connector.normalize_datetime("ikke en dato"))
        self.assertIsNone(feed_connector.normalize_datetime(None))

    def test_claim_value_matches_the_pool_shape(self):
        self.assertEqual(
            feed_connector.news_claim_value("Bedre  sosial   funksjon", "2025-09-22T20:00:00+02:00"),
            "Bedre sosial funksjon (2025-09-22T20:00:00+02:00)",
        )
        self.assertEqual(feed_connector.news_claim_value("Nyhet", None), "Nyhet")

    def test_observation_carries_dated_news_key(self):
        mapping = {
            "https://example.test/": """<html><head><link rel="alternate" type="application/rss+xml" href="/feed/"></head></html>""",
            "https://example.test/feed/": self.RSS_OFFSET,
        }
        with patch.object(feed_connector, "fetch", _fetcher(mapping)):
            observations = feed_connector.observations_for_org("923609016", dict(WEBSITE_VALUE))
        self.assertEqual(len(observations), 1)
        metrics = observations[0]["metrics"]
        self.assertEqual(metrics["published_at"], "2025-09-22T20:00:00+02:00")
        self.assertEqual(metrics["published_date"], "2025-09-22")
        self.assertEqual(metrics["claim_value"], "Bedre sosial funksjon (2025-09-22T20:00:00+02:00)")
        self.assertEqual(validate_observation(observations[0]), [])


class SiteFeedEntityStatusTests(unittest.TestCase):
    def test_only_exact_identity_status_is_publishable(self):
        helper = getattr(site_feed, "exact_entity_for_status", None)
        self.assertIsNotNone(helper, "exact_entity_for_status helper is missing")
        self.assertTrue(helper("exact"))
        self.assertTrue(helper("verified"))
        self.assertFalse(helper("related_or_uncertain"))
        self.assertFalse(helper("review"))
        self.assertFalse(helper(""))


class ProbedSiteNewsTests(unittest.TestCase):
    def _record(self, excerpt="Publisert 2026-08-14"):
        return {
            "status": "available",
            "source_url": "https://example.test/",
            "retrieved_at": "2026-10-25T00:00:00Z",
            "content_sha256": "a" * 64,
            "value": {
                "final_url": "https://example.test/",
                "pages": [
                    {"url": "https://example.test/", "title": "Forside", "main_text_excerpt": "Velkommen", "content_sha256": "a" * 64},
                    {"url": "https://example.test/nyheter/oppdatering", "title": "Oppdatering", "main_text_excerpt": excerpt, "content_sha256": "b" * 64},
                ],
                "social_links": [],
                "structured_organisations": [],
            },
        }

    def _rows(self, record, body=None):
        from scripts import extract_probed_site_signals as probed

        with patch.object(probed, "fetch_website", lambda url: (record, {})):
            if body is None:
                with patch.object(probed, "fetch_page_body", lambda url, timeout=20: None):
                    return probed.process(
                        {
                            "organisation_number": "923609016",
                            "website": "https://example.test/",
                            "identity_score": "0.95",
                            "method": "email_or_slug_probe_v1",
                        },
                        {"923609016": {"organisation_number": "923609016", "name": "Example AS"}},
                    )
            with patch.object(probed, "fetch_page_body", lambda url, timeout=20: body):
                return probed.process(
                    {
                        "organisation_number": "923609016",
                        "website": "https://example.test/",
                        "identity_score": "0.95",
                        "method": "email_or_slug_probe_v1",
                    },
                    {"923609016": {"organisation_number": "923609016", "name": "Example AS"}},
                )

    def test_probed_verified_site_emits_dated_news(self):
        rows = self._rows(self._record())
        news = [row for row in rows if row.get("signal_type") == "public_post"]
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["observed_at"], "2026-08-14")
        self.assertTrue(news[0]["exact_entity"])
        self.assertEqual(validate_observation(news[0]), [])

    def test_probed_verified_site_mines_date_from_page_body(self):
        rows = self._rows(
            self._record(excerpt="Oppdatering om driften"),
            body="<html><body>Publisert 2026-08-14</body></html>",
        )
        news = [row for row in rows if row.get("signal_type") == "public_post"]
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["observed_at"], "2026-08-14")
        self.assertEqual(news[0]["metrics"]["date_source"], "page_body")


class NewsPageDiscoveryTests(unittest.TestCase):
    def test_returns_joined_same_domain_link(self):
        html = '<a href="/nyheter/">Nyheter</a><a href="/om">Om oss</a>'
        self.assertEqual(
            collect_news_pages(html, "https://example.test/"),
            ["https://example.test/nyheter/"],
        )

    def test_excludes_external_domain(self):
        html = '<a href="https://facebook.com/no/nyheter">Feed</a><a href="https://other.test/blogg/x">B</a>'
        self.assertEqual(collect_news_pages(html, "https://example.test/"), [])

    def test_caps_at_five(self):
        html = "".join(f'<a href="/nyheter/{i}">N{i}</a>' for i in range(8))
        self.assertEqual(len(collect_news_pages(html, "https://example.test/")), 5)

    def test_empty_when_no_news_links(self):
        html = '<a href="/om">Om</a><a href="/kontakt">Kontakt</a>'
        self.assertEqual(collect_news_pages(html, "https://example.test/"), [])

    def test_matches_norwegian_news_terms(self):
        html = '<a href="/aktuelt/">A</a><a href="/presse">P</a><a href="/blogg/innlegg">B</a><a href="/katalog">K</a>'
        result = collect_news_pages(html, "https://example.test/")
        self.assertEqual(
            result,
            ["https://example.test/aktuelt/", "https://example.test/presse", "https://example.test/blogg/innlegg"],
        )

    def test_feed_guess_for_news_page(self):
        self.assertEqual(
            feed_guesses_for("https://example.test/aktuelt"),
            ["https://example.test/aktuelt/feed/"],
        )

    def test_feed_guess_skips_when_already_a_feed(self):
        self.assertEqual(feed_guesses_for("https://example.test/nyheter/feed/"), [])


if __name__ == "__main__":
    unittest.main()
