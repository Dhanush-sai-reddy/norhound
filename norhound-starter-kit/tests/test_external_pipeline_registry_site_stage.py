"""The external pipeline must publish the registry-proved website stage.

BRREG declares each company's website domain in its own official filing. When
the crawled page sits on exactly that domain and corroborates the company,
the identity is official-grade — the registry resolves the domain to the legal
entity and the page confirms it. That proof unlocks the website family for
hundreds of brand sites whose legal name never appears in their own title.

This stage was implemented and tested but never wired into the pipeline, so
the 1,000-company run published only 348 website claims instead of 564.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = (ROOT / "scripts" / "run_external_pipeline.py").read_text(encoding="utf-8")


class RegistrySiteStageTests(unittest.TestCase):
    def test_pipeline_runs_the_registry_proved_site_connector(self) -> None:
        self.assertIn("extract_registry_proved_site_observations.py", PIPELINE)

    def test_pipeline_collects_the_registry_site_output(self) -> None:
        self.assertIn("observation_files.append(registry_site_out)", PIPELINE)

    def test_registry_site_stage_is_enabled_by_default(self) -> None:
        self.assertIn('parser.set_defaults(registry_sites=True)', PIPELINE)
        self.assertIn(
            '"--no-registry-sites", dest="registry_sites", action="store_false"',
            PIPELINE,
        )


if __name__ == "__main__":
    unittest.main()
