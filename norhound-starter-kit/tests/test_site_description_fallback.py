"""A company page with no <title> and no meta description still describes the company.

Six of the shipped 1,000 companies have an exact-identity site whose title and
meta description are both empty — a server-rendered page with no head metadata.
`extract_site_description.py` built its website-description claim from
`title — description`, so for those six the claim was empty and the company
lost its website-family fact even though the page was captured, verified and
belonged to the company.

The page's own extracted main text is the company's own words, so it is the
right fallback. It is not new information and it is not fabricated: it comes
from the bytes already captured and hashed for that page.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.extract_site_description import observations_for_profile  # noqa: E402
from scripts.extract_registry_proved_site_observations import extract_observation  # noqa: E402

ORG = "911696223"
DIGEST = "e" * 64


def _profile(*, title: str = "", description: str = "", excerpt: str = "Vi bygger ting i Bergen.") -> dict:
    return {
        "organisation_number": ORG,
        "name": "COMMUNICARE AS",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://communicare.as/",
                "retrieved_at": "2026-11-06T10:00:00Z",
                "content_sha256": DIGEST,
                "value": {
                    "final_url": "https://communicare.as/",
                    "registered_domain": "communicare.as",
                    "title": title,
                    "description": description,
                    "main_text_excerpt": excerpt,
                    "content_sha256": DIGEST,
                    "identity_assessment": {
                        "status": "exact",
                        "score": 0.95,
                        "publishable": True,
                    },
                },
            }
        },
    }


class WebsiteDescriptionTests(unittest.TestCase):
    def test_a_page_with_a_title_publishes_the_title(self) -> None:
        rows = observations_for_profile(_profile(title="Communicare"))
        website_rows = [r for r in rows if r["signal_type"] == "website_description"]
        self.assertEqual(len(website_rows), 1)
        self.assertIn("Communicare", website_rows[0]["evidence_span"])

    def test_a_page_with_no_title_falls_back_to_the_main_text(self) -> None:
        rows = observations_for_profile(_profile())
        website_rows = [r for r in rows if r["signal_type"] == "website_description"]
        self.assertEqual(len(website_rows), 1)
        self.assertIn("Vi bygger ting i Bergen.", website_rows[0]["evidence_span"])

    def test_a_page_with_neither_title_nor_text_publishes_nothing(self) -> None:
        rows = observations_for_profile(_profile(excerpt=""))
        self.assertEqual([r for r in rows if r["signal_type"] == "website_description"], [])

    def test_the_fallback_keeps_the_page_digest(self) -> None:
        rows = observations_for_profile(_profile())
        website_rows = [r for r in rows if r["signal_type"] == "website_description"]
        self.assertEqual(website_rows[0]["content_sha256"], DIGEST)


class RegistrySiteDescriptionTests(unittest.TestCase):
    """The registry-proved website connector must not drop a titleless page either."""

    def _profile(self, *, title: str = "", description: str = "",
                 excerpt: str = "Communicare bygger ting i Bergen.") -> dict:
        profile = _profile(title=title, description=description, excerpt=excerpt)
        profile["website"] = "communicare.as"
        profile["evidence"]["registry"] = {
            "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/" + ORG,
            "retrieved_at": "2026-11-06T09:00:00Z",
            "value": {"hjemmeside": "communicare.as"},
        }
        return profile

    def test_a_titleless_page_still_produces_a_description(self) -> None:
        observation, status = extract_observation(self._profile())
        self.assertIsNotNone(observation)
        self.assertEqual(status["status"], "accepted")
        assert observation is not None
        self.assertIn("Communicare bygger ting i Bergen.", observation["metrics"]["description"])

    def test_a_page_with_no_text_at_all_is_skipped(self) -> None:
        observation, status = extract_observation(self._profile(excerpt=""))
        self.assertIsNone(observation)
        self.assertIn(status["reason"], {"no_extractable_text", "identity_not_corroborated"})
