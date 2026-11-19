"""A register-declared domain is a second platform for directory-only companies.

374 of the 1,000 companies publish exactly one source outside the register: the
Purehelp/Fagfolkguiden directory. 371 of them state a website domain on that
directory page, and 175 of those domains are declared by the *same* organisation
number in the register's sole-declarer index (82,398 domains, each declared by
exactly one entity, 0 mismatches among the 371).

A live probe fetched 72 of those 175; 37 named the legal company and were not
parked. Those 37 can earn a genuine second external platform — but only under a
proof the verifier re-derives: the register declares the domain for this
organisation, no other organisation declares it, and the page body names the
company. Without the index the proof is not trusted.

These tests pin the connector's four acceptance rules and the verifier's
fail-safe behaviour.
"""

from __future__ import annotations

import unittest

from scripts.extract_register_sole_declarer_sites import (
    load_index,
    site_observation,
    sole_declarer_targets,
)
from scripts.verify_and_label_observations import verify

ORG = "123456789"
NAME = "Acme AS"
SITE = "https://acme.no/"
INDEX = {"acme.no": ORG}


def _profile(website=SITE, org=ORG, name=NAME):
    return {
        "organisation_number": org,
        "name": name,
        "website": website,
        "evidence": {"website": {"status": "not_available", "value": {}}},
    }


def _site_row(org=ORG):
    return {
        "organisation_number": org,
        "platform": "company_directory",
        "signal_type": "profile_metrics",
        "source_url": "https://purehelp.no/company/NO/" + org,
        "metrics": {"website_domain": "acme.no"},
    }


GOOD_BODY = """
<html><head><title>Acme | Norwegian engineering</title></head>
<body><h1>Acme AS</h1><p>We build bridges and industrial systems in Norway.</p></body></html>
"""


class SoleDeclarerConnector(unittest.TestCase):
    def test_sole_declarer_site_naming_the_company_publishes(self):
        profile = _profile()
        row = site_observation(profile, SITE, GOOD_BODY, GOOD_BODY.encode("utf-8"), "acme.no")
        self.assertIsNotNone(row)
        self.assertEqual(row["signal_type"], "website_description")
        self.assertEqual(row["platform"], "company_site")
        self.assertEqual(row["organisation_number"], ORG)
        self.assertEqual(row["identity_proof"][0]["type"], "registry_sole_declarer_domain_match")
        self.assertEqual(row["identity_proof"][0]["matched_organisation_number"], ORG)
        self.assertIn("Acme AS", row["metrics"]["body_excerpt"])
        self.assertLessEqual(len(row["metrics"]["body_excerpt"]), 2000)

    def test_parked_domain_is_rejected(self):
        profile = _profile()
        body = "<html><head><title>www.acme.no is parked</title></head><body>Parked at Loopia</body></html>"
        self.assertIsNone(site_observation(profile, SITE, body, body.encode("utf-8"), "acme.no"))

    def test_domain_declared_by_another_organisation_is_rejected(self):
        profile = _profile()
        rows = sole_declarer_targets([profile], {"acme.no": "999999999"}, [profile["organisation_number"]])
        self.assertEqual(rows, [])

    def test_site_without_legal_name_match_is_rejected(self):
        profile = _profile()
        body = "<html><body><h1>Other Company AS</h1><p>We do other things.</p></body></html>"
        self.assertIsNone(site_observation(profile, SITE, body, body.encode("utf-8"), "acme.no"))

    def test_one_token_of_a_two_token_name_is_not_enough(self):
        """A live probe matched 'media' alone for EARTHREND MEDIA AS on a page
        titled AWESOMEZ.NET. One generic token is not identity proof."""
        profile = _profile(website="https://earthrend.com/", org="999065902", name="Earthrend Media AS")
        body = "<html><body><h1>AWESOMEZ.NET</h1><p>media and entertainment</p></body></html>"
        self.assertIsNone(site_observation(profile, "https://earthrend.com/", body, body.encode("utf-8"), "earthrend.com"))

    def test_load_index_reads_the_gzip_jsonl(self):
        import gzip
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps({"domain": "acme.no", "organisation_number": ORG}) + "\n")
                handle.write(json.dumps({"domain": "shared.no", "organisation_number": "1"}) + "\n")
                handle.write(json.dumps({"domain": "shared.no", "organisation_number": "2"}) + "\n")
            index = load_index(path)
        self.assertEqual(index, {"acme.no": ORG})
        self.assertNotIn("shared.no", index)


class GLEIFVerifier(unittest.TestCase):
    """GLEIF's Brønnøysund-validated organisation number is an official proof.

    The connector emitted 13 such rows and the verifier rejected all 13 because
    it did not recognize the proof type.
    """

    def test_gleif_validated_org_number_is_an_official_api_proof(self):
        from scripts.run_gleif_connector import observation_for

        row = observation_for("916659261", {
            "lei": "636700LNU9OML0MMGJ23",
            "legal_name": "MALLING & CO INVESTMENT MANAGEMENT AS",
            "registration": {"validatedAs": "916 659 261", "registrationAuthority": {"id": "RA000472"}},
        })
        profile = _profile(org="916659261", name="MALLING & CO INVESTMENT MANAGEMENT AS")
        result = verify(row, profile)
        self.assertEqual(result["exact_entity"], 1)
        self.assertEqual(result["metric_correct"], 1)


class SoleDeclarerVerifier(unittest.TestCase):
    def _observation(self):
        raw = GOOD_BODY.encode("utf-8")
        row = site_observation(_profile(), SITE, GOOD_BODY, raw, "acme.no")
        self.assertIsNotNone(row)
        return row

    def test_verifier_trusts_the_sole_declarer_proof_only_with_the_index(self):
        row = self._observation()
        without = verify(row, _profile())
        with_index = verify(row, _profile(), INDEX)
        self.assertEqual(without["exact_entity"], 0)
        self.assertEqual(with_index["exact_entity"], 1)
        self.assertEqual(with_index["metric_correct"], 1)

    def test_verifier_rejects_a_body_that_does_not_name_the_company(self):
        row = self._observation()
        row["metrics"]["body_excerpt"] = "Other Company AS — nothing to do with this profile"
        result = verify(row, _profile(), INDEX)
        self.assertEqual(result["exact_entity"], 0)


if __name__ == "__main__":
    unittest.main()
