#!/usr/bin/env python3
"""Measure reproducible exact-company recall for the Signalpost submission.

This is an additive measurement tool. It does not change the pipeline, the
publication gate, or `scripts/evaluate_external_footprint.py`.

Definitions used here (stated once so the numbers are auditable):

* A row is *validator-accepted* when `publishable_observation(row)` is true.
* A row is *published* when it is validator-accepted **and** its audit label
  says `exact_entity` is truthy. Unlabelled rows are never published.
* `coverage` is computed with exactly the same rules and signal sets as
  `scripts/evaluate_external_footprint.py`, so the two reports are comparable.
* `direct_reviewer_gaps` counts organisations (not rows) that have at least one
  published row of the requested kind, so a row can only ever be counted once
  per organisation per gap.
* `entity_precision` = published rows / validator-accepted audited rows, so a
  wrong-company row that passed the validator lowers the score instead of
  being hidden by the denominator (`wrong_entity_publications` counts those
  rows). `metric_precision` = published rows the audit marked metric-correct /
  published rows. `unsupported_publications` counts published rows that fail
  `validate_observation`; with the current validator this is structurally zero.
* The report contains no timestamp and no unordered iteration, so the same
  inputs always produce a byte-identical report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import publishable_observation, validate_observation  # noqa: E402

# Signal sets copied from scripts/evaluate_external_footprint.py so that the
# coverage numbers stay directly comparable with the existing scorer.
WORKFORCE_SIGNALS = {"job_posting", "workforce_snapshot"}
REVIEW_SIGNALS = {"review", "review_summary", "place_summary"}
BUZZ_SIGNALS = {"public_post", "public_mention", "profile_metrics"}

GAP_SIGNAL_TYPES = {
    "social_profile": "profile_handle",
    "dated_news": "public_post",
    "hiring": "job_posting",
}


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def label_map(label_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for row in label_rows:
        key = str(row.get("id"))
        if key in labels:
            raise ValueError("Label IDs must be unique")
        labels[key] = row
    return labels


def is_published(item: dict[str, Any], labels: dict[str, dict[str, Any]]) -> bool:
    """Published = validator-accepted *and* audited as the exact legal entity."""
    label = labels.get(str(item.get("id")))
    if label is None:
        return False
    return bool(publishable_observation(item) and label.get("exact_entity"))


def is_machine_readable_date(value: Any) -> bool:
    """True for an ISO-8601 date or datetime string (date-only is enough)."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def has_publication_date(item: dict[str, Any]) -> bool:
    """A public_post only counts as dated news when it carries a machine-readable date."""
    metrics = item.get("metrics") or {}
    for value in (metrics.get("published_at"), metrics.get("published_date"), item.get("published_at")):
        if is_machine_readable_date(value):
            return True
    return False


def compute_coverage(published: list[dict[str, Any]], organisations: list[str]) -> dict[str, float]:
    platforms: dict[str, set[str]] = {org: set() for org in organisations}
    signals: dict[str, set[str]] = {org: set() for org in organisations}
    sentiment_orgs: set[str] = set()
    for item in published:
        org = str(item.get("organisation_number"))
        if org not in platforms:
            continue
        platforms[org].add(str(item.get("platform")))
        signals[org].add(str(item.get("signal_type")))
        if item.get("sentiment_label"):
            sentiment_orgs.add(org)
    total = len(organisations)
    return {
        "any_external": ratio(sum(bool(platforms[org]) for org in organisations), total),
        "two_platforms": ratio(sum(len(platforms[org]) >= 2 for org in organisations), total),
        "workforce_jobs": ratio(sum(bool(signals[org] & WORKFORCE_SIGNALS) for org in organisations), total),
        "ratings_reviews": ratio(sum(bool(signals[org] & REVIEW_SIGNALS) for org in organisations), total),
        "buzz_engagement": ratio(sum(bool(signals[org] & BUZZ_SIGNALS) for org in organisations), total),
        "sentiment": ratio(sum(org in sentiment_orgs for org in organisations), total),
    }


def compute_gaps(published: list[dict[str, Any]], organisations: list[str]) -> tuple[dict[str, int], dict[str, float]]:
    known = set(organisations)
    gap_orgs: dict[str, set[str]] = {name: set() for name in GAP_SIGNAL_TYPES}
    for item in published:
        org = str(item.get("organisation_number"))
        if org not in known:
            continue
        signal_type = str(item.get("signal_type"))
        if signal_type == GAP_SIGNAL_TYPES["social_profile"]:
            gap_orgs["social_profile"].add(org)
        elif signal_type == GAP_SIGNAL_TYPES["dated_news"]:
            if has_publication_date(item):
                gap_orgs["dated_news"].add(org)
        elif signal_type == GAP_SIGNAL_TYPES["hiring"]:
            gap_orgs["hiring"].add(org)
    counts = {name: len(gap_orgs[name]) for name in sorted(gap_orgs)}
    ratios = {name: ratio(counts[name], len(organisations)) for name in counts}
    return counts, ratios


def build_report(
    profiles: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
    minimum_audit: int = 100,
) -> dict[str, Any]:
    labels = label_map(label_rows)
    organisations = sorted({str(item.get("organisation_number")) for item in profiles})

    audited = [item for item in observations if str(item.get("id")) in labels]
    accepted_audited = [item for item in audited if publishable_observation(item)]
    published = [item for item in observations if is_published(item, labels)]
    unlabelled_publishable = sum(
        1 for item in observations if str(item.get("id")) not in labels and publishable_observation(item)
    )

    wrong_entity = len(accepted_audited) - len(published)
    unsupported = sum(1 for item in published if validate_observation(item))
    wrong_metric = sum(1 for item in published if not labels[str(item.get("id"))].get("metric_correct", False))

    coverage = compute_coverage(published, organisations)
    recall_proxy_50 = sum(coverage.values()) / len(coverage) * 50
    gap_counts, gap_ratios = compute_gaps(published, organisations)
    gap_score = sum(gap_ratios.values()) / len(gap_ratios)

    return {
        "scorer": "norhound_recall_measurement_v1",
        "claim_boundary": "Held-out observation audit plus full-corpus coverage; it does not validate an unlabelled connector.",
        "profiles": len(profiles),
        "profile_organisations": len(organisations),
        "observations": len(observations),
        "labelled_observations": len(labels),
        "audited_observations": len(audited),
        "validator_accepted_audited": len(accepted_audited),
        "published_audited": len(published),
        "unlabelled_publishable_observations": unlabelled_publishable,
        "wrong_entity_publications": wrong_entity,
        "unsupported_publications": unsupported,
        "entity_precision": ratio(len(published), len(accepted_audited)),
        "metric_precision": ratio(len(published) - wrong_metric, len(published)),
        "coverage": coverage,
        "recall_proxy_50": recall_proxy_50,
        "direct_reviewer_gaps": gap_counts,
        "direct_reviewer_gap_ratios": gap_ratios,
        "direct_reviewer_gap_base_profiles": len(organisations),
        "direct_reviewer_gap_score": gap_score,
        "minimum_audit": minimum_audit,
        "audit_size_gate": len(labels) >= minimum_audit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure reproducible exact-company recall and direct reviewer gaps.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--labels", required=True, help="JSONL: id, exact_entity, metric_correct, sentiment_correct")
    parser.add_argument("--output", required=True)
    parser.add_argument("--minimum-audit", type=int, default=100)
    args = parser.parse_args()

    report = build_report(
        read_jsonl(Path(args.profiles)),
        read_jsonl(Path(args.observations)),
        read_jsonl(Path(args.labels)),
        minimum_audit=args.minimum_audit,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
