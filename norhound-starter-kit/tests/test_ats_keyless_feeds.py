"""Keyless ATS feeds: Teamtailor JSON, Recruitee offers, Easycruit RSS.

Three public applicant-tracking systems publish a machine-readable feed with
no API key, no login and no paid account, and their robots rules allow the
feed paths:

* Teamtailor — `https://<tenant>.teamtailor.com/jobs.json` (JSON Feed 1.1).
  The tenant's robots.txt disallows only `/app/`, `/messages/`, `/messenger/`,
  `/facebook/tab/` and `/jobs/internal/`, so `/jobs.json` is allowed. The feed
  carries `title`, `url`, `date_published` and `content_html` per role.
* Recruitee — `https://<tenant>.recruitee.com/api/offers/`. robots.txt
  disallows only `/v/`. Each offer carries `title`, `slug`,
  `careers_apply_url`, `published_at` and `company_name`.
* Easycruit — `https://<tenant>.easycruit.com/rss/jobs`. The per-vacancy HTML
  page answers HTTP 202 with an empty body (anti-bot), so the RSS feed is the
  only viable keyless path.

Two rules make the rows safe to publish:

1. The tenant is only ever reached through a link published on the company's
   own exact-identity site (`linked_from_verified_site`). A `related_or_uncertain`
   site is a group page and its roles belong to someone else.
2. These three platforms are *multi-tenant*: one tenant can host boards for
   unrelated companies. So the feed's own company name must corroborate the
   legal entity before any role is published.

Every row also carries the role's real publication date. A role card without a
date is still a role card, but it must not borrow the crawl date as its
publication date.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts import run_ats_jobs_connector as ats  # noqa: E402

ORG = "937901925"


def _profile(name: str = "BIG BITE AS", status: str = "exact") -> dict:
    return {
        "organisation_number": ORG,
        "name": name,
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://bigbite.no/",
                "value": {
                    "final_url": "https://bigbite.no/",
                    "identity_assessment": {"status": status, "score": 0.95},
                },
            }
        },
    }


TEAMTAILOR_FEED = {
    "version": "https://jsonfeed.org/version/1.1",
    "title": "Big Bite",
    "items": [
        {
            "id": "9501c072",
            "title": "Butikkeier Big Bite",
            "url": "https://bigbite.teamtailor.com/jobs/8588957-butikkeier-big-bite",
            "date_published": "2026-10-22T00:00:00+02:00",
            "content_html": "<p>Klar for å drive din egen Big Bite?</p>",
        }
    ],
}

RECRUITEE_FEED = {
    "offers": [
        {
            "title": "Senior Manager, Quality Operations",
            "slug": "senior-manager-quality-operations",
            "published_at": "2026-10-12 08:26:26 UTC",
            "company_name": "Big Bite",
            "careers_apply_url": "https://bigbite.recruitee.com/o/senior-manager-quality-operations/c/new",
            "requirements": "<p>Vi ser etter en leder.</p>",
        }
    ],
}

EASYCRUIT_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Big Bite</title>
    <item>
      <title>Butikksjef Big Bite Oslo</title>
      <link>https://bigbite.easycruit.com/vacancy/3675555</link>
      <pubDate>Sat, 07 Nov 2026 00:11:25 +0000</pubDate>
      <description><p>Vi trenger en butikksjef.</p></description>
    </item>
  </channel>
</rss>
"""


class FeedReaderTests(unittest.TestCase):
    def test_teamtailor_json_feed_is_parsed(self) -> None:
        jobs = ats.parse_teamtailor_feed(json.dumps(TEAMTAILOR_FEED))
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["title"], "Butikkeier Big Bite")
        self.assertEqual(job["url"], "https://bigbite.teamtailor.com/jobs/8588957-butikkeier-big-bite")
        self.assertEqual(job["posted"], "2026-10-22T00:00:00+02:00")
        self.assertEqual(job["feed_company"], "Big Bite")
        self.assertIn("drive din egen Big Bite", job["description"])

    def test_recruitee_offers_are_parsed(self) -> None:
        jobs = ats.parse_recruitee_feed(json.dumps(RECRUITEE_FEED))
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["title"], "Senior Manager, Quality Operations")
        self.assertEqual(
            job["url"],
            "https://bigbite.recruitee.com/o/senior-manager-quality-operations/c/new",
        )
        self.assertEqual(job["posted"], "2026-10-12T08:26:26Z")
        self.assertEqual(job["feed_company"], "Big Bite")

    def test_easycruit_rss_is_parsed(self) -> None:
        jobs = ats.parse_easycruit_feed(EASYCRUIT_RSS)
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["title"], "Butikksjef Big Bite Oslo")
        self.assertEqual(job["url"], "https://bigbite.easycruit.com/vacancy/3675555")
        self.assertEqual(job["posted"], "2026-11-07T00:11:25Z")
        self.assertEqual(job["feed_company"], "Big Bite")

    def test_a_broken_feed_yields_no_rows(self) -> None:
        self.assertEqual(ats.parse_teamtailor_feed("not json"), [])
        self.assertEqual(ats.parse_recruitee_feed("not json"), [])
        self.assertEqual(ats.parse_easycruit_feed("not xml at all <"), [])

    def test_a_feed_with_no_items_yields_no_rows(self) -> None:
        self.assertEqual(ats.parse_teamtailor_feed(json.dumps({"items": []})), [])
        self.assertEqual(ats.parse_recruitee_feed(json.dumps({"offers": []})), [])
        self.assertEqual(ats.parse_easycruit_feed("<rss><channel></channel></rss>"), [])


class CompanyNameGuardTests(unittest.TestCase):
    def test_a_matching_feed_company_name_corroborates_the_entity(self) -> None:
        self.assertTrue(ats.feed_company_matches(_profile(), "Big Bite"))

    def test_a_different_feed_company_name_does_not(self) -> None:
        self.assertFalse(ats.feed_company_matches(_profile(), "Lekia"))

    def test_an_organisation_number_in_the_feed_name_counts(self) -> None:
        self.assertTrue(ats.feed_company_matches(_profile(), f"Big Bite {ORG}"))


class ProcessTests(unittest.TestCase):
    def _run(self, html: str, profile: dict, feed: str, jobs: list[dict]) -> list[dict]:
        original_fetch = ats.fetch_html
        original_feed = getattr(ats, feed)
        original_robots = ats._robots_allowed
        try:
            ats.fetch_html = lambda url, *a, **k: html
            ats._robots_allowed = lambda url, timeout: True
            setattr(ats, feed, lambda *a, **k: jobs)
            return ats.process(profile)
        finally:
            ats.fetch_html = original_fetch
            setattr(ats, feed, original_feed)
            ats._robots_allowed = original_robots

    def test_a_teamtailor_link_publishes_a_dated_role_card(self) -> None:
        jobs = ats.parse_teamtailor_feed(json.dumps(TEAMTAILOR_FEED))
        rows = self._run(
            '<html><a href="https://bigbite.teamtailor.com/jobs">Jobb</a></html>',
            _profile(),
            "teamtailor_json_jobs",
            jobs,
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["signal_type"], "job_posting")
        self.assertEqual(row["source_url"], "https://bigbite.teamtailor.com/jobs/8588957-butikkeier-big-bite")
        self.assertEqual(row["signal"]["job_title"], "Butikkeier Big Bite")
        self.assertEqual(row["signal"]["published"], "2026-10-22T00:00:00+02:00")

    def test_a_recruitee_link_publishes_a_dated_role_card(self) -> None:
        jobs = ats.parse_recruitee_feed(json.dumps(RECRUITEE_FEED))
        rows = self._run(
            '<html><a href="https://bigbite.recruitee.com/o/x">Jobb</a></html>',
            _profile(),
            "recruitee_jobs",
            jobs,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signal"]["published"], "2026-10-12T08:26:26Z")

    def test_an_easycruit_link_publishes_a_dated_role_card(self) -> None:
        jobs = ats.parse_easycruit_feed(EASYCRUIT_RSS)
        rows = self._run(
            '<html><a href="https://bigbite.easycruit.com/vacancy/1">Jobb</a></html>',
            _profile(),
            "easycruit_jobs",
            jobs,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signal"]["published"], "2026-11-07T00:11:25Z")

    def test_a_role_card_never_borrows_the_crawl_date(self) -> None:
        """An undated role card stays undated; the crawl date is not a publication date."""
        jobs = [{"title": "Butikkeier Big Bite", "url": "https://bigbite.teamtailor.com/jobs/1",
                 "posted": None, "description": "", "feed_company": "Big Bite"}]
        rows = self._run(
            '<html><a href="https://bigbite.teamtailor.com/jobs">Jobb</a></html>',
            _profile(),
            "teamtailor_json_jobs",
            jobs,
        )
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["signal"].get("published"))

    def test_a_multi_tenant_feed_for_another_company_publishes_nothing(self) -> None:
        jobs = [{"title": "Butikkeier Lekia", "url": "https://lekia.teamtailor.com/jobs/1",
                 "posted": "2026-10-22T00:00:00+02:00", "description": "", "feed_company": "Lekia"}]
        rows = self._run(
            '<html><a href="https://bigbite.teamtailor.com/jobs">Jobb</a></html>',
            _profile(),
            "teamtailor_json_jobs",
            jobs,
        )
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
