"""The company-site activity connector must emit a well-formed identity proof.

The registry-domain promotion stores its proof as a single dict on the
profile's `identity_assessment.promotion_proof`. The activity connector spread
that dict with `list(...)`, which turns a dict into a list of its **keys** —
so every promoted site emitted `identity_proof: ['type', 'domain', ...]`
instead of a list of proof objects. The verifier then raised
`AttributeError: 'str' object has no attribute 'get'` and the whole
1,000-company run died after every other connector had already run.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.extract_company_site_activity import observation  # noqa: E402
from scripts.verify_and_label_observations import verify as verify_observation  # noqa: E402

ORG = "937901925"
DIGEST = "d" * 64


def _profile(*, promotion_proof: object) -> dict:
    assessment = {
        "status": "exact",
        "score": 0.95,
        "publishable": True,
    }
    if promotion_proof is not None:
        assessment["promotion_proof"] = promotion_proof
    return {
        "organisation_number": ORG,
        "name": "TESTBEDRIFF AS",
        "website": "testbedrift.no",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://testbedrift.no/",
                "retrieved_at": "2026-11-06T10:00:00Z",
                "content_sha256": DIGEST,
                "value": {
                    "final_url": "https://testbedrift.no/",
                    "registered_domain": "testbedrift.no",
                    "title": "Testbedrift",
                    "main_text_excerpt": "Testbedrift AS bygger ting.",
                    "content_sha256": DIGEST,
                    "identity_assessment": assessment,
                    "pages": [{"url": "https://testbedrift.no/", "content_sha256": DIGEST}],
                    "social_links": [],
                },
            },
            "registry": {
                "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/" + ORG,
                "retrieved_at": "2026-11-06T09:00:00Z",
            },
        },
    }


PROMOTION_PROOF = {
    "type": "registry_declared_domain_unique",
    "domain": "testbedrift.no",
    "register_field": "hjemmeside",
    "sole_declarer_in_register": True,
}


class IdentityProofShapeTests(unittest.TestCase):
    def test_promotion_proof_dict_becomes_a_list_of_proof_objects(self) -> None:
        rows = observation(_profile(promotion_proof=PROMOTION_PROOF))
        self.assertTrue(rows)
        for row in rows:
            self.assertIsInstance(row["identity_proof"], list)
            for proof in row["identity_proof"]:
                self.assertIsInstance(proof, dict)
                self.assertIn("type", proof)

    def test_the_promotion_proof_is_carried_through(self) -> None:
        rows = observation(_profile(promotion_proof=PROMOTION_PROOF))
        types = {proof.get("type") for proof in rows[0]["identity_proof"]}
        self.assertIn("registry_declared_domain_unique", types)

    def test_a_promoted_site_verifies_as_the_exact_entity(self) -> None:
        profile = _profile(promotion_proof=PROMOTION_PROOF)
        row = observation(profile)[0]
        label = verify_observation(row, profile)
        self.assertEqual(label["exact_entity"], 1)

    def test_a_site_without_promotion_still_verifies(self) -> None:
        profile = _profile(promotion_proof=None)
        row = observation(profile)[0]
        label = verify_observation(row, profile)
        self.assertEqual(label["exact_entity"], 1)


if __name__ == "__main__":
    unittest.main()
