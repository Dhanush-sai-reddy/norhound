"""The whole-run script must cover every stage of the Signalpost pipeline.

The repository documented the pipeline as a list of `uv run python ...`
commands in the README, which meant a 1,000-company run had to be driven by
hand and could silently stop after any stage. `scripts/run_full_batch.sh` is
the single executable that runs every stage in order, and this test pins the
stage list so a stage cannot be dropped without failing the suite.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_full_batch.sh"


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class FullBatchScriptTests(unittest.TestCase):
    def test_the_script_exists_and_is_executable(self) -> None:
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(SCRIPT.stat().st_mode & 0o111, "run_full_batch.sh must be executable")

    def test_the_script_declares_every_required_stage(self) -> None:
        text = _script_text()
        required = [
            "select_entry_batch.py",
            "run_competition_batch.py",
            "build_registry_domain_index.py",
            "promote_registry_declared_sites.py",
            "run_external_pipeline.py",
            "merge_external_outputs.py",
            "purge_wrong_company_probes.py",
            "verify_and_label_observations.py",
            "evaluate_external_footprint.py",
            "emit_contract_envelope.py",
            "build_deterministic_summaries.py",
            "build_static_site.py",
            "measure_recall.py",
        ]
        for stage in required:
            self.assertIn(stage, text, f"{stage} stage missing from run_full_batch.sh")

    def test_the_script_is_fail_fast(self) -> None:
        self.assertRegex(_script_text(), r"set\s+-[a-z]*e")

    def test_no_stage_requires_an_api_key(self) -> None:
        """No stage may be handed a credential.

        A comment may name a key to say it is *not* needed; what must not
        appear is an actual credential being passed to a stage or exported
        into the environment.
        """
        text = _script_text()
        code = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in (
            "FIRECRAWL_API_KEY",
            "GOOGLE_PLACES_KEY",
            "NVIDIA_API_KEY",
            "BRAVE_API_KEY",
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
        ):
            self.assertNotIn(forbidden, code, f"{forbidden} would make the run keyed")
        self.assertNotIn("--api-key-env", code)
        self.assertNotRegex(code, r"export\s+\w*KEY")

    def test_the_script_states_that_no_credential_is_needed(self) -> None:
        self.assertIn("WITHOUT an API key", _script_text())

    def test_the_script_documents_the_keyless_sources_it_uses(self) -> None:
        text = _script_text()
        self.assertIn("keyless", text.lower())

    def test_a_smaller_batch_can_be_run_from_an_existing_manifest(self) -> None:
        """The 1,000-company floor belongs to the submission, not to the pipeline.

        `select_entry_batch.py` refuses to emit fewer than 1,000 entries because
        a submission must cover 1,000 companies. That constraint must not stop
        the pipeline itself from running on a smaller manifest, so the script
        accepts an existing manifest and derives the expected count from it.
        """
        text = _script_text()
        self.assertIn("ENTRY_MANIFEST", text)
        self.assertIn("expected_count", text)


if __name__ == "__main__":
    unittest.main()
