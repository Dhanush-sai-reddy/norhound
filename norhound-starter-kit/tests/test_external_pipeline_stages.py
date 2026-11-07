"""The external pipeline must never reference an uninitialised observation list.

The GLEIF and Google Places stages append their output to `observation_files`,
but the list is only created further down the script. Enabling either stage
therefore crashed the whole 1,000-company run with a `NameError` after every
other connector had already spent its request budget.

These tests pin the stage order: the list exists before the first stage can
append to it, and every optional stage contributes to the consolidated output.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "run_external_pipeline.py"


def _tree() -> ast.Module:
    return ast.parse(PIPELINE.read_text(encoding="utf-8"))


def _first_append_line(tree: ast.Module) -> int:
    """Line number of the earliest `observation_files.append(...)` call."""
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "observation_files"
        ):
            lines.append(node.lineno)
    if not lines:
        raise AssertionError("no observation_files.append(...) call found")
    return min(lines)


def _assignment_line(tree: ast.Module) -> int:
    """Line number of the `observation_files = [...]` assignment."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "observation_files":
                    return node.lineno
    raise AssertionError("no observation_files assignment found")


class ObservationListOrderTests(unittest.TestCase):
    def test_observation_files_is_created_before_any_stage_appends_to_it(self) -> None:
        tree = _tree()
        self.assertLess(
            _assignment_line(tree),
            _first_append_line(tree),
            "observation_files is appended to before it is assigned; the pipeline raises NameError",
        )

    def test_every_optional_stage_output_is_collected(self) -> None:
        source = PIPELINE.read_text(encoding="utf-8")
        for stage in ("gleif_out", "places_out", "google_news_out", "kunngjoring_out"):
            self.assertIn(f"observation_files.append({stage})", source)


class AtsStageTests(unittest.TestCase):
    """The ATS connector must run inside the pipeline, not as a side script.

    `run_ats_jobs_connector.py` existed and produced rows, but the pipeline
    never called it, so every applicant-tracking system the corpus could reach
    was silently dropped from the shipped corpus. The connector reaches only
    public ATS feeds (no key), and only through a link published on the
    company's own exact-identity site.
    """

    def test_pipeline_runs_the_ats_connector(self) -> None:
        self.assertIn("run_ats_jobs_connector.py", PIPELINE.read_text(encoding="utf-8"))

    def test_pipeline_collects_the_ats_output(self) -> None:
        self.assertIn("observation_files.append(ats_out)", PIPELINE.read_text(encoding="utf-8"))

    def test_ats_stage_is_enabled_by_default(self) -> None:
        source = PIPELINE.read_text(encoding="utf-8")
        self.assertIn('parser.set_defaults(ats=True)', source)
        self.assertIn('"--no-ats", dest="ats", action="store_false"', source)


if __name__ == "__main__":
    unittest.main()
