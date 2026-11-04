from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.measure_recall import build_report, has_publication_date

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure_recall.py"
EVALUATOR = ROOT / "scripts" / "evaluate_external_footprint.py"

ORG_A = "810034882"
ORG_B = "812702432"
ORG_C = "913460086"


def _profiles():
    return [
        {"organisation_number": ORG_A, "name": "SANDNES ELEKTRISKE AS"},
        {"organisation_number": ORG_B, "name": "RASTAVEGEN 1 AS"},
        {"organisation_number": ORG_C, "name": "FJELLVEIEN 5 AS"},
    ]


def _observation(**overrides):
    base = {
        "id": "obs-1",
        "organisation_number": ORG_A,
        "platform": "company_site",
        "source_url": "https://example.test/om-oss",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "content_sha256": "a" * 64,
        "exact_entity": True,
        "identity_proof": [{"type": "website_identity_gate", "status": "exact", "score": 0.95}],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_site",
        "signal_type": "public_post",
        "evidence_span": "Eksempel på en publisert artikkel.",
        "metrics": {},
    }
    base.update(overrides)
    return base


def _label(**overrides):
    base = {"id": "obs-1", "exact_entity": 1, "metric_correct": 1, "sentiment_correct": False}
    base.update(overrides)
    return base


def _fixture():
    """Three companies; every row is publishable unless a test needs it rejected."""
    observations = [
        # --- social profiles: A twice (once per organisation), B wrong entity, C unpublishable ---
        _observation(id="s1", organisation_number=ORG_A, platform="linkedin", signal_type="profile_handle"),
        _observation(id="s2", organisation_number=ORG_A, platform="facebook", signal_type="profile_handle"),
        _observation(id="s3", organisation_number=ORG_B, platform="linkedin", signal_type="profile_handle"),
        _observation(id="s4", organisation_number=ORG_C, platform="x", signal_type="profile_handle", rights_status="pending"),
        # --- news: A dated twice, B undated, C dated via top-level published_at ---
        _observation(id="d1", organisation_number=ORG_A, metrics={"published_at": "2026-01-02T10:00:00Z"}),
        _observation(id="d2", organisation_number=ORG_A, metrics={"published_at": "2026-02-03"}),
        _observation(id="d3", organisation_number=ORG_B, metrics={}),
        _observation(id="d4", organisation_number=ORG_C, published_at="2026-04-05T08:00:00Z", metrics={}),
        # --- hiring: A twice, B unpublishable, C wrong entity ---
        _observation(id="h1", organisation_number=ORG_A, platform="job_board", signal_type="job_posting"),
        _observation(id="h2", organisation_number=ORG_A, platform="job_board", signal_type="job_posting"),
        _observation(id="h3", organisation_number=ORG_B, platform="job_board", signal_type="job_posting", rights_status="pending"),
        _observation(id="h4", organisation_number=ORG_C, platform="job_board", signal_type="job_posting"),
        # --- publishable but never labelled: cannot count as published ---
        _observation(id="u1", organisation_number=ORG_B, platform="linkedin", signal_type="profile_handle"),
    ]
    labels = [
        _label(id="s1"),
        _label(id="s2"),
        _label(id="s3", exact_entity=0, metric_correct=0),
        _label(id="s4"),
        _label(id="d1"),
        _label(id="d2"),
        _label(id="d3", metric_correct=0),
        _label(id="d4"),
        _label(id="h1"),
        _label(id="h2"),
        _label(id="h3"),
        _label(id="h4", exact_entity=0, metric_correct=0),
    ]
    return _profiles(), observations, labels


def _report():
    profiles, observations, labels = _fixture()
    return build_report(profiles, observations, labels)


def _write_fixture(directory: Path):
    profiles, observations, labels = _fixture()
    paths = {}
    for name, rows in (("profiles", profiles), ("observations", observations), ("labels", labels)):
        path = directory / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        paths[name] = path
    return paths


class MeasureRecallGapTests(unittest.TestCase):
    def test_social_profile_counts_each_organisation_once(self):
        report = _report()
        self.assertEqual(report["direct_reviewer_gaps"]["social_profile"], 1)
        self.assertAlmostEqual(report["direct_reviewer_gap_ratios"]["social_profile"], 1 / 3)

    def test_dated_news_needs_a_machine_readable_date(self):
        report = _report()
        self.assertEqual(report["direct_reviewer_gaps"]["dated_news"], 2)
        self.assertAlmostEqual(report["direct_reviewer_gap_ratios"]["dated_news"], 2 / 3)

    def test_hiring_counts_job_postings_once_per_organisation(self):
        report = _report()
        self.assertEqual(report["direct_reviewer_gaps"]["hiring"], 1)
        self.assertAlmostEqual(report["direct_reviewer_gap_ratios"]["hiring"], 1 / 3)

    def test_rejected_and_wrong_entity_rows_are_never_counted(self):
        report = _report()
        # s3 and h4 are labelled "not the exact entity"; s4 and h3 fail validation.
        # Only organisation A may appear in the social and hiring gap counts.
        self.assertEqual(report["direct_reviewer_gaps"]["social_profile"], 1)
        self.assertEqual(report["direct_reviewer_gaps"]["hiring"], 1)
        self.assertEqual(report["wrong_entity_publications"], 2)
        self.assertEqual(report["unsupported_publications"], 0)

    def test_unlabelled_publishable_row_is_not_published(self):
        report = _report()
        self.assertEqual(report["unlabelled_publishable_observations"], 1)
        self.assertEqual(report["direct_reviewer_gaps"]["social_profile"], 1)

    def test_gap_score_is_mean_of_three_gap_ratios(self):
        report = _report()
        ratios = report["direct_reviewer_gap_ratios"]
        self.assertAlmostEqual(report["direct_reviewer_gap_score"], (ratios["social_profile"] + ratios["dated_news"] + ratios["hiring"]) / 3)
        self.assertEqual(report["direct_reviewer_gap_base_profiles"], 3)

    def test_publication_date_detector_accepts_three_locations(self):
        self.assertTrue(has_publication_date({"metrics": {"published_at": "2026-01-02T10:00:00Z"}}))
        self.assertTrue(has_publication_date({"metrics": {"published_date": "2026-03-04"}}))
        self.assertTrue(has_publication_date({"published_at": "2026-04-05T08:00:00Z"}))
        self.assertFalse(has_publication_date({"metrics": {}}))
        self.assertFalse(has_publication_date({"metrics": {"published_at": ""}}))
        self.assertFalse(has_publication_date({"metrics": {"published_at": "5. mai 2018"}}))
        self.assertFalse(has_publication_date({"metrics": {"published_at": "not-a-date"}}))


class MeasureRecallReportTests(unittest.TestCase):
    def test_coverage_fields_match_the_existing_scorer(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            paths = _write_fixture(directory)
            mine = directory / "measure.json"
            theirs = directory / "evaluate.json"
            subprocess.run(
                [sys.executable, str(SCRIPT), "--profiles", str(paths["profiles"]), "--observations", str(paths["observations"]),
                 "--labels", str(paths["labels"]), "--output", str(mine)],
                check=True, capture_output=True, text=True, cwd=str(ROOT),
            )
            subprocess.run(
                [sys.executable, str(EVALUATOR), "--profiles", str(paths["profiles"]), "--observations", str(paths["observations"]),
                 "--labels", str(paths["labels"]), "--output", str(theirs)],
                check=True, capture_output=True, text=True, cwd=str(ROOT),
            )
            mine_report = json.loads(mine.read_text(encoding="utf-8"))
            their_report = json.loads(theirs.read_text(encoding="utf-8"))
        self.assertEqual(mine_report["coverage"], their_report["coverage"])
        self.assertEqual(
            list(mine_report["coverage"]),
            ["any_external", "two_platforms", "workforce_jobs", "ratings_reviews", "buzz_engagement", "sentiment"],
        )

    def test_recall_proxy_is_mean_of_coverage_times_fifty(self):
        report = _report()
        expected = sum(report["coverage"].values()) / len(report["coverage"]) * 50
        self.assertAlmostEqual(report["recall_proxy_50"], expected)

    def test_precision_counts_are_not_degenerate(self):
        report = _report()
        self.assertEqual(report["published_audited"], 8)
        self.assertEqual(report["validator_accepted_audited"], 10)
        self.assertAlmostEqual(report["entity_precision"], 0.8)
        self.assertAlmostEqual(report["metric_precision"], 0.875)

    def test_audit_size_gate_uses_minimum_audit(self):
        profiles, observations, labels = _fixture()
        self.assertFalse(build_report(profiles, observations, labels, minimum_audit=100)["audit_size_gate"])
        self.assertTrue(build_report(profiles, observations, labels, minimum_audit=12)["audit_size_gate"])

    def test_duplicate_label_ids_are_rejected(self):
        profiles, observations, labels = _fixture()
        labels.append(_label(id="s1"))
        with self.assertRaises(ValueError):
            build_report(profiles, observations, labels)

    def test_same_inputs_produce_byte_identical_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            paths = _write_fixture(directory)
            first = directory / "first.json"
            second = directory / "second.json"
            for output in (first, second):
                subprocess.run(
                    [sys.executable, str(SCRIPT), "--profiles", str(paths["profiles"]), "--observations", str(paths["observations"]),
                     "--labels", str(paths["labels"]), "--output", str(output)],
                    check=True, capture_output=True, text=True, cwd=str(ROOT),
                )
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_report_has_no_timestamp_like_field(self):
        report = _report()
        for key in report:
            self.assertNotIn("time", key.lower())
            self.assertNotIn("date", key.lower())


if __name__ == "__main__":
    unittest.main()
