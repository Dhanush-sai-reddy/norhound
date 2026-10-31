"""One terminal envelope per input number, even when the register dropped the entity.

Deleted entities vanish from the bulk registry dump. The batch contract still
requires an envelope for every input, so absence must surface as an explicit
state instead of aborting the run or silently shortening the batch.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import profiles_from_bulk, terminal_envelope, validate_envelopes  # noqa: E402

COLUMNS = (
    "organisasjonsnummer",
    "navn",
    "organisasjonsform.kode",
    "antallAnsatte",
    "konkurs",
    "underAvvikling",
    "forretningsadresse.kommune",
    "forretningsadresse.kommunenummer",
    "næringskode1.kode",
    "næringskode1.beskrivelse",
    "hjemmeside",
    "sisteInnsendteAarsregnskap",
)

MODULES = ("registry", "accounting_obligation", "registry_live", "financials", "roles", "website")

# 999999991 is a syntactically valid number that the snapshot below does not list
ABSENT = "999999991"
ORGS = ["918493415", ABSENT, "915589338"]


def write_bulk(directory: Path) -> Path:
    path = directory / "enheter.csv"
    rows = [
        ("918493415", "FJELLDAL VEST AS", "AS", "12", "false", "false", "Oslo", "0301", "4321", "Verksteddrift", "https://fjelldal-vest.example", "2024"),
        ("915589338", "HAFSLUND HAVBRUK AS", "AS", "44", "false", "false", "Bodø", "1804", "0322", "Oppdrett", "https://hafslund.example", "2024"),
    ]
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as handle:
        handle.write(";".join(COLUMNS) + "\n")
        for row in rows:
            handle.write(";".join(row) + "\n")
    return path


class AbsentEntityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bulk = write_bulk(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_number_does_not_abort_the_batch(self):
        profiles, metadata = profiles_from_bulk(self.bulk, ORGS)
        self.assertEqual([profile["organisation_number"] for profile in profiles], ORGS)
        self.assertEqual(metadata["absent_from_snapshot"], [ABSENT])
        self.assertEqual(metadata["selected"], 2)

    def test_absent_profile_records_explicit_not_found_without_values(self):
        profiles, _ = profiles_from_bulk(self.bulk, ORGS)
        absent = next(profile for profile in profiles if profile["organisation_number"] == ABSENT)
        self.assertTrue(absent["absent_from_registry_snapshot"])
        self.assertIsNone(absent["name"])
        registry = absent["evidence"]["registry"]
        self.assertEqual(registry["status"], "not_found")
        self.assertIsNone(registry["value"])
        self.assertIn("absent from the frozen registry snapshot", registry["note"])
        self.assertTrue(registry["content_sha256"])

    def test_envelope_count_matches_inputs_with_no_silent_drop(self):
        profiles, _ = profiles_from_bulk(self.bulk, ORGS)
        for profile in profiles:
            for module in MODULES:
                profile["evidence"].setdefault(
                    module,
                    {
                        "field": module,
                        "status": "not_found" if profile.get("absent_from_registry_snapshot") else "available",
                        "source_type": "official_registry_bulk",
                        "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv",
                        "retrieved_at": "2026-11-01T00:00:00Z",
                        "retry_count": 0,
                    },
                )
        envelopes = [
            terminal_envelope(profile, run_id="batch-absent", modules=MODULES, started_at="2026-11-01T00:00:00Z", completed_at="2026-11-01T00:00:05Z")
            for profile in profiles
        ]
        self.assertEqual(len(envelopes), len(ORGS))
        validation = validate_envelopes(envelopes, len(ORGS))
        self.assertTrue(validation["passed"], validation)
        self.assertTrue(validation["checks"]["zero_silent_drops"])
        states = {item["organisation_number"]: item["state"] for item in envelopes}
        self.assertEqual(states, {org: "complete" for org in ORGS})

    def test_absent_envelope_is_serialisable_and_carries_no_fabricated_facts(self):
        profiles, _ = profiles_from_bulk(self.bulk, ORGS)
        absent = next(profile for profile in profiles if profile["organisation_number"] == ABSENT)
        envelope = terminal_envelope(absent, run_id="batch-absent", modules=("registry", "accounting_obligation"), started_at="2026-11-01T00:00:00Z", completed_at="2026-11-01T00:00:05Z")
        round_tripped = json.loads(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        self.assertEqual(round_tripped["profile"]["name"], None)
        self.assertEqual(round_tripped["modules"]["registry"]["state"], "not_found")
        for record in round_tripped["profile"]["evidence"].values():
            self.assertIsNone(record["value"])


class CompetitionBatchCliTests(unittest.TestCase):
    """Run the batch runner end to end: an absent number still gets an envelope, at zero requests."""

    def test_one_envelope_per_input_with_no_network_and_no_silent_drop(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            bulk = write_bulk(directory)
            organisations = directory / "orgs.jsonl"
            organisations.write_text("".join(json.dumps({"organisation_number": org}) + "\n" for org in ORGS), encoding="utf-8")
            envelopes_path = directory / "envelopes.jsonl"
            profiles_path = directory / "profiles.jsonl"
            report_path = directory / "report.json"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run_competition_batch.py"),
                 "--organisations", str(organisations), "--bulk", str(bulk),
                 "--output", str(envelopes_path), "--profiles-output", str(profiles_path),
                 "--report", str(report_path), "--run-id", "batch-cli",
                 "--modules", "registry,accounting_obligation"],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            envelopes = [json.loads(line) for line in envelopes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual([item["organisation_number"] for item in envelopes], ORGS)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["validation"]["passed"], report["validation"])
            self.assertTrue(report["validation"]["checks"]["zero_silent_drops"])
            self.assertEqual(report["registry"]["absent_from_snapshot"], [ABSENT])
            self.assertEqual(report["operations"]["requests"], 0)
            absent = next(item for item in envelopes if item["organisation_number"] == ABSENT)
            self.assertEqual({module: absent["modules"][module]["state"] for module in absent["modules"]}, {"registry": "not_found", "accounting_obligation": "not_found"})


if __name__ == "__main__":
    unittest.main()
