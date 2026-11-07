from __future__ import annotations

import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "run_external_pipeline.py"


class ExternalPipelineWiringTests(unittest.TestCase):
    def test_org_ids_file_is_written_before_it_is_used(self) -> None:
        lines = SOURCE.read_text(encoding="utf-8").splitlines()
        assignments = [i for i, line in enumerate(lines) if line.strip().startswith("orgs_out =")]
        self.assertEqual(len(assignments), 1, "expected exactly one orgs_out assignment")
        assigned = assignments[0]
        used = [i for i, line in enumerate(lines) if "orgs_out" in line and i != assigned]
        self.assertTrue(used, "orgs_out is never passed to a connector")
        too_early = [i + 1 for i in used if i < assigned]
        self.assertEqual(too_early, [], f"orgs_out referenced before it is written: lines {too_early}")

    def test_every_connector_output_path_is_defined_once(self) -> None:
        lines = SOURCE.read_text(encoding="utf-8").splitlines()
        defined = [line.strip().split(" =")[0] for line in lines if "_out = prefix.with_suffix" in line]
        duplicates = {name for name in defined if defined.count(name) > 1}
        self.assertEqual(duplicates, set(), f"output paths defined more than once: {sorted(duplicates)}")


if __name__ == "__main__":
    unittest.main()
