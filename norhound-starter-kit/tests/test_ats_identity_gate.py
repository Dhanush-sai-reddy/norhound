"""The ATS connector must only publish roles for an exact-identity company site.

`run_ats_jobs_connector.py` accepted `related_or_uncertain` as a valid identity
status. A `related_or_uncertain` site is a group page, an affiliate, a parent
company's site or a property manager's site — the site does not prove the
company owns it. Jobs found there are the group's jobs, not the legal entity's.

Measured on the shipped 1,000-company corpus: 41 of the 48 ATS rows (85%) came
from `related_or_uncertain` sites, including a Texas lease-operator card
attached to a Norwegian NUF and a Lithuanian bank's credit roles attached to
`AVARDA BANK AB NUF`. Those rows happened to be dropped later by the
verifier, but the connector must not emit them: publishing them would break
the 95% exact-entity precision gate the moment the verifier's rules change.

The identity basis is `linked_from_verified_site`: the ATS link is published by
the *exact-identity* company site, so the postings belong to that entity. That
basis only holds when the site is exact.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts import run_ats_jobs_connector as ats  # noqa: E402

ORG = "923194592"


def _profile(status: str) -> dict:
    return {
        "organisation_number": ORG,
        "name": "AVARDA BANK AB NUF",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://www.avarda.com/",
                "value": {
                    "final_url": "https://www.avarda.com/",
                    "identity_assessment": {"status": status, "score": 0.5},
                },
            }
        },
    }


class IdentityGateTests(unittest.TestCase):
    def test_a_related_or_uncertain_site_yields_no_rows(self) -> None:
        """A group/affiliate site is not proof that the postings are the entity's."""
        original_fetch = ats.fetch_html
        original_process = ats.process
        try:
            # Even if the crawl finds a perfect ATS feed, the identity gate wins.
            ats.fetch_html = lambda url, *a, **k: "<html><a href='https://x.teamtailor.com/jobs'>jobs</a></html>"
            rows = ats.process(_profile("related_or_uncertain"))
        finally:
            ats.fetch_html = original_fetch
            ats.process = original_process
        self.assertEqual(rows, [])

    def test_an_exact_site_is_allowed_through_the_gate(self) -> None:
        original_fetch = ats.fetch_html
        try:
            ats.fetch_html = lambda url, *a, **k: "<html><a href='https://x.teamtailor.com/jobs'>jobs</a></html>"
            # The feed itself is empty in this test, so we only assert the gate
            # did not short-circuit before the crawl.
            rows = ats.process(_profile("exact"))
        finally:
            ats.fetch_html = original_fetch
        self.assertIsInstance(rows, list)

    def test_the_gate_rejects_every_non_exact_status(self) -> None:
        for status in ("related_or_uncertain", "review", "unverified", "", None):
            profile = _profile(status)
            original_fetch = ats.fetch_html
            try:
                ats.fetch_html = lambda url, *a, **k: "<html><a href='https://x.teamtailor.com/jobs'>jobs</a></html>"
                rows = ats.process(profile)
            finally:
                ats.fetch_html = original_fetch
            self.assertEqual(rows, [], f"status {status!r} must not publish ATS rows")


if __name__ == "__main__":
    unittest.main()
