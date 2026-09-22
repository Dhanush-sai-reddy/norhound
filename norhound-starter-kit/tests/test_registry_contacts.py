from __future__ import annotations

import unittest

from scripts.extract_registry_contacts import observations_for_profile


def _profile(email="post@sandneselektriske.no", phone="51 68 57 00"):
    return {
        "organisation_number": "810034882",
        "evidence": {
            "registry": {
                "status": "available",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "content_sha256": "c" * 64,
                "value": {"epostadresse": email, "telefon": phone, "mobil": ""},
            },
            "website": {
                "status": "available",
                "source_url": "https://example.test/",
                "retrieved_at": "2026-09-14T00:00:00Z",
                "value": {"identity_assessment": {"publishable": True}},
            },
        },
    }


class RegistryContactsTests(unittest.TestCase):
    def test_email_and_phone_emitted(self):
        obs = observations_for_profile(_profile())
        by_signal = {o["signal_type"]: o for o in obs}
        self.assertEqual(by_signal["contact_email"]["evidence_span"], "post@sandneselektriske.no")
        self.assertEqual(by_signal["contact_phone"]["evidence_span"], "51 68 57 00")
        self.assertTrue(all(o["exact_entity"] for o in obs))

    def test_missing_contacts_emit_nothing(self):
        self.assertEqual(observations_for_profile(_profile(email="", phone="")), [])

    def test_no_registry_emit_nothing(self):
        profile = _profile()
        del profile["evidence"]["registry"]
        self.assertEqual(observations_for_profile(profile), [])

    def test_output_is_deterministic(self):
        self.assertEqual(observations_for_profile(_profile()), observations_for_profile(_profile()))


if __name__ == "__main__":
    unittest.main()
