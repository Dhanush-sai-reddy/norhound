from __future__ import annotations

import unittest

from scripts.run_registry_updates_connector import collect, events_url


def _payload():
    return {"_embedded": {"oppdaterteEnheter": [
        {"oppdateringsid": 9, "dato": "2026-09-10T06:03:29.443Z", "organisasjonsnummer": "810034882", "endringstype": "Endring",
         "_links": {"enhet": {"href": "https://data.brreg.no/enhetsregisteret/api/enheter/810034882"}}},
        {"oppdateringsid": 3, "dato": "2026-08-01T06:03:29.443Z", "organisasjonsnummer": "810034882", "endringstype": "Ukjent",
         "_links": {"enhet": {"href": "https://data.brreg.no/enhetsregisteret/api/enheter/810034882"}}},
        {"oppdateringsid": 1, "dato": "2026-07-01T06:03:29.443Z", "organisasjonsnummer": "999999999", "endringstype": "Endring",
         "_links": {"enhet": {"href": "https://data.brreg.no/enhetsregisteret/api/enheter/999999999"}}},
    ]}}


class RegistryUpdatesTests(unittest.TestCase):
    def test_url_queries_single_org(self):
        url = events_url("810034882")
        self.assertIn("organisasjonsnummer=810034882", url)
        self.assertIn("data.brreg.no", url)

    def test_collect_emits_dated_observations_newest_first(self):
        obs = collect("810034882", _payload(), retrieved_at="2026-09-22T00:00:00Z")
        self.assertEqual(len(obs), 2)
        self.assertEqual(obs[0]["observed_at"], "2026-09-10")
        self.assertEqual(obs[0]["signal_type"], "registry_update")
        self.assertTrue(all(o["exact_entity"] for o in obs))

    def test_other_org_events_ignored(self):
        obs = collect("810034882", _payload(), retrieved_at="2026-09-22T00:00:00Z")
        self.assertTrue(all(o["organisation_number"] == "810034882" for o in obs))

    def test_empty_payload_emits_nothing(self):
        self.assertEqual(collect("810034882", {}, retrieved_at="2026-09-22T00:00:00Z"), [])

    def test_output_is_deterministic(self):
        first = collect("810034882", _payload(), retrieved_at="2026-09-22T00:00:00Z")
        self.assertEqual(first, collect("810034882", _payload(), retrieved_at="2026-09-22T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
