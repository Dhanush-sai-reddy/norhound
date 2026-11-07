from __future__ import annotations

import unittest

from scripts.extract_registry_workforce import observations_for_profile
from src.norway_company_agent.external_footprint import publishable_observation


def _profile(employees="47", registered="2026-05-12"):
    return {
        "organisation_number": "986678298",
        "evidence": {
            "registry": {
                "status": "available",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "content_sha256": "a" * 64,
                "value": {
                    "antallAnsatte": "45",
                    "registreringsdatoAntallAnsatteEnhetsregisteret": registered,
                    "registreringsdatoantallansatteNAVAaregisteret": "",
                },
            },
            "registry_live": {
                "status": "available",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/986678298",
                "retrieved_at": "2026-09-29T10:03:05.141945Z",
                "content_sha256": "b" * 64,
                "value": {"organisation_number": "986678298", "employees": employees},
            },
        },
    }


class RegistryWorkforceTests(unittest.TestCase):
    def test_count_emitted_from_live_registry_record(self):
        obs = observations_for_profile(_profile())
        self.assertEqual(len(obs), 1)
        row = obs[0]
        self.assertEqual(row["signal_type"], "workforce_snapshot")
        self.assertEqual(row["platform"], "brreg")
        self.assertEqual(row["source_url"], "https://data.brreg.no/enhetsregisteret/api/enheter/986678298")
        self.assertEqual(row["content_sha256"], "b" * 64)
        self.assertEqual(row["metrics"]["workforce_value"], 47)
        self.assertEqual(row["evidence_span"], '"employees": 47')

    def test_observed_at_uses_brreg_registration_date(self):
        row = observations_for_profile(_profile())[0]
        self.assertEqual(row["observed_at"], "2026-05-12")
        self.assertEqual(row["effective_at"], "2026-05-12")

    def test_missing_registration_date_omits_observed_at(self):
        row = observations_for_profile(_profile(registered=""))[0]
        self.assertNotIn("observed_at", row)

    def test_missing_count_emits_nothing(self):
        self.assertEqual(observations_for_profile(_profile(employees="")), [])

    def test_missing_live_record_emits_nothing(self):
        profile = _profile()
        del profile["evidence"]["registry_live"]
        self.assertEqual(observations_for_profile(profile), [])

    def test_row_is_publishable(self):
        self.assertTrue(publishable_observation(observations_for_profile(_profile())[0]))

    def test_output_is_deterministic(self):
        self.assertEqual(observations_for_profile(_profile()), observations_for_profile(_profile()))


if __name__ == "__main__":
    unittest.main()
