"""The sole-declarer domain index must build from the official BRREG bulk dump.

Brønnøysund publishes the whole Enhetsregisteret as one gzipped JSON document
(`GET /enhetsregisteret/api/enheter/lastned`, ~211 MB compressed, no API key).
The shipped index builder only understood CSV, so the official dump could not
be used and the registry-declared-domain proof stayed switched off for the
whole batch.

Only domains declared by exactly one organisation number are written. A domain
claimed by two or more organisation numbers is omitted entirely, so downstream
promotion is default-deny.
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
sys.path.insert(0, str(ROOT))

from scripts.build_registry_domain_index import build_index  # noqa: E402


def _dump(rows: list[dict]) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".json.gz", delete=False)
    handle.close()
    with gzip.open(handle.name, "wt", encoding="utf-8") as sink:
        json.dump(rows, sink, ensure_ascii=False)
    return Path(handle.name)


class BuildIndexTests(unittest.TestCase):
    def test_reads_organisations_from_the_official_json_dump(self) -> None:
        source = _dump([
            {"organisasjonsnummer": "123456789", "hjemmeside": "https://www.example.no/"},
            {"organisasjonsnummer": "987654321", "hjemmeside": "other.no"},
        ])
        try:
            index, report = build_index(source)
        finally:
            source.unlink()
        self.assertEqual(index["example.no"], "123456789")
        self.assertEqual(report["register_rows"], 2)

    def test_shared_domains_are_omitted(self) -> None:
        source = _dump([
            {"organisasjonsnummer": "123456789", "hjemmeside": "shared.no"},
            {"organisasjonsnummer": "987654321", "hjemmeside": "shared.no"},
        ])
        try:
            index, report = build_index(source)
        finally:
            source.unlink()
        self.assertNotIn("shared.no", index)
        self.assertEqual(report["shared_domains_omitted"], 1)

    def test_www_prefix_and_scheme_are_normalised(self) -> None:
        source = _dump([
            {"organisasjonsnummer": "123456789", "hjemmeside": "http://WWW.Example.no/path"},
        ])
        try:
            index, _ = build_index(source)
        finally:
            source.unlink()
        self.assertIn("example.no", index)

    def test_rows_without_a_valid_organisation_number_are_skipped(self) -> None:
        source = _dump([
            {"organisasjonsnummer": "123", "hjemmeside": "short.no"},
            {"organisasjonsnummer": "123456789", "hjemmeside": "good.no"},
        ])
        try:
            index, report = build_index(source)
        finally:
            source.unlink()
        self.assertNotIn("short.no", index)
        self.assertIn("good.no", index)
        self.assertEqual(report["register_rows"], 2)


if __name__ == "__main__":
    unittest.main()
