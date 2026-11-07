from __future__ import annotations

import json
import unittest
from unittest import mock

import scripts.run_ats_jobs_connector as conn
from scripts.run_ats_jobs_connector import collect_careers_page_links, extract_role_cards, find_ats


class AtsRobustnessTests(unittest.TestCase):
    def test_fetch_html_returns_none_when_hostname_does_not_resolve(self):
        with mock.patch.object(conn, "_robots_allowed", return_value=True):
            with mock.patch.object(conn, "http", side_effect=ValueError("Hostname did not resolve")):
                self.assertIsNone(conn.fetch_html("https://does-not-exist.invalid/"))

    def test_process_returns_no_rows_for_unverified_site(self):
        profile = {
            "organisation_number": "123456789",
            "evidence": {
                "website": {
                    "status": "available",
                    "source_url": "https://related.test/",
                    "value": {
                        "identity_assessment": {"status": "related_or_uncertain", "publishable": False},
                        "final_url": "https://related.test/",
                    },
                }
            },
        }
        with mock.patch.object(conn, "fetch_html", return_value='<html><a href="https://jobs.lever.co/x">Jobs</a></html>'):
            self.assertEqual(conn.process(profile), [])

    def test_process_emits_rows_for_exact_site(self):
        profile = {
            "organisation_number": "123456789",
            "evidence": {
                "website": {
                    "status": "available",
                    "source_url": "https://example.test/",
                    "value": {
                        "identity_assessment": {"status": "exact", "publishable": True},
                        "final_url": "https://example.test/",
                    },
                }
            },
        }
        lever_payload = json.dumps([{"id": "1", "text": "Engineer", "hostedUrl": "https://jobs.lever.co/x/1"}])
        with mock.patch.object(conn, "fetch_html", return_value='<html><a href="https://jobs.lever.co/x">Jobs</a></html>'):
            with mock.patch.object(conn, "http", return_value=lever_payload.encode()):
                rows = conn.process(profile)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["exact_entity"])
        self.assertEqual(rows[0]["signal_type"], "job_posting")


class CollectCareersPageLinksTests(unittest.TestCase):
    def test_returns_joined_same_domain_careers_link(self):
        html = '<html><a href="/karriere">Karriere</a></html>'
        self.assertEqual(
            collect_careers_page_links(html, "https://example.test/"),
            ["https://example.test/karriere"],
        )

    def test_excludes_external_domain(self):
        html = '<a href="https://evil.test/careers">Careers</a>'
        self.assertEqual(collect_careers_page_links(html, "https://example.test/"), [])

    def test_caps_at_five(self):
        html = "".join(f'<a href="/karriere/{i}">Karriere {i}</a>' for i in range(8))
        links = collect_careers_page_links(html, "https://example.test/")
        self.assertEqual(len(links), 5)
        self.assertEqual(links[0], "https://example.test/karriere/0")
        self.assertEqual(links[4], "https://example.test/karriere/4")

    def test_empty_when_no_match(self):
        html = '<a href="/om-oss">Om oss</a><a href="/tjenester">Tjenester</a>'
        self.assertEqual(collect_careers_page_links(html, "https://example.test/"), [])

    def test_dedups_and_keeps_order_of_appearance(self):
        html = (
            '<a href="/tjenester">Tjenester</a>'
            '<a href="/jobs">Jobs</a>'
            '<a href="/jobs">Jobs again</a>'
            '<a href="/Karriere">Karriere</a>'
            '<a href="https://evil.test/jobs">External</a>'
        )
        self.assertEqual(
            collect_careers_page_links(html, "https://example.test/"),
            ["https://example.test/jobs", "https://example.test/Karriere"],
        )


class FindAtsTests(unittest.TestCase):
    def test_workable_match(self):
        m = find_ats('<a href="https://apply.workable.com/acme-nordic">Apply</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("workable"), "apply.workable.com/acme-nordic")
        self.assertEqual(m.group("workable_slug"), "acme-nordic")

    def test_webcruiter_match(self):
        m = find_ats('<a href="https://acme.webcruiter.com">Jobs</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("webcruiter"), "acme.webcruiter.com")

    def test_jobylon_match(self):
        m = find_ats('<a href="https://www.jobylon.com/jobs/12345">Jobs</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("jobylon"), "www.jobylon.com/jobs/12345")
        self.assertEqual(m.group("jobylon_id"), "12345")

    def test_reachmee_match(self):
        m = find_ats('<a href="https://acme.reachmee.com">Jobs</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("reachmee"), "acme.reachmee.com")

    def test_hrmanager_match(self):
        m = find_ats('<a href="https://acme.hr-manager.net">Jobs</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("hrmanager"), "acme.hr-manager.net")

    def test_recman_match(self):
        m = find_ats('<a href="https://acme.recman.no">Jobs</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("recman"), "acme.recman.no")

    def test_easycruit_match(self):
        m = find_ats('<a href="https://acme.easycruit.com">Jobs</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("easycruit"), "acme.easycruit.com")

    def test_jobbnorge_match(self):
        m = find_ats('<a href="https://www.jobbnorge.no">Jobs</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("jobbnorge"), "www.jobbnorge.no")

    def test_new_providers_match_case_insensitive(self):
        m = find_ats('<a HREF="HTTPS://WWW.JOBBNORGE.NO/jobb">Ledige</a>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group("jobbnorge"), "WWW.JOBBNORGE.NO")

    def test_existing_workday_still_matches(self):
        m = find_ats("https://acme.wd3.myworkdayjobs.com/acme-jobs")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("workday"), "acme")
        self.assertEqual(m.group("wdn"), "3")
        self.assertEqual(m.group("wdsite"), "acme-jobs")

    def test_existing_lever_still_matches(self):
        m = find_ats("https://jobs.lever.co/acme")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("lever"), "acme")

    def test_existing_greenhouse_still_matches(self):
        m = find_ats("https://boards.greenhouse.io/acme")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("greenhouse"), "acme")

    def test_existing_smartrecruiters_still_matches(self):
        m = find_ats("https://acme.smartrecruiters.com")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("smart"), "acme")

    def test_existing_teamtailor_still_matches(self):
        m = find_ats("https://acme.teamtailor.com")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("teamtailor"), "acme")


class ExtractRoleCardsTests(unittest.TestCase):
    BASE = "https://acme.webcruiter.com/"

    def test_extracts_plausible_job_link(self):
        html = '<a href="/job/123"><span>Senior Backend Developer</span></a>'
        self.assertEqual(
            extract_role_cards(html, self.BASE),
            [{"title": "Senior Backend Developer", "url": "https://acme.webcruiter.com/job/123"}],
        )

    def test_rejects_kontakt_oss(self):
        html = '<a href="/kontakt">Kontakt oss</a>'
        self.assertEqual(extract_role_cards(html, self.BASE), [])

    def test_rejects_short_text(self):
        html = '<a href="/a">AI</a><a href="/b">Jobb</a>'
        self.assertEqual(extract_role_cards(html, self.BASE), [])

    def test_rejects_stopword_prefixed_text(self):
        html = (
            '<a href="/1">Les mer her</a>'
            '<a href="/2">Se alle stillinger</a>'
            '<a href="/3">Personvern</a>'
        )
        self.assertEqual(extract_role_cards(html, self.BASE), [])

    def test_caps_at_twenty(self):
        html = "".join(f'<a href="/job/{i}">Stilling Nummer {i}</a>' for i in range(30))
        cards = extract_role_cards(html, self.BASE)
        self.assertEqual(len(cards), 20)
        self.assertEqual(cards[0]["url"], "https://acme.webcruiter.com/job/0")
        self.assertEqual(cards[19]["url"], "https://acme.webcruiter.com/job/19")

    def test_excludes_external_domain(self):
        html = '<a href="https://evil.test/job/1">Senior Backend Developer</a>'
        self.assertEqual(extract_role_cards(html, self.BASE), [])

    def test_dedups_by_url_and_collapses_whitespace(self):
        html = (
            '<a href="/job/1">  Senior   Developer  </a>'
            '<a href="/job/1">Senior Developer again</a>'
            '<a href="/job/2">Lead Engineer</a>'
        )
        self.assertEqual(
            extract_role_cards(html, self.BASE),
            [
                {"title": "Senior Developer", "url": "https://acme.webcruiter.com/job/1"},
                {"title": "Lead Engineer", "url": "https://acme.webcruiter.com/job/2"},
            ],
        )


class ProcessWiringTests(unittest.TestCase):
    def _profile(self):
        return {
            "organisation_number": "981234567",
            "evidence": {
                "website": {
                    "status": "available",
                    "source_url": "https://acme.test/",
                    "value": {"identity_assessment": {"status": "exact"}},
                }
            },
        }

    def test_publishes_role_cards_for_new_provider(self):
        pages = {
            "https://acme.test/": '<html><a href="https://acme.webcruiter.com/">Ledige stillinger</a></html>',
            "https://acme.webcruiter.com/": (
                '<a href="/job/1">Senior Developer</a><a href="/job/2">Lead Engineer</a>'
            ),
        }

        def fake_fetch(url, *a, **k):
            for key, value in pages.items():
                if key.rstrip("/") == url.rstrip("/"):
                    return value
            return None

        with mock.patch.object(conn, "fetch_html", side_effect=fake_fetch):
            rows = conn.process(self._profile())
        self.assertTrue(rows, "expected rows for webcruiter role cards")
        for row in rows:
            self.assertEqual(row["metrics"]["ats"], "webcruiter")
            self.assertEqual(row["strategy"], "ats_role_card")
            self.assertEqual(row["signal_type"], "job_posting")
            self.assertTrue(row["exact_entity"])
        self.assertEqual({r["evidence_span"].split(" (")[0] for r in rows}, {"Senior Developer", "Lead Engineer"})

    def test_uses_discovered_careers_link_before_hardcoded_paths(self):
        pages = {
            "https://acme.test/": '<html><a href="/karriere/stillinger">Karriere</a></html>',
            "https://acme.test/karriere/stillinger": '<html><a href="https://jobs.lever.co/acme">Jobs</a></html>',
        }

        def fake_fetch(url, *a, **k):
            return pages.get(url)

        lever = json.dumps([{"text": "Dev", "hostedUrl": "https://jobs.lever.co/acme/1"}]).encode()

        with mock.patch.object(conn, "fetch_html", side_effect=fake_fetch), \
                mock.patch.object(conn, "http", return_value=lever):
            rows = conn.process(self._profile())
        self.assertTrue(rows, "expected lever jobs found via discovered careers link")
        self.assertEqual(rows[0]["metrics"]["ats"], "lever")
        self.assertEqual(rows[0]["identity_proof"][0]["ats_link_page"], "https://acme.test/karriere/stillinger")


    def test_uses_full_ats_url_including_path(self):
        pages = {
            "https://acme.test/": '<html><a href="https://web103.reachmee.com/rk/mee/index.phtml">Ledige</a></html>',
            "https://web103.reachmee.com/rk/mee/index.phtml": (
                '<a href="/rk/mee/job/1">Senior Developer</a>'
            ),
        }

        def fake_fetch(url, *a, **k):
            for key, value in pages.items():
                if key.rstrip("/") == url.rstrip("/"):
                    return value
            return None

        with mock.patch.object(conn, "fetch_html", side_effect=fake_fetch):
            rows = conn.process(self._profile())
        self.assertTrue(rows, "expected role cards fetched from the full ATS URL with path")
        self.assertEqual(rows[0]["metrics"]["ats"], "reachmee")


if __name__ == "__main__":
    unittest.main()
