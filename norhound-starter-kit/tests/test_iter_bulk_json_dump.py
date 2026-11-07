"""The registry bulk reader must understand the official JSON dump.

Brønnøysund publishes the whole Enhetsregisteret as a gzipped JSON array
(`GET /enhetsregisteret/api/enheter/lastned`, ~211 MB compressed, no API key).
That single download now feeds both the sole-declarer domain index and the
batch builder, so the whole pipeline runs from one official fetch instead of
two.

`iter_bulk` only understood CSV, so the JSON dump raised
`_csv.Error: Could not determine delimiter` and the run died at the base
batch stage — after the 211 MB download had already been paid for.
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.sampling import iter_bulk  # noqa: E402


def _dump(records: list[dict]) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".json.gz", delete=False)
    handle.close()
    with gzip.open(handle.name, "wt", encoding="utf-8") as sink:
        json.dump(records, sink, ensure_ascii=False)
    return Path(handle.name)


def _record(org: str = "810034882") -> dict:
    return {
        "organisasjonsnummer": org,
        "navn": "SANDNES ELEKTRISKE AS",
        "organisasjonsform": {"kode": "AS", "beskrivelse": "Aksjeselskap"},
        "antallAnsatte": 10,
        "konkurs": False,
        "underAvvikling": False,
        "forretningsadresse": {
            "kommune": "SANDNES",
            "kommunenummer": "1108",
            "adresse": ["Strandgata 21"],
            "postnummer": "4307",
            "poststed": "SANDNES",
        },
        "postadresse": {"postnummer": "4307", "poststed": "SANDNES"},
        "naeringskode1": {"kode": "43.210", "beskrivelse": "Elektrisk installasjonsarbeid"},
        "hjemmeside": "https://sandneselektriske.no",
        "sisteInnsendteAarsregnskap": "2025",
        "telefon": "51 68 57 00",
        "epostadresse": "post@sandneselektriske.no",
    }


class JsonDumpTests(unittest.TestCase):
    def test_the_official_json_dump_is_readable(self) -> None:
        path = _dump([_record()])
        try:
            rows = list(iter_bulk(path))
        finally:
            path.unlink()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["organisation_number"], "810034882")
        self.assertEqual(row["name"], "SANDNES ELEKTRISKE AS")
        self.assertEqual(row["legal_form"], "AS")
        self.assertEqual(row["employees"], 10)
        self.assertEqual(row["municipality"], "SANDNES")
        self.assertEqual(row["municipality_number"], "1108")
        self.assertEqual(row["industry_code"], "43.210")
        self.assertEqual(row["industry_label"], "Elektrisk installasjonsarbeid")
        self.assertEqual(row["website"], "https://sandneselektriske.no")
        self.assertEqual(row["latest_submitted_accounts"], "2025")
        self.assertFalse(row["bankrupt"])
        self.assertFalse(row["liquidating"])

    def test_the_row_keeps_the_fields_the_registry_enrichment_reads(self) -> None:
        path = _dump([_record()])
        try:
            row = next(iter(iter_bulk(path)))
        finally:
            path.unlink()
        raw = row["raw"]
        self.assertEqual(raw["telefon"], "51 68 57 00")
        self.assertEqual(raw["epostadresse"], "post@sandneselektriske.no")
        self.assertEqual(raw["forretningsadresse.adresse"], ["Strandgata 21"])
        self.assertEqual(raw["postadresse.postnummer"], "4307")

    def test_rows_with_an_invalid_organisation_number_are_skipped(self) -> None:
        path = _dump([_record("123"), _record("810034882")])
        try:
            rows = list(iter_bulk(path))
        finally:
            path.unlink()
        self.assertEqual([row["organisation_number"] for row in rows], ["810034882"])

    def test_a_csv_dump_still_works(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".csv.gz", delete=False, mode="w")
        handle.write(
            "Organisasjonsnummer;Navn;Organisasjonsform.kode;Antall ansatte;Konkurs;"
            "Under avvikling;Forretningsadresse.kommune;Forretningsadresse.kommunenummer;"
            "Næringskode1.kode;Næringskode1.beskrivelse;Hjemmeside;Siste innsendte årsregnskap\n"
            "810034882;SANDNES ELEKTRISKE AS;AS;10;False;False;SANDNES;1108;43.210;"
            "Elektrisk installasjonsarbeid;sandneselektriske.no;2025\n"
        )
        handle.close()
        path = Path(handle.name)
        try:
            rows = list(iter_bulk(path))
        finally:
            path.unlink()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organisation_number"], "810034882")
        self.assertEqual(rows[0]["legal_form"], "AS")
        self.assertEqual(rows[0]["employees"], 10)


if __name__ == "__main__":
    unittest.main()
