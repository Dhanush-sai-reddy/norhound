from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import measure_recall

build_report = measure_recall.build_report
has_publication_date = measure_recall.has_publication_date

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure_recall.py"
EVALUATOR = ROOT / "scripts" / "evaluate_external_footprint.py"

ORG_A = "810034882"
ORG_B = "812702432"
ORG_C = "913460086"
ORG_OUTSIDE = "999999999"


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
    """Three companies, one out-of-profile organisation, one unlabelled row.

    Organisation A carries the social, hiring and metrics.published_at evidence;
    B carries the public_mention and review_summary evidence (and no public_post,
    so buzz coverage must depend on public_mention); C carries the top-level
    published_at and the sentiment row.
    """
    observations = [
        # --- social profiles: A twice (once per organisation), B wrong entity, C unpublishable ---
        _observation(id="s1", organisation_number=ORG_A, platform="linkedin", signal_type="profile_handle"),
        _observation(id="s2", organisation_number=ORG_A, platform="facebook", signal_type="profile_handle"),
        _observation(id="s3", organisation_number=ORG_B, platform="linkedin", signal_type="profile_handle"),
        _observation(id="s4", organisation_number=ORG_C, platform="x", signal_type="profile_handle", rights_status="pending"),
        # --- news: A via metrics.published_at, C via top-level published_at ---
        _observation(id="d1", organisation_number=ORG_A, metrics={"published_at": "2026-01-02T10:00:00Z"}),
        _observation(id="d2", organisation_number=ORG_A, metrics={"published_at": "2026-02-03"}),
        _observation(id="d4", organisation_number=ORG_C, published_at="2026-04-05T08:00:00Z"),
        # --- BRREG registry announcement: dated only in signal.date, never in dated_news ---
        _observation(id="reg1", organisation_number=ORG_A, platform="brreg", signal={"date": "2026-08-20", "title": "Fusjonsbeslutning"}),
        # --- buzz via public_mention and reviews via review_summary ---
        _observation(id="b1", organisation_number=ORG_B, platform="company_directory", signal_type="public_mention"),
        _observation(id="r1", organisation_number=ORG_B, platform="company_directory", signal_type="review_summary"),
        # --- sentiment row ---
        _observation(
            id="t1",
            organisation_number=ORG_C,
            platform="company_directory",
            signal_type="sentiment",
            source_class="customer_review",
            sentiment_label="positive",
            sentiment_model_version="rules-v1",
        ),
        # --- hiring: A twice, B unpublishable, C wrong entity ---
        _observation(id="h1", organisation_number=ORG_A, platform="job_board", signal_type="job_posting"),
        _observation(id="h2", organisation_number=ORG_A, platform="job_board", signal_type="job_posting"),
        _observation(id="h3", organisation_number=ORG_B, platform="job_board", signal_type="job_posting", rights_status="pending"),
        _observation(id="h4", organisation_number=ORG_C, platform="job_board", signal_type="job_posting"),
        # --- published row for an organisation that is not in the profile file ---
        _observation(id="x1", organisation_number=ORG_OUTSIDE, platform="job_board", signal_type="job_posting"),
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
        _label(id="d4"),
        _label(id="reg1"),
        _label(id="b1"),
        _label(id="r1", metric_correct=0),
        _label(id="t1", sentiment_correct=0),
        _label(id="h1"),
        _label(id="h2"),
        _label(id="h3"),
        _label(id="h4", exact_entity=0, metric_correct=0),
        _label(id="x1"),
    ]
    return _profiles(), observations, labels


def _report():
    profiles, observations, labels = _fixture()
    return build_report(profiles, observations, labels)


def _single_org_report(observations, labels, org=ORG_A):
    return build_report([{"organisation_number": org, "name": "EN AS"}], observations, labels)


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

    def test_gap_key_order_follows_the_brief(self):
        report = _report()
        self.assertEqual(list(report["direct_reviewer_gaps"]), ["social_profile", "dated_news", "hiring"])
        self.assertEqual(list(report["direct_reviewer_gap_ratios"]), ["social_profile", "dated_news", "hiring"])

    def test_rejected_and_wrong_entity_rows_are_never_counted(self):
        report = _report()
        # s3 and h4 are labelled "not the exact entity"; s4 and h3 fail validation.
        # Only organisation A may appear in the social and hiring gap counts.
        self.assertEqual(report["direct_reviewer_gaps"]["social_profile"], 1)
        self.assertEqual(report["direct_reviewer_gaps"]["hiring"], 1)
        self.assertEqual(report["wrong_entity_publications"], 0)
        self.assertEqual(report["unsupported_publications"], 0)
        self.assertEqual(report["withheld_wrong_entity_rows"], 2)

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

    def test_publication_date_detector_survives_a_non_dict_metrics_field(self):
        self.assertFalse(has_publication_date({"metrics": ["x"]}))
        self.assertFalse(has_publication_date({"metrics": "2026-01-02"}))
        self.assertFalse(has_publication_date({"metrics": None}))
        # A top-level published_at is still accepted when metrics is not a dict.
        self.assertTrue(has_publication_date({"metrics": ["x"], "published_at": "2026-01-02"}))

    def test_undated_public_post_is_not_dated_news(self):
        observation = _observation(id="p1", metrics={})
        report = _single_org_report([observation], [_label(id="p1")])
        self.assertEqual(report["direct_reviewer_gaps"]["dated_news"], 0)

    def test_registry_announcement_is_reported_separately_from_dated_news(self):
        observation = _observation(id="reg", platform="brreg", signal={"date": "2026-08-20", "title": "Fusjonsbeslutning"})
        report = _single_org_report([observation], [_label(id="reg")])
        self.assertEqual(report["direct_reviewer_gaps"]["dated_news"], 0)
        self.assertEqual(report["dated_registry_announcements"], 1)
        self.assertAlmostEqual(report["dated_registry_announcements_ratio"], 1.0)

    def test_registry_announcement_does_not_join_dated_news_when_a_strict_date_exists(self):
        observations = [
            _observation(id="reg", platform="brreg", signal={"date": "2026-08-20"}),
            _observation(id="post", metrics={"published_at": "2026-01-02T10:00:00Z"}),
        ]
        report = _single_org_report(observations, [_label(id="reg"), _label(id="post")])
        self.assertEqual(report["direct_reviewer_gaps"]["dated_news"], 1)
        self.assertEqual(report["dated_registry_announcements"], 1)


class MeasureRecallCoverageTests(unittest.TestCase):
    def test_coverage_values_are_exact(self):
        report = _report()
        self.assertEqual(
            report["coverage"],
            {
                "any_external": 1.0,
                "two_platforms": 2 / 3,
                "workforce_jobs": 1 / 3,
                "ratings_reviews": 1 / 3,
                "buzz_engagement": 1.0,
                "sentiment": 1 / 3,
            },
        )

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
        self.assertEqual(mine_report["published_audited"], their_report["published_audited"])
        self.assertEqual(
            list(mine_report["coverage"]),
            ["any_external", "two_platforms", "workforce_jobs", "ratings_reviews", "buzz_engagement", "sentiment"],
        )

    def test_ratings_reviews_counts_review_summary_rows(self):
        report = _report()
        self.assertAlmostEqual(report["coverage"]["ratings_reviews"], 1 / 3)

    def test_buzz_engagement_counts_public_mention_rows(self):
        report = _report()
        self.assertAlmostEqual(report["coverage"]["buzz_engagement"], 1.0)
        organisation_b = _observation(id="b2", organisation_number=ORG_B, platform="company_directory", signal_type="public_mention")
        single = _single_org_report([organisation_b], [_label(id="b2")], org=ORG_B)
        self.assertAlmostEqual(single["coverage"]["buzz_engagement"], 1.0)

    def test_sentiment_coverage_counts_sentiment_rows(self):
        report = _report()
        self.assertAlmostEqual(report["coverage"]["sentiment"], 1 / 3)

    def test_sentiment_label_detector_requires_a_truthy_label(self):
        detector = measure_recall.has_sentiment_label
        self.assertTrue(detector({"sentiment_label": "positive"}))
        self.assertFalse(detector({"sentiment_label": ""}))
        self.assertFalse(detector({"sentiment_label": None}))
        self.assertFalse(detector({}))

    def test_out_of_profile_organisation_moves_no_organisation_metric(self):
        profiles, observations, labels = _fixture()
        with_outside = build_report(profiles, observations, labels)
        without_outside = build_report(profiles, [row for row in observations if row["id"] != "x1"], [row for row in labels if row["id"] != "x1"])
        self.assertEqual(with_outside["coverage"], without_outside["coverage"])
        self.assertEqual(with_outside["direct_reviewer_gaps"], without_outside["direct_reviewer_gaps"])
        self.assertEqual(with_outside["direct_reviewer_gap_score"], without_outside["direct_reviewer_gap_score"])
        self.assertEqual(with_outside["profile_organisations"], without_outside["profile_organisations"])
        self.assertEqual(with_outside["direct_reviewer_gaps"]["hiring"], 1)

    def test_organisation_signals_helper_excludes_unknown_organisations(self):
        observations = [
            _observation(id="s1", organisation_number=ORG_A, signal_type="profile_handle"),
            _observation(id="x1", organisation_number=ORG_OUTSIDE, signal_type="profile_handle"),
        ]
        platforms, signals = measure_recall.collect_organisation_signals(observations, [ORG_A])
        self.assertIn(ORG_A, platforms)
        self.assertNotIn(ORG_OUTSIDE, platforms)
        self.assertNotIn(ORG_OUTSIDE, signals)

    def test_profile_without_organisation_number_is_skipped(self):
        profiles, observations, labels = _fixture()
        profiles = profiles + [{"name": "ORGANS WITHOUT NUMBER AS"}]
        report = build_report(profiles, observations, labels)
        self.assertEqual(report["profiles"], 4)
        self.assertEqual(report["profile_organisations"], 3)
        self.assertEqual(report["profiles_missing_organisation_number"], 1)
        self.assertAlmostEqual(report["coverage"]["two_platforms"], 2 / 3)

    def test_recall_proxy_is_mean_of_coverage_times_fifty(self):
        report = _report()
        expected = sum(report["coverage"].values()) / len(report["coverage"]) * 50
        self.assertAlmostEqual(report["recall_proxy_50"], expected)


class MeasureRecallReportTests(unittest.TestCase):
    def test_canonical_precision_keys_keep_canonical_semantics(self):
        report = _report()
        self.assertEqual(report["wrong_entity_publications"], 0)
        self.assertEqual(report["entity_precision"], 1.0)
        self.assertAlmostEqual(report["metric_precision"], 11 / 12)

    def test_withheld_rows_and_accepted_entity_yield_are_reported_separately(self):
        report = _report()
        self.assertEqual(report["withheld_wrong_entity_rows"], 2)
        self.assertAlmostEqual(report["accepted_entity_yield"], 12 / 14)

    def test_sentiment_accuracy_is_reported(self):
        report = _report()
        self.assertEqual(report["sentiment_audited"], 1)
        self.assertEqual(report["sentiment_accuracy"], 0.0)

    def test_sentiment_accuracy_is_null_without_sentiment_rows(self):
        report = build_report(_profiles(), [], [])
        self.assertEqual(report["sentiment_audited"], 0)
        self.assertIsNone(report["sentiment_accuracy"])

    def test_metric_definitions_document_every_metric(self):
        report = _report()
        definitions = report["metric_definitions"]
        undocumented = set(report) - set(definitions) - {"scorer", "claim_boundary", "metric_definitions"}
        self.assertEqual(undocumented, set())
        self.assertIn("signal.date", definitions["dated_news"])
        self.assertIn("signal.date", definitions["dated_registry_announcements"])

    def test_audit_size_gate_uses_minimum_audit(self):
        profiles, observations, labels = _fixture()
        self.assertFalse(build_report(profiles, observations, labels, minimum_audit=100)["audit_size_gate"])
        self.assertTrue(build_report(profiles, observations, labels, minimum_audit=16)["audit_size_gate"])

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
            lowered = key.lower()
            self.assertNotIn("timestamp", lowered)
            self.assertNotIn("generated", lowered)
            self.assertNotIn("created", lowered)
            self.assertFalse(lowered.endswith("_at"))


if __name__ == "__main__":
    unittest.main()
