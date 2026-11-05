"""Registry-proved website observations.

BRREG (the official registry) states each company's website domain. When the
crawled site lives on exactly that domain *and* the page corroborates the
company (its organisation number, or a legal-name token), the identity is
official-grade: the registry resolves the domain to the legal entity and the
page confirms it. The verifier re-derives both conditions from the frozen
profile — it never trusts what the observation says about itself.
"""

from __future__ import annotations

import unittest

from scripts.extract_registry_proved_site_observations import extract_observation, normalise_host
from scripts.verify_and_label_observations import verify as verify_observation

ORG = "916498721"
OTHER_ORG = "999999999"
REGISTRY_URL = "https://data.brreg.no/enhetsregisteret/api/enheter/916498721"
SITE_URL = "https://clemenskraft.no/"
DIGEST = "c" * 64


def _profile(
    *,
    name: str = "FJÆRLAND KRAFT AS",
    registry_website: str = "clemenskraft.no",
    site_url: str = SITE_URL,
    site_domain: str = "clemenskraft.no",
    title: str = "Fjærland Kraft AS",
    description: str = "Kraftverk og fornybar energi i Sogn.",
    excerpt: str = "Fjærland Kraft AS driver kraftverk i Sogn.",
    digest: str = DIGEST,
    publishable: bool = False,
    status: str = "available",
) -> dict:
    """A frozen profile whose site gate is not publishable (the 366-company case)."""
    return {
        "organisation_number": ORG,
        "name": name,
        "website": registry_website,
        "evidence": {
            "website": {
                "status": status,
                "source_url": site_url,
                "retrieved_at": "2026-09-29T10:03:57.808865Z",
                "content_sha256": digest,
                "value": {
                    "requested_url": site_url,
                    "final_url": site_url,
                    "registered_domain": site_domain,
                    "title": title,
                    "description": description,
                    "main_text_excerpt": excerpt,
                    "social_links": [],
                    "structured_organisations": [],
                    "content_sha256": digest,
                    "identity_assessment": {
                        "publishable": publishable,
                        "label": "review" if not publishable else "exact",
                        "score": 0.85 if not publishable else 1.0,
                    },
                    "pages": [{"url": site_url, "content_sha256": digest}],
                },
            },
            "registry": {
                "source_url": REGISTRY_URL,
                "retrieved_at": "2026-09-29T10:02:25.550213Z",
                "content_sha256": "d" * 64,
            },
        },
    }


def _observation(**changes):
    row, _status = extract_observation(_profile())
    row = dict(row or {})
    row.update(changes)
    return row


class RegistryProvedSiteObservationTests(unittest.TestCase):
    def test_emits_website_description_with_registry_domain_proof(self):
        row, status = extract_observation(_profile())
        self.assertIsNotNone(row)
        self.assertEqual(status["status"], "accepted")
        self.assertEqual(row["organisation_number"], ORG)
        self.assertEqual(row["platform"], "company_site")
        self.assertEqual(row["signal_type"], "website_description")
        self.assertEqual(row["source_class"], "company_site")
        self.assertEqual(row["acquisition_mode"], "permitted_public_page")
        self.assertEqual(row["rights_status"], "approved")
        self.assertEqual(row["source_url"], SITE_URL)
        self.assertEqual(row["content_sha256"], DIGEST)
        self.assertEqual(row["retrieved_at"], "2026-09-29T10:03:57.808865Z")
        proof = row["identity_proof"][0]
        self.assertEqual(proof["type"], "registry_declared_website_domain_match")
        self.assertEqual(proof["matched_organisation_number"], ORG)
        self.assertEqual(proof["source_url"], REGISTRY_URL)
        self.assertTrue(proof["retrieved_at"])
        self.assertEqual(row["id"], f"registry-site-{ORG}-{DIGEST[:16]}")

    def test_skips_when_registry_domain_differs_from_the_crawled_site(self):
        row, status = extract_observation(_profile(registry_website="other.no"))
        self.assertIsNone(row)
        self.assertEqual(status["reason"], "registry_domain_mismatch")

    def test_skips_when_the_page_does_not_corroborate_the_company(self):
        row, status = extract_observation(
            _profile(
                name="FJÆRLAND KRAFT AS",
                title="Parkert domene",
                description="Domenet er til salgs.",
                excerpt="This domain is for sale.",
            )
        )
        self.assertIsNone(row)
        self.assertEqual(status["reason"], "identity_not_corroborated")

    def test_accepts_the_organisation_number_as_page_corroboration(self):
        row, status = extract_observation(
            _profile(
                name="FJÆRLAND KRAFT AS",
                title="Parkert domene",
                description="Domenet er til salgs.",
                excerpt=f"Organisasjonsnummer {ORG}.",
            )
        )
        self.assertIsNotNone(row)
        self.assertEqual(status["status"], "accepted")

    def test_skips_without_website_evidence_or_digest(self):
        self.assertIsNone(extract_observation(_profile(status="blocked"))[0])
        self.assertIsNone(extract_observation(_profile(digest=""))[0])

    def test_normalise_host_strips_scheme_www_and_port(self):
        self.assertEqual(normalise_host("https://www.Example.no/path"), "example.no")
        self.assertEqual(normalise_host("example.no:443"), "example.no")
        self.assertEqual(normalise_host(""), "")


class RegistryProvedSiteVerifierTests(unittest.TestCase):
    def test_accepts_a_registry_proved_row_even_when_the_site_gate_is_not_publishable(self):
        row = _observation()
        label = verify_observation(row, _profile())
        self.assertEqual(label["exact_entity"], 1)
        self.assertTrue(label["checks"]["registry_domain_proof_consistent"])

    def test_rejects_a_registry_proof_that_names_another_organisation(self):
        row = _observation()
        row["identity_proof"][0]["matched_organisation_number"] = OTHER_ORG
        label = verify_observation(row, _profile())
        self.assertEqual(label["exact_entity"], 0)

    def test_rejects_a_row_whose_source_host_differs_from_the_registry_domain(self):
        row = _observation(source_url="https://elsewhere.no/")
        label = verify_observation(row, _profile())
        self.assertEqual(label["exact_entity"], 0)

    def test_rejects_a_website_row_without_the_registry_proof_when_the_gate_is_not_publishable(self):
        row = _observation(identity_proof=[{"type": "website_identity_gate", "score": 0.85}])
        label = verify_observation(row, _profile())
        self.assertEqual(label["exact_entity"], 0)

    def test_rejects_a_registry_proved_row_without_a_digest(self):
        row = _observation(content_sha256="")
        label = verify_observation(row, _profile())
        self.assertEqual(label["exact_entity"], 0)


if __name__ == "__main__":
    unittest.main()
