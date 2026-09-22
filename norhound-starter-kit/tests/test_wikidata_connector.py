from __future__ import annotations

import unittest

from scripts.run_wikidata_connector import collect, prime_index
from scripts.verify_and_label_observations import verify as verify_observation

ORG = "923609016"
SEARCH_PAYLOAD = {"query": {"search": [{"title": "Q1776022"}]}}
ENTITY_PAYLOAD = {
    "entities": {
        "Q1776022": {
            "labels": {"nb": {"value": "Equinor"}},
            "claims": {
                "P2333": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": ORG}}}],
                "P856": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": "https://www.equinor.com"}}}],
                "P4264": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": "equinor"}}}],
            },
            "sitelinks": {"enwiki": {"title": "Equinor"}},
        }
    }
}


def _fake_fetch(url: str) -> dict:
    if "list=search" in url:
        return SEARCH_PAYLOAD
    return ENTITY_PAYLOAD


class WikidataConnectorTests(unittest.TestCase):
    def test_prime_parses_entity_values_and_handles(self):
        index = prime_index([ORG], _fake_fetch, retrieved_at="2026-09-22T00:00:00Z")
        entry = index[ORG]
        self.assertEqual(entry["qid"], "Q1776022")
        self.assertEqual(entry["values"]["wikidata.website"], "https://www.equinor.com")
        self.assertEqual(entry["handles"][0]["platform"], "linkedin")
        self.assertEqual(entry["wikipedia"][0]["lang"], "en")

    def test_prime_with_no_hits_is_empty(self):
        index = prime_index([ORG], lambda url: {"query": {"search": []}}, retrieved_at="2026-09-22T00:00:00Z")
        self.assertEqual(index, {})

    def test_collect_emits_exact_entity_observations(self):
        index = prime_index([ORG], _fake_fetch, retrieved_at="2026-09-22T00:00:00Z")
        obs = collect(ORG, index[ORG])
        by_signal = {(o["platform"], o["signal_type"]) for o in obs}
        self.assertIn(("wikidata", "company_profile"), by_signal)
        self.assertIn(("wikipedia", "company_profile"), by_signal)
        self.assertIn(("linkedin", "profile_handle"), by_signal)
        self.assertTrue(all(o["exact_entity"] for o in obs))
        self.assertTrue(all(o["identity_proof"] for o in obs))

    def test_collect_is_deterministic(self):
        index = prime_index([ORG], _fake_fetch, retrieved_at="2026-09-22T00:00:00Z")
        self.assertEqual(collect(ORG, index[ORG]), collect(ORG, index[ORG]))

    def test_verify_accepts_wikidata_proof_as_exact_entity(self):
        index = prime_index([ORG], _fake_fetch, retrieved_at="2026-09-22T00:00:00Z")
        obs = collect(ORG, index[ORG])[0]
        profile = {
            "organisation_number": ORG,
            "evidence": {"website": {"status": "available", "source_url": "https://www.equinor.com", "value": {"identity_assessment": {"publishable": True}}}},
        }
        label = verify_observation(obs, profile)
        self.assertEqual(label["exact_entity"], 1)
        self.assertEqual(label["metric_correct"], 1)


if __name__ == "__main__":
    unittest.main()
