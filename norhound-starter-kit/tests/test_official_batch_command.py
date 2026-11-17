"""The official run has one documented command, and it must accept their batch.

The official submission contract asks for "one documented command that accepts
a JSONL batch of organisation numbers" and "exactly one terminal envelope per
input", plus a "machine-readable run report with runtime, request count and
third-party cost":

  https://builderr.ai/starter-briefs/signalpost.md          (retrieved 2026-11-17)
  https://builderr.ai/signalpost-starter-kit.tar.gz         (retrieved 2026-11-18)

These tests pin the command's shape so it cannot quietly stop accepting a
supplied batch, stop emitting refresh metadata, or stop writing the run report.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from norway_company_agent.batch import read_organisation_numbers  # noqa: E402

SCRIPT = ROOT / "scripts" / "run_official_batch.sh"


class OfficialBatchCommandTests(unittest.TestCase):
    def test_the_command_exists_and_is_executable(self) -> None:
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(SCRIPT.stat().st_mode & 0o111)

    def test_the_command_requires_a_batch(self) -> None:
        result = subprocess.run(
            ["bash", str(SCRIPT)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--batch is required", result.stderr)

    def test_the_command_passes_the_supplied_batch_to_the_pipeline(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ENTRY_MANIFEST=\"$BATCH\"", text)
        self.assertIn("bash scripts/run_full_batch.sh", text)

    def test_the_command_attaches_refresh_changes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("attach_refresh_changes.py", text)
        self.assertIn("--previous", text)

    def test_the_command_writes_the_run_report(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("build_official_run_report.py", text)
        self.assertIn("official-run-report.json", text)

    def test_the_command_never_asks_for_a_credential(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("GOOGLE_PLACES_KEY", "FIRECRAWL_API_KEY", "NVIDIA_API_KEY"):
            self.assertNotIn(forbidden, text)


class SuppliedBatchFormatTests(unittest.TestCase):
    """Builderr hands over a JSONL batch. Both shapes must be accepted."""

    def test_a_jsonl_batch_of_bare_numbers_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch.jsonl"
            path.write_text("810034882\n974760673\n", encoding="utf-8")
            orgs = read_organisation_numbers(path)
        self.assertEqual(orgs, ["810034882", "974760673"])

    def test_a_jsonl_batch_of_objects_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch.jsonl"
            path.write_text(
                json.dumps({"organisation_number": "810034882"}) + "\n",
                encoding="utf-8",
            )
            orgs = read_organisation_numbers(path)
        self.assertEqual(orgs, ["810034882"])


class RunReportTests(unittest.TestCase):
    def test_the_report_states_runtime_requests_and_cost(self) -> None:
        from scripts import build_official_run_report as report_builder

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "run-report.json").write_text(
                json.dumps(
                    {
                        "started_at": "2026-11-18T10:00:00Z",
                        "completed_at": "2026-11-18T10:30:00Z",
                        "operations": {"requests": 1200},
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "envelopes-final.jsonl").write_text(
                json.dumps(
                    {
                        "organisation_number": "810034882",
                        "claims": [{"field": "official_website"}],
                        "evidence": [{"id": "ev-1"}],
                        "operations": {"requests": 3, "third_party_cost_usd": 0},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "external-final.jsonl").write_text(
                json.dumps({"id": "obs-1"}) + "\n", encoding="utf-8"
            )
            (run_dir / "eval-final.json").write_text(
                json.dumps({"entity_precision": 1.0, "wrong_entity_publications": 0}),
                encoding="utf-8",
            )
            report = report_builder.build(run_dir)

        self.assertGreater(report["runtime_ms"], 0)
        self.assertEqual(report["requests"]["registry_and_website"], 1200)
        self.assertEqual(report["third_party_cost_usd"], 0)
        self.assertEqual(report["outputs"]["envelopes"], 1)
        self.assertEqual(report["outputs"]["claims"], 1)
        self.assertEqual(report["identity_precision"], 1.0)

    def test_an_unmeasured_request_count_is_a_bound_not_a_guess(self) -> None:
        from scripts import build_official_run_report as report_builder

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "external-final.jsonl").write_text(
                json.dumps({"id": "obs-1"}) + "\n", encoding="utf-8"
            )
            report = report_builder.build(run_dir)

        self.assertFalse(report["requests"]["measured"])
        self.assertEqual(report["requests"]["external_lower_bound"], 1)
        self.assertIsNone(report["requests"]["external_connectors"])
        self.assertIn("note", report["requests"])

    def test_a_measured_request_log_replaces_the_bound(self) -> None:
        from scripts import build_official_run_report as report_builder

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "requests.jsonl").write_text(
                "\n".join(
                    json.dumps({"host": "example.no", "method": "GET", "status": 200})
                    for _ in range(3)
                )
                + "\n",
                encoding="utf-8",
            )
            report = report_builder.build(run_dir)

        self.assertTrue(report["requests"]["measured"])
        self.assertEqual(report["requests"]["total"], 3)
        self.assertEqual(report["requests"]["busiest_hosts"]["example.no"], 3)


if __name__ == "__main__":
    unittest.main()
