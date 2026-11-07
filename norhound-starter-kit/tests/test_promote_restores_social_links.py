"""Registry-site promotion must restore the social links the gate withheld.

`apply_website_identity_gate` empties `social_links` for a site whose legal
name never appears in its own title, and it keeps the per-link verdicts in
`social_link_assessments`. When the register-declared-domain proof later
promotes that site, the link verdicts are still there and still say the handle
is exact — but `social_links` stays empty, so the handle is never published.

Twenty-three batch companies lost thirty-seven exact social handles this way.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.promote_registry_declared_sites import promote  # noqa: E402

ORG = "986537872"
DOMAIN = "outdoor.no"


def _profile() -> dict:
    return {
        "organisation_number": ORG,
        "name": "OUTDOOR AS",
        "website": DOMAIN,
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://outdoor.no/",
                "content_sha256": "b" * 64,
                "value": {
                    "final_url": "https://outdoor.no/",
                    "registered_domain": DOMAIN,
                    "title": "Outdoor",
                    "main_text_excerpt": "Outdoor AS selger friluftsutstyr.",
                    "identity_assessment": {
                        "status": "related_or_uncertain",
                        "score": 0.3,
                        "publishable": False,
                        "matched_tokens": ["outdoor"],
                    },
                    "social_links": [],
                    "social_link_assessments": [
                        {
                            "platform": "instagram",
                            "url": "https://instagram.com/outdoor_as",
                            "identity_score": 0.98,
                            "publishable": True,
                        },
                        {
                            "platform": "facebook",
                            "url": "https://facebook.com/someone-else",
                            "identity_score": 0.3,
                            "publishable": False,
                        },
                    ],
                },
            },
            "registry": {"value": {"hjemmeside": DOMAIN}},
        },
    }


class RestoresSocialLinksTests(unittest.TestCase):
    def test_promotion_restores_the_exact_social_handles(self) -> None:
        profile = _profile()
        promote(profile, {DOMAIN: ORG}, "2026-11-07")
        value = profile["evidence"]["website"]["value"]
        self.assertEqual(
            value["social_links"],
            [{"platform": "instagram", "url": "https://instagram.com/outdoor_as"}],
        )

    def test_promotion_does_not_restore_a_handle_the_link_gate_rejected(self) -> None:
        profile = _profile()
        promote(profile, {DOMAIN: ORG}, "2026-11-07")
        value = profile["evidence"]["website"]["value"]
        urls = {link["url"] for link in value["social_links"]}
        self.assertNotIn("https://facebook.com/someone-else", urls)

    def test_promotion_without_link_assessments_leaves_links_untouched(self) -> None:
        profile = _profile()
        profile["evidence"]["website"]["value"].pop("social_link_assessments")
        promote(profile, {DOMAIN: ORG}, "2026-11-07")
        value = profile["evidence"]["website"]["value"]
        self.assertEqual(value["social_links"], [])


if __name__ == "__main__":
    unittest.main()
