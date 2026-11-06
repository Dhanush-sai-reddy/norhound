"""Tests for the keyless Purehelp directory connector.

Purehelp publishes one public page per Norwegian organisation number
(``https://purehelp.no/company/NO/<orgnr>``). The page is a directory profile
that mirrors the public registers (Enhetsregisteret / Foretaksregisteret /
Regnskapsregisteret). A row is published only when the page itself proves the
exact legal entity:

* the organisation number in the page payload equals the requested 9-digit
  organisation number exactly, and
* the legal name on the page equals the BRREG legal name after legal-form
  normalisation (or is a strict prefix/suffix variant of it).

The connector is keyless: no API key, no login, robots-allowed public pages
only. Every emitted row carries the source URL, the retrieval time, the
content hash of the page body and the extraction method.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.run_purehelp_directory_connector import (  # noqa: E402
    build_observations,
    company_payload,
    legal_name_matches,
    normalize_legal_name,
    run_connector,
)


ORG = "916498721"
ORG_NAME = "FJÆRLAND KRAFT AS"
PAGE_URL = f"https://purehelp.no/company/NO/{ORG}"


def nuxt_page(entries: dict) -> str:
    """Build a Nuxt SSR page with the given ``data`` payload.

    The payload uses the devalue format: every value lives in one flat array
    and objects/arrays reference their members by index.
    """
    flat: list = []

    def encode(value):
        if isinstance(value, dict):
            index = len(flat)
            flat.append(None)
            flat[index] = {key: encode(item) for key, item in value.items()}
            return index
        if isinstance(value, list):
            index = len(flat)
            flat.append(None)
            flat[index] = [encode(item) for item in value]
            return index
        index = len(flat)
        flat.append(value)
        return index

    flat.append(["ShallowReactive", 1])
    flat.append({"data": 2})
    flat.append(["ShallowReactive", 3])
    slot = len(flat)
    flat.append(None)
    flat[slot] = {key: encode(value) for key, value in entries.items()}
    body = json.dumps(flat, ensure_ascii=False)
    return (
        "<html><head><title>Purehelp</title></head><body>"
        f'<script type="application/json" data-nuxt-data="nuxt-app" id="__NUXT_DATA__">{body}</script>'
        "</body></html>"
    )


def company(overrides: dict | None = None) -> dict:
    payload = {
        "id": "d0ecb6cc-44d0-460d-af6c-16ba833ad9f6",
        "orgNumber": ORG,
        "countryCode": "NO",
        "name": ORG_NAME,
        "status": "Active",
        "isActive": True,
        "legalForm": "AS",
        "legalFormDescription": "Limited company",
        "naceCode": "35.121",
        "naceDescriptionEng": "Production of electricity from hydropower",
        "town": "OSLO",
        "zipcode": "0160",
        "municipality": "OSLO",
        "municipalityNumber": "0301",
        "county": "Oslo",
        "registrationDate": "2016-01-06T00:00:00.000Z",
        "registryStatus": "ACTIVE",
        "registryStatusDate": "2016-01-06",
        "employees": 42,
        "employeesSource": "enhetsregisteret",
        "employeesAsOf": "2026-09-18T00:00:00.000Z",
        "email": "post@example.no",
        "phone": "22 33 44 55",
        "website": "example.no",
    }
    payload.update(overrides or {})
    return payload


def page_for(payload: dict, org: str = ORG) -> str:
    return nuxt_page({f"company-NO-{org}": payload})


class PurehelpPayloadTests(unittest.TestCase):
    def test_reads_the_company_payload_of_the_requested_organisation(self):
        payload = company_payload(page_for(company()), ORG)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["orgNumber"], ORG)
        self.assertEqual(payload["name"], ORG_NAME)

    def test_returns_nothing_for_another_organisation(self):
        payload = company_payload(page_for(company()), "123456789")
        self.assertIsNone(payload)

    def test_returns_nothing_for_a_page_without_the_nuxt_payload(self):
        self.assertIsNone(company_payload("<html><body>no data</body></html>", ORG))


class PurehelpLegalNameTests(unittest.TestCase):
    def test_normalises_the_trailing_legal_form(self):
        self.assertEqual(normalize_legal_name("FJÆRLAND KRAFT AS"), "fjaerland kraft")
        self.assertEqual(normalize_legal_name("Fjaerland Kraft A/S"), "fjaerland kraft")

    def test_matches_the_same_name_in_a_different_case(self):
        self.assertTrue(legal_name_matches(ORG_NAME, "fjaerland kraft as"))

    def test_matches_a_registry_name_that_only_adds_sameiet(self):
        self.assertTrue(legal_name_matches("BJERGSTED TERRASSE", "SAMEIET BJERGSTED TERRASSE"))

    def test_rejects_a_different_company(self):
        self.assertFalse(legal_name_matches(ORG_NAME, "FJÆRLAND KRAFT EIENDOM AS"))
        self.assertFalse(legal_name_matches(ORG_NAME, "ANNET AS"))


class PurehelpObservationTests(unittest.TestCase):
    def setUp(self):
        self.raw = page_for(company()).encode("utf-8")
        self.rows = build_observations(
            ORG,
            ORG_NAME,
            company(),
            PAGE_URL,
            self.raw,
            "2026-11-06T00:00:00Z",
        )
        self.by_signal = {row["signal_type"]: row for row in self.rows}

    def test_publishes_a_profile_metrics_row_for_the_company_directory(self):
        row = self.by_signal["profile_metrics"]
        self.assertEqual(row["organisation_number"], ORG)
        self.assertEqual(row["platform"], "company_directory")
        self.assertEqual(row["source_url"], PAGE_URL)
        self.assertEqual(row["retrieved_at"], "2026-11-06T00:00:00Z")
        self.assertEqual(row["acquisition_mode"], "permitted_public_page")
        self.assertEqual(row["rights_status"], "approved")
        self.assertTrue(row["exact_entity"])
        self.assertEqual(len(row["content_sha256"]), 64)
        self.assertEqual(row["source_class"], "company_directory")

    def test_the_profile_metrics_row_proves_the_exact_organisation_number(self):
        row = self.by_signal["profile_metrics"]
        proof_types = [proof["type"] for proof in row["identity_proof"]]
        self.assertIn("exact_organisation_number_on_directory_page", proof_types)
        self.assertIn("exact_legal_name_on_directory_page", proof_types)

    def test_the_profile_metrics_row_carries_the_registry_facts(self):
        metrics = self.by_signal["profile_metrics"]["metrics"]
        self.assertEqual(metrics["legal_form"], "AS")
        self.assertEqual(metrics["nace_code"], "35.121")
        self.assertEqual(metrics["municipality"], "OSLO")
        self.assertEqual(metrics["registration_date"], "2016-01-06")
        self.assertEqual(metrics["registry_status"], "ACTIVE")

    def test_publishes_a_workforce_snapshot_with_the_as_of_date(self):
        row = self.by_signal["workforce_snapshot"]
        self.assertEqual(row["metrics"]["employees"], 42)
        self.assertEqual(row["metrics"]["as_of"], "2026-09-18")
        self.assertEqual(row["metrics"]["employees_source"], "enhetsregisteret")

    def test_publishes_the_contact_details(self):
        self.assertEqual(self.by_signal["contact_email"]["metrics"]["email"], "post@example.no")
        self.assertEqual(self.by_signal["contact_phone"]["metrics"]["phone"], "22 33 44 55")

    def test_never_publishes_a_financial_value_from_the_directory(self):
        rows = build_observations(
            ORG,
            ORG_NAME,
            company({"financials": [{"fiscalYear": 2025, "revenue": 1000}]}),
            PAGE_URL,
            self.raw,
            "2026-11-06T00:00:00Z",
        )
        for row in rows:
            self.assertNotIn("revenue", json.dumps(row["metrics"]))

    def test_every_row_has_a_unique_id(self):
        ids = [row["id"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(row["id"].startswith("purehelp-") for row in self.rows))


class PurehelpRunTests(unittest.TestCase):
    def test_runs_over_a_page_cache_and_rejects_a_wrong_company(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "pages"
            cache.mkdir(parents=True)
            (cache / f"{ORG}.html").write_bytes(page_for(company()).encode("utf-8"))
            # A page whose payload states another organisation number.
            other = "123456789"
            (cache / f"{other}.html").write_bytes(
                page_for(company({"orgNumber": "999999999", "name": "ANNET AS"}), other).encode("utf-8")
            )
            # A page for the right organisation number but another company.
            third = "555555555"
            (cache / f"{third}.html").write_bytes(
                page_for(company({"orgNumber": third, "name": "ANNET AS"}), third).encode("utf-8")
            )
            profiles = {
                ORG: {"organisation_number": ORG, "name": ORG_NAME},
                other: {"organisation_number": other, "name": "ANNET AS"},
                third: {"organisation_number": third, "name": ORG_NAME},
            }
            rows, report = run_connector(
                profiles=profiles,
                wanted=[ORG, other, third],
                cache_dir=cache,
                offline=True,
            )
        self.assertEqual(report["orgs_accepted"], 1)
        self.assertEqual(report["rejected_by_reason"].get("org_number_mismatch"), 1)
        self.assertEqual(report["rejected_by_reason"].get("legal_name_mismatch"), 1)
        self.assertTrue(all(row["organisation_number"] == ORG for row in rows))
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
