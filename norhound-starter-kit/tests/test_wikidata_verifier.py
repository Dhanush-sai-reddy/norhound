"""Verifier tests for Wikidata P2333 handles as exact-entity social profiles.

A Wikidata row is trusted only when its identity proof names the profile
organisation number, its QID is well formed and consistent with the entity
URL, and the Wikidata entity JSON was hashed. A handle proved that way is an
exact-entity social profile even without a company-site cross-link; a handle
proved only by the website still needs the identity gate's social_links.
"""

from __future__ import annotations

import unittest

from scripts.verify_and_label_observations import verify as verify_observation

ORG = "923609016"
OTHER_ORG = "999999999"
QID = "Q1776022"
ENTITY_URL = f"https://www.wikidata.org/wiki/{QID}"
OTHER_ENTITY_URL = "https://www.wikidata.org/wiki/Q999999"
HANDLE_URL = "https://www.linkedin.com/company/equinor"
SITE_SOCIAL_URL = "https://www.facebook.com/equinor"
SITE_URL = "https://www.equinor.com/"


def _profile(*, social_links=(SITE_SOCIAL_URL,)):
    """Frozen profile evidence; the gate only observed SITE_SOCIAL_URL."""
    return {
        "organisation_number": ORG,
        "name": "Equinor ASA",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": SITE_URL,
                "value": {
                    "final_url": SITE_URL,
                    "content_sha256": "b" * 64,
                    "identity_assessment": {"publishable": True, "label": "exact", "score": 1.0},
                    "social_links": [{"url": url} for url in social_links],
                },
            }
        },
    }


def _wikidata_proof(matched_organisation_number=ORG, **extra):
    proof = {
        "type": "organisation_number_on_wikidata",
        "source": "wikidata.org",
        "source_class": "open_knowledge_base",
        "explanation": (
            f"Wikidata entity {QID} carries property P2333 (Norwegian organisation number) "
            "equal to the profile organisation number; no name matching involved."
        ),
    }
    if matched_organisation_number is not None:
        proof["matched_organisation_number"] = matched_organisation_number
    proof.update(extra)
    return proof


def _wikidata_handle(**changes):
    """A Wikidata P2333 handle row whose handle URL is absent from social_links."""
    obs = {
        "id": f"wikidata-{ORG}-handle-linkedin-0",
        "organisation_number": ORG,
        "platform": "linkedin",
        "signal_type": "profile_handle",
        "source_url": ENTITY_URL,
        "retrieved_at": "2026-09-22T00:00:00Z",
        "content_sha256": "a" * 64,
        "exact_entity": True,
        "identity_proof": [_wikidata_proof()],
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "public_mention",
        "strategy": "wikidata_p2333_orgnr_match",
        "evidence_span": HANDLE_URL,
        "metrics": {"platform": "linkedin", "url": HANDLE_URL, "property": "P4264", "qid": QID},
    }
    obs.update(changes)
    return obs


def _site_handle(handle_url=HANDLE_URL, **changes):
    """A company-site handle row proved by the website identity gate only."""
    obs = {
        "id": "site-handle-1",
        "organisation_number": ORG,
        "platform": "linkedin",
        "signal_type": "profile_handle",
        "source_url": f"{SITE_URL}kontakt",
        "retrieved_at": "2026-09-22T00:00:00Z",
        "content_sha256": "b" * 64,
        "exact_entity": True,
        "identity_proof": [{"type": "website_identity_assessment", "value": "exact"}],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_social",
        "evidence_span": handle_url,
        "metrics": {"platform": "linkedin", "url": handle_url},
    }
    obs.update(changes)
    return obs


class WikidataHandleVerifierTests(unittest.TestCase):
    def test_p2333_handle_is_exact_entity_without_company_site_social_link(self):
        profile = _profile()
        gate_socials = [s["url"] for s in profile["evidence"]["website"]["value"]["social_links"]]
        self.assertNotIn(HANDLE_URL, gate_socials)
        label = verify_observation(_wikidata_handle(), profile)
        self.assertEqual(label["exact_entity"], 1)
        self.assertEqual(label["metric_correct"], 1)
        self.assertTrue(label["checks"]["wikidata_proof_consistent"])
        self.assertFalse(label["checks"]["handle_present_in_gate_socials"])

    def test_p2333_handle_rejected_when_proof_organisation_number_differs(self):
        obs = _wikidata_handle()
        obs["identity_proof"] = [_wikidata_proof(matched_organisation_number=OTHER_ORG)]
        label = verify_observation(obs, _profile())
        self.assertEqual(label["exact_entity"], 0)
        self.assertFalse(label["checks"]["wikidata_proof_consistent"])

    def test_p2333_handle_rejected_when_qid_is_malformed(self):
        obs = _wikidata_handle()
        obs["metrics"] = {**obs["metrics"], "qid": "not-a-qid"}
        label = verify_observation(obs, _profile())
        self.assertEqual(label["exact_entity"], 0)
        self.assertFalse(label["checks"]["wikidata_proof_consistent"])

    def test_p2333_handle_rejected_when_entity_url_qid_differs_from_metrics(self):
        obs = _wikidata_handle(source_url=OTHER_ENTITY_URL)
        label = verify_observation(obs, _profile())
        self.assertEqual(label["exact_entity"], 0)
        self.assertFalse(label["checks"]["wikidata_proof_consistent"])

    def test_p2333_handle_rejected_when_content_digest_missing(self):
        obs = _wikidata_handle()
        obs.pop("content_sha256")
        label = verify_observation(obs, _profile())
        self.assertEqual(label["exact_entity"], 0)
        self.assertFalse(label["checks"]["wikidata_proof_consistent"])

    def test_p2333_proof_value_fallback_used_when_matched_number_absent(self):
        obs = _wikidata_handle()
        obs["identity_proof"] = [{"type": "organisation_number_on_wikidata", "value": ORG}]
        label = verify_observation(obs, _profile())
        self.assertEqual(label["exact_entity"], 1)
        self.assertTrue(label["checks"]["wikidata_proof_consistent"])

    def test_p2333_proof_value_fallback_ignored_when_not_nine_digits(self):
        obs = _wikidata_handle()
        obs["identity_proof"] = [{"type": "organisation_number_on_wikidata", "value": "Equinor ASA"}]
        label = verify_observation(obs, _profile())
        self.assertEqual(label["exact_entity"], 0)
        self.assertFalse(label["checks"]["wikidata_proof_consistent"])

    def test_wikipedia_article_row_with_related_qid_stays_trusted(self):
        obs = {
            "id": f"wikidata-{ORG}-wikipedia-no",
            "organisation_number": ORG,
            "platform": "wikipedia",
            "signal_type": "company_profile",
            "source_url": "https://no.wikipedia.org/wiki/Equinor",
            "retrieved_at": "2026-09-22T00:00:00Z",
            "content_sha256": "a" * 64,
            "exact_entity": True,
            "identity_proof": [_wikidata_proof()],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "public_mention",
            "strategy": "wikidata_p2333_orgnr_match",
            "evidence_span": f"Wikipedia article linked from Wikidata entity {QID} (Equinor)",
            "metrics": {"language": "no", "qid": QID},
        }
        label = verify_observation(obs, _profile())
        self.assertEqual(label["exact_entity"], 1)
        self.assertEqual(label["metric_correct"], 1)
        self.assertTrue(label["checks"]["wikidata_proof_consistent"])

    def test_website_handle_missing_from_social_links_without_trusted_proof_is_rejected(self):
        label = verify_observation(_site_handle(), _profile())
        self.assertEqual(label["exact_entity"], 0)
        self.assertFalse(label["checks"]["handle_present_in_gate_socials"])
        self.assertFalse(label["checks"]["wikidata_identity_proof"])

    def test_website_handle_present_in_social_links_stays_exact_entity(self):
        label = verify_observation(_site_handle(handle_url=SITE_SOCIAL_URL), _profile())
        self.assertEqual(label["exact_entity"], 1)
        self.assertTrue(label["checks"]["handle_present_in_gate_socials"])


if __name__ == "__main__":
    unittest.main()
