from __future__ import annotations

import unittest

from scripts.extract_substructure import observations_for_profile


def _profile():
    return {
        "organisation_number": "818751362",
        "evidence": {
            "registry": {
                "status": "available",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/818751362",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "content_sha256": "a" * 64,
                "value": {"navn": "AGIO FORVALTNING AS"},
            },
            "locations": {
                "status": "available",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/underenheter?overordnetEnhet=818751362&size=1000",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "content_sha256": "b" * 64,
                "value": {"locations": [
                    {"organisation_number": "924066245", "name": "HAUGE BYGÅRD",
                     "address": {"kommune": "TROMSØ", "kommunenummer": "5501", "adresse": "TESTVEIEN 1"},
                     "industry": {"kode": "68.209", "beskrivelse": "Utleie av egen fast eiendom"}, "employees": None},
                ]},
            },
            "group": {
                "status": "available",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/konsernstruktur/920053548",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "content_sha256": "c" * 64,
                "value": {
                    "organisasjonsnummer": "920053548",
                    "navn": "ONH EDUCATION AS",
                    "children": [{
                        "organisasjonsnummer": "812840622",
                        "navn": "OSLO ANALYTICA AS",
                        "parentOrganisasjonsnummer": "920053548",
                        "grunnlag": "51,0%",
                        "knytningsform": {"kode": "KDAT", "beskrivelse": "Konsern datter"},
                    }],
                },
            },
        },
    }


class SubstructureTests(unittest.TestCase):
    def test_subunit_emitted(self):
        obs = observations_for_profile(_profile())
        subunits = [o for o in obs if o["signal_type"] == "subunit"]
        self.assertEqual(len(subunits), 1)
        self.assertEqual(subunits[0]["evidence_span"], "HAUGE BYGÅRD")
        self.assertTrue(subunits[0]["exact_entity"])

    def test_group_child_emitted(self):
        obs = observations_for_profile(_profile())
        children = [o for o in obs if o["signal_type"] == "group_child"]
        self.assertEqual(children[0]["evidence_span"], "OSLO ANALYTICA AS")
        self.assertTrue(children[0]["exact_entity"])

    def test_missing_modules_emit_nothing(self):
        profile = _profile()
        del profile["evidence"]["locations"]
        del profile["evidence"]["group"]
        self.assertEqual(observations_for_profile(profile), [])

    def test_empty_subunits_emit_nothing(self):
        profile = _profile()
        profile["evidence"]["locations"]["value"] = {"locations": []}
        obs = observations_for_profile(profile)
        self.assertEqual([o for o in obs if o["signal_type"] == "subunit"], [])

    def test_output_is_deterministic(self):
        self.assertEqual(observations_for_profile(_profile()), observations_for_profile(_profile()))


if __name__ == "__main__":
    unittest.main()