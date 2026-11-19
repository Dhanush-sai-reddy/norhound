"""The ATS connector must not call a navigation link a role card.

The shipped corpus has 26 ATS rows over 3 companies, 0 published: the
fail-safe gate rejects the third-party board pages. But 3 of those rows carry
`metrics.role_card: true` for a jobbnorge *navigation* link whose anchor text
is "Ledige stillinger" — a link to the vacancies index, not a role. The flag is
wrong even though the row is unpublished, and would become a wrong hiring fact
the moment the identity gate is widened.

These tests pin the rule: a generic vacancies link is not a role card; a link
that names a role is.
"""

from __future__ import annotations

import unittest

from scripts.run_ats_jobs_connector import extract_role_cards

BOARD = "https://www.jobbnorge.no/ledige-stillinger"


class ATSRoleCardTests(unittest.TestCase):
    def test_navigation_link_is_not_a_role_card(self):
        html = (
            "<html><body><nav>"
            '<a href="/ledige-stillinger">Ledige stillinger</a>'
            '<a href="/alle-jobber">Alle jobber</a>'
            '<a href="/om-oss">Om oss</a>'
            "</nav></body></html>"
        )
        self.assertEqual(extract_role_cards(html, BOARD), [])

    def test_a_link_that_names_a_role_is_a_role_card(self):
        html = (
            "<html><body>"
            "<h1>Ledige stillinger</h1>"
            '<a href="/stilling/12345">Senior utvikler</a>'
            "</body></html>"
        )
        cards = extract_role_cards(html, BOARD)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["title"], "Senior utvikler")
        self.assertEqual(cards[0]["url"], "https://www.jobbnorge.no/stilling/12345")


if __name__ == "__main__":
    unittest.main()
