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
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "run_external_pipeline.py"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts import run_external_pipeline as pipeline  # noqa: E402


def _tree() -> ast.Module:
    return ast.parse(PIPELINE.read_text(encoding="utf-8"))


def _stage_line(tree: ast.Module, script_name: str) -> int:
    """Line number of the `run([...])` call that invokes `script_name`."""
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "run"):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and child.value.endswith(script_name)
            ):
                lines.append(node.lineno)
                break
    if not lines:
        raise AssertionError(f"no run([...]) call invokes {script_name}")
    return min(lines)


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


class RescueStageTests(unittest.TestCase):
    """The browser rescue must run inside the pipeline, before the site stages.

    Measured on the shipped 1,000-company corpus, 167 companies had no usable
    page: 68 were `source_error` (the urllib fetch never produced a page) and
    99 were `js_fallback_candidate` (the page exists but its text is rendered
    by client-side JavaScript, so the static HTML was almost empty — 90 of the
    99 carried no social link at all).

    `scripts/rescue_website_pages.py` re-fetches exactly those homepages with
    a headless Chromium and rebuilds the website evidence with the same shape
    `fetch_website` produces. It only helps if it runs BEFORE the activity,
    news, jobs, description, registry-site and ATS stages: those stages read
    the website evidence, so a rescue that runs afterwards would recover text
    that nothing downstream ever sees.
    """

    def test_the_pipeline_runs_the_rescue_connector(self) -> None:
        self.assertIn("rescue_website_pages.py", PIPELINE.read_text(encoding="utf-8"))

    def test_the_rescue_stage_is_enabled_by_default(self) -> None:
        source = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("parser.set_defaults(rescue=True)", source)
        self.assertIn('"--no-rescue", dest="rescue", action="store_false"', source)

    def test_the_rescue_stage_runs_before_the_site_stages(self) -> None:
        tree = _tree()
        self.assertLess(
            _stage_line(tree, "rescue_website_pages.py"),
            _stage_line(tree, "extract_company_site_activity.py"),
            "the rescue must run before the site stages, or the recovered page text is discarded",
        )

    def test_the_rescued_profiles_replace_the_input_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rescue = Path(tmp) / "batch-rescued-profiles.jsonl"
            rescue.write_text("{}\n", encoding="utf-8")
            self.assertEqual(pipeline.resolve_profiles_path(rescue, "profiles.jsonl"), str(rescue))

    def test_a_missing_or_empty_rescue_output_keeps_the_input_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            self.assertEqual(pipeline.resolve_profiles_path(empty, "profiles.jsonl"), "profiles.jsonl")
            missing = Path(tmp) / "missing.jsonl"
            self.assertEqual(pipeline.resolve_profiles_path(missing, "profiles.jsonl"), "profiles.jsonl")


class StageBudgetTests(unittest.TestCase):
    """A stage that needs more than an hour must get more than an hour.

    The 1,000-company run died at the annual-report workforce stage: it
    downloads and OCRs a full annual report per company, and the default
    one-hour budget killed it after 276 cached PDFs, which took the whole run
    with it (the pipeline is fail-fast, so stages 6-14 never ran).
    """

    def test_the_workforce_pdf_stage_gets_more_than_an_hour(self) -> None:
        self.assertGreaterEqual(pipeline.stage_timeout("workforce_pdf"), 10800)

    def test_the_rescue_stage_gets_more_than_an_hour(self) -> None:
        self.assertGreaterEqual(pipeline.stage_timeout("rescue"), 5400)

    def test_a_stage_budget_can_be_overridden_by_the_environment(self) -> None:
        os.environ["NORHOUND_WORKFORCE_PDF_TIMEOUT_S"] = "42"
        try:
            self.assertEqual(pipeline.stage_timeout("workforce_pdf"), 42)
        finally:
            del os.environ["NORHOUND_WORKFORCE_PDF_TIMEOUT_S"]

    def test_the_pipeline_uses_the_per_stage_budget(self) -> None:
        source = PIPELINE.read_text(encoding="utf-8")
        self.assertIn('timeout=stage_timeout("rescue")', source)
        self.assertIn('timeout=stage_timeout("workforce_pdf")', source)


if __name__ == "__main__":
    unittest.main()
