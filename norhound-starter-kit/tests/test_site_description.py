from __future__ import annotations

import unittest

from scripts.extract_site_description import observations_for_profile


def _profile(title="Agio Forvaltning", description="Forretningsfører for sameier.", orgs=None, publishable=True):
    return {
        "organisation_number": "818751362",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://example.test/",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "content_sha256": "d" * 64,
                "value": {
                    "identity_assessment": {"publishable": publishable},
                    "title": title,
                    "description": description,
                    "structured_organisations": orgs if orgs is not None else [{"name": "Agio Forvaltning", "url": "https://example.test/"}],
                },
            }
        },
    }


class SiteDescriptionTests(unittest.TestCase):
    def test_description_and_brand_emitted(self):
        obs = observations_for_profile(_profile())
        by_signal = {o["signal_type"]: o for o in obs}
        self.assertIn("Forretningsfører", by_signal["website_description"]["evidence_span"])
        self.assertEqual(by_signal["public_brand"]["evidence_span"], "Agio Forvaltning")
        self.assertTrue(all(o["exact_entity"] for o in obs))

    def test_missing_text_emits_nothing(self):
        self.assertEqual(observations_for_profile(_profile(title="", description="", orgs=[])), [])

    def test_ungated_site_emits_nothing(self):
        self.assertEqual(observations_for_profile(_profile(publishable=False)), [])

    def test_output_is_deterministic(self):
        self.assertEqual(observations_for_profile(_profile()), observations_for_profile(_profile()))


if __name__ == "__main__":
    unittest.main()
