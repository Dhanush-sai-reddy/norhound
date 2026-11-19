"""A role card is a role title plus an apply action — never a careers page.

The shipped jobs connector published zero role cards: all 159 of its rows were
`careers_page`. A live probe of the captured careers pages found 14 companies
whose site carries a real role card (a role title *and* an apply action), and
those companies publish no hiring fact at all today, because hiring is the
only scored fact family below 99 % (49 / 84).

These tests pin the four acceptance rules of the role-card connector:

* a role page with a role title and an apply action publishes `job_posting`,
* a generic careers hub ("Ledige stillinger") is not a role card,
* a page that says it has no open positions is not a role card,
* a role page without an apply action is not a role card,
* a role page on another domain, or one that never names the company, is
  rejected — the identity rule is what keeps a group site from publishing
  another entity's vacancy,
* the cards per company are bounded and ordered deterministically,
* the published observation survives the fail-safe verifier.
"""

from __future__ import annotations

import hashlib
import unittest

from scripts.extract_company_site_role_cards import (
    MAX_CARDS,
    observations,
)
from scripts.verify_and_label_observations import verify

ORG = "981023048"
NAME = "APRIIL REKLAME AS"
SITE = "https://apriil.no/"


def _profile(pages=(), website=SITE, org=ORG, name=NAME):
    return {
        "organisation_number": org,
        "name": name,
        "website": website,
        "evidence": {
            "website": {
                "status": "available",
                "source_url": SITE,
                "retrieved_at": "2026-11-19T00:00:00Z",
                "content_sha256": "f" * 64,
                "value": {
                    "identity_assessment": {
                        "publishable": True,
                        "score": 0.95,
                        "method": "deterministic_name_org_evidence_v2",
                    },
                    "final_url": SITE,
                    "registered_domain": "apriil.no",
                    "pages": list(pages),
                },
            }
        },
    }


def _page(url, title="Ledige stillinger", excerpt=""):
    return {"url": url, "title": title, "main_text_excerpt": excerpt, "content_sha256": "b" * 64}


CAREERS_HUB = """
<html><head><title>Ledige stillinger</title></head>
<body>
  <h1>Ledige stillinger</h1>
  <p>Vi har flere ledige stillinger hos oss.</p>
  <a href="/ledige-stillinger/senior-digital-markedsforer">Senior digital markedsfører</a>
  <a href="/ledige-stillinger/strukturert-skrivetalent">Strukturert skrivetalent med teft for teknologi</a>
</body></html>
"""

ROLE_PAGE = """
<html><head><title>Senior digital markedsfører</title></head>
<body>
  <h1>Senior digital markedsfører</h1>
  <p>APRIIL REKLAME AS søker en senior digital markedsfører.</p>
  <a href="mailto:lasse.maroen@apriil.no?subject=S%C3%B8knad">Søk på stillingen</a>
</body></html>
"""


class RoleCardRules(unittest.TestCase):
    def test_role_page_with_apply_action_publishes_job_posting(self):
        profile = _profile(pages=[_page(SITE + "ledige-stillinger")])
        url = SITE + "ledige-stillinger/senior-digital-markedsforer"
        raw = ROLE_PAGE.encode("utf-8")
        rows = observations(profile, {url: raw})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["signal_type"], "job_posting")
        self.assertEqual(row["platform"], "company_site")
        self.assertEqual(row["organisation_number"], ORG)
        self.assertEqual(row["metrics"]["job_title"], "Senior digital markedsfører")
        self.assertEqual(
            row["metrics"]["apply_url"],
            "mailto:lasse.maroen@apriil.no?subject=S%C3%B8knad",
        )
        self.assertEqual(row["content_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(row["acquisition_mode"], "permitted_public_page")
        self.assertEqual(row["rights_status"], "approved")
        self.assertTrue(row["identity_proof"])

    def test_generic_careers_page_is_not_a_role_card(self):
        profile = _profile(pages=[_page(SITE + "ledige-stillinger")])
        hub = """
        <html><head><title>Ledige stillinger</title></head><body>
          <h1>Ledige stillinger</h1>
          <p>Vi har flere ledige stillinger.</p>
          <a href="/kontakt">Send søknad</a>
        </body></html>
        """
        self.assertEqual(observations(profile, {SITE + "ledige-stillinger": hub.encode("utf-8")}), [])

    def test_negated_open_positions_page_is_not_a_role_card(self):
        profile = _profile(pages=[_page(SITE + "ledige-stillinger")])
        page = """
        <html><head><title>Ledige stillinger</title></head><body>
          <h1>Ledige stillinger</h1>
          <p>Vi har ingen ledige stillinger akkurat nå.</p>
          <a href="/kontakt">Send søknad</a>
        </body></html>
        """
        self.assertEqual(observations(profile, {SITE + "ledige-stillinger": page.encode("utf-8")}), [])

    def test_role_page_without_apply_action_is_not_a_role_card(self):
        profile = _profile(pages=[_page(SITE + "ledige-stillinger")])
        page = """
        <html><head><title>Senior digital markedsfører</title></head><body>
          <h1>Senior digital markedsfører</h1>
          <p>APRIIL REKLAME AS søker en senior digital markedsfører.</p>
          <a href="/">Tilbake</a>
        </body></html>
        """
        url = SITE + "ledige-stillinger/senior-digital-markedsforer"
        self.assertEqual(observations(profile, {url: page.encode("utf-8")}), [])

    def test_role_page_on_another_domain_is_rejected(self):
        profile = _profile(pages=[_page(SITE + "ledige-stillinger")])
        url = "https://www.finn.no/job/fulltime/ad.html?finnkode=288923463"
        self.assertEqual(observations(profile, {url: ROLE_PAGE.encode("utf-8")}), [])

    def test_role_page_that_does_not_name_the_company_is_rejected(self):
        # The page is on the company's own domain but never names the company,
        # and the domain is not the one BRREG declares for this organisation.
        profile = _profile(pages=[_page(SITE + "ledige-stillinger")], website="https://other-registry-domain.no/")
        page = """
        <html><head><title>Senior digital markedsfører</title></head><body>
          <h1>Senior digital markedsfører</h1>
          <p>Vi søker en senior digital markedsfører til vårt team.</p>
          <a href="mailto:hr@example.no?subject=S%C3%B8knad">Søk på stillingen</a>
        </body></html>
        """
        url = SITE + "ledige-stillinger/senior-digital-markedsforer"
        self.assertEqual(observations(profile, {url: page.encode("utf-8")}), [])

    def test_role_cards_are_bounded_and_sorted(self):
        pages = [_page(SITE + "ledige-stillinger")]
        profile = _profile(pages=pages)
        fetched = {}
        for index in range(10):
            url = f"{SITE}ledige-stillinger/rolle-{index:02d}"
            fetched[url] = (
                "<html><body><h1>Rolle nummer "
                + f"{index:02d}"
                + "</h1>"
                "<p>APRIIL REKLAME AS søker en kollega.</p>"
                '<a href="mailto:hr@apriil.no?subject=Soknad">Søk på stillingen</a>'
                "</body></html>"
            ).encode("utf-8")
        rows = observations(profile, fetched)
        self.assertEqual(len(rows), MAX_CARDS)
        self.assertEqual(
            [row["source_url"] for row in rows],
            sorted(row["source_url"] for row in rows),
        )

    def test_observations_pass_the_fail_safe_verifier(self):
        profile = _profile(pages=[_page(SITE + "ledige-stillinger")])
        url = SITE + "ledige-stillinger/senior-digital-markedsforer"
        rows = observations(profile, {url: ROLE_PAGE.encode("utf-8")})
        self.assertEqual(len(rows), 1)
        label = verify(rows[0], profile)
        self.assertEqual(label["exact_entity"], 1)
        self.assertEqual(label["metric_correct"], 1)


if __name__ == "__main__":
    unittest.main()
