"""Regression tests for the envelope rewrite that drops the duplicate copy.

The emitter used to nest the built contract envelope under a ``contract``
key, writing every claim and every evidence record twice.  The shipped
``envelopes.jsonl`` reached 118 MB that way, past the 100 MiB per-file limit
of the Git host.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.rebuild_submission_artifacts import rewrite  # noqa: E402


class RewriteTests(unittest.TestCase):
    def test_the_duplicate_contract_copy_is_dropped(self):
        envelope = {"organisation_number": "912345678", "contract": {"claims": [{"field": "x"}]}}
        self.assertNotIn("contract", rewrite(envelope))

    def test_the_claims_survive_at_the_top_level(self):
        envelope = {"organisation_number": "912345678",
                    "contract": {"claims": [{"field": "legal_name", "value": "TEST AS"}],
                                 "evidence": [{"id": "ev-1"}],
                                 "run": {"terminal_status": "completed"},
                                 "errors": [],
                                 "operations": {"claims": 1}}}
        out = rewrite(envelope)
        self.assertEqual(out["claims"], [{"field": "legal_name", "value": "TEST AS"}])
        self.assertEqual(out["evidence"], [{"id": "ev-1"}])
        self.assertEqual(out["run"]["terminal_status"], "completed")
        self.assertEqual(out["operations"], {"claims": 1})

    def test_every_other_section_is_left_untouched(self):
        envelope = {"organisation_number": "912345678", "profile": {"name": "TEST AS"},
                    "modules": {"roles": {}}, "state": "complete",
                    "contract": {"claims": [], "evidence": []}}
        out = rewrite(envelope)
        self.assertEqual(out["profile"], {"name": "TEST AS"})
        self.assertEqual(out["modules"], {"roles": {}})
        self.assertEqual(out["state"], "complete")

    def test_an_envelope_without_a_contract_copy_is_unchanged(self):
        envelope = {"organisation_number": "912345678", "claims": [{"field": "x"}]}
        self.assertEqual(rewrite(dict(envelope)), envelope)

    def test_the_cli_rewrites_a_file_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "envelopes.jsonl"
            dst = Path(tmp) / "out.jsonl"
            src.write_text(json.dumps({
                "organisation_number": "912345678",
                "profile": {"name": "TEST AS"},
                "contract": {"claims": [{"field": "legal_name", "value": "TEST AS"}],
                             "evidence": [], "run": {"terminal_status": "completed"},
                             "errors": [], "operations": {}},
            }) + "\n", encoding="utf-8")
            subprocess.run([sys.executable, str(ROOT / "scripts" / "rebuild_submission_artifacts.py"),
                            "--envelopes", str(src), "--output", str(dst)],
                           check=True, capture_output=True)
            row = json.loads(dst.read_text(encoding="utf-8").splitlines()[0])
            self.assertNotIn("contract", row)
            self.assertEqual(row["claims"][0]["field"], "legal_name")
            self.assertEqual(row["profile"], {"name": "TEST AS"})


if __name__ == "__main__":
    unittest.main()
