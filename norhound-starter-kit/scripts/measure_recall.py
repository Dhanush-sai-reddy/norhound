#!/usr/bin/env python3
"""Measure reproducible exact-company recall for the Signalpost submission.

This is an additive measurement tool. It does not change the pipeline, the
publication gate, or `scripts/evaluate_external_footprint.py`.

Definitions used here (stated once so the numbers are auditable):

* A row is *validator-accepted* when `publishable_observation(row)` is true.
* A row is *published* when it is validator-accepted **and** its audit label
  says `exact_entity` is truthy. Unlabelled rows are never published.
* `coverage` is computed with exactly the same rules and signal sets as
  `scripts/evaluate_external_footprint.py`, so the numbers are comparable.
* `entity_precision`, `metric_precision`, `wrong_entity_publications` and
  `unsupported_publications` keep the canonical semantics of
  `scripts/evaluate_external_footprint.py`, because downstream consumers
  (`scripts/score_competition_v3.py`, `scripts/build_static_site.py`) read
  those key names. The stricter, non-degenerate measures are published under
  their own names: `withheld_wrong_entity_rows` (validator-accepted audited
  rows the audit could not confirm as the exact legal entity) and
  `accepted_entity_yield` (published / validator-accepted audited rows).
* `direct_reviewer_gaps` counts organisations (not rows) that have at least one
  published row of the requested kind, so a row can only ever be counted once
  per organisation per gap.
* `dated_news` counts only publication dates that a reader can verify on the
  page itself: `metrics.published_at`, `metrics.published_date` or a top-level
  `published_at`. BRREG registry announcements are dated in `signal.date`
  instead; they are official registry events rather than news, so they are
  deliberately **excluded** from `dated_news` and reported separately as
  `dated_registry_announcements`.
* The report contains no timestamp and no unordered iteration, so the same
  inputs always produce a byte-identical report. Every metric carries a
  one-line definition in `metric_definitions`.
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

# Gap order follows the brief: social_profile, dated_news, hiring.
GAP_SIGNAL_TYPES = {
    "social_profile": "profile_handle",
    "dated_news": "public_post",
    "hiring": "job_posting",
}

REGISTRY_PLATFORM = "brreg"


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
    """A public_post counts as dated news only when it carries a publication date.

    The accepted locations are `metrics.published_at`, `metrics.published_date`
    and a top-level `published_at`. A date in `signal.date` (BRREG registry
    announcements) is deliberately not accepted here.
    """
    metrics = item.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    for value in (metrics.get("published_at"), metrics.get("published_date"), item.get("published_at")):
        if is_machine_readable_date(value):
            return True
    return False


def has_sentiment_label(item: dict[str, Any]) -> bool:
    """A truthy sentiment label only: an empty or absent label is not evidence."""
    return bool(item.get("sentiment_label"))


def has_registry_announcement_date(item: dict[str, Any]) -> bool:
    """True when a BRREG announcement row carries a date in `signal.date`."""
    signal = item.get("signal")
    signal = signal if isinstance(signal, dict) else {}
    value = signal.get("date")
    return isinstance(value, str) and bool(value.strip())


def collect_organisation_signals(
    published: list[dict[str, Any]], organisations: list[str]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Per-organisation platform and signal sets, restricted to profiled organisations."""
    known = set(organisations)
    platforms: dict[str, set[str]] = {}
    signals: dict[str, set[str]] = {}
    for item in published:
        org = str(item.get("organisation_number"))
        if org not in known:
            continue
        platforms.setdefault(org, set()).add(str(item.get("platform")))
        signals.setdefault(org, set()).add(str(item.get("signal_type")))
    return platforms, signals


def compute_coverage(published: list[dict[str, Any]], organisations: list[str]) -> dict[str, float]:
    platforms, signals = collect_organisation_signals(published, organisations)
    known = set(organisations)
    sentiment_orgs = {
        str(item.get("organisation_number"))
        for item in published
        if has_sentiment_label(item) and str(item.get("organisation_number")) in known
    }
    total = len(organisations)
    return {
        "any_external": ratio(sum(bool(platforms.get(org)) for org in organisations), total),
        "two_platforms": ratio(sum(len(platforms.get(org, set())) >= 2 for org in organisations), total),
        "workforce_jobs": ratio(sum(bool(signals.get(org, set()) & WORKFORCE_SIGNALS) for org in organisations), total),
        "ratings_reviews": ratio(sum(bool(signals.get(org, set()) & REVIEW_SIGNALS) for org in organisations), total),
        "buzz_engagement": ratio(sum(bool(signals.get(org, set()) & BUZZ_SIGNALS) for org in organisations), total),
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
    counts = {name: len(gap_orgs[name]) for name in GAP_SIGNAL_TYPES}
    ratios = {name: ratio(counts[name], len(organisations)) for name in counts}
    return counts, ratios


def registry_announcement_count(published: list[dict[str, Any]], organisations: list[str]) -> int:
    """Organisations with a published BRREG public_post dated in signal.date."""
    known = set(organisations)
    return len({
        str(item.get("organisation_number"))
        for item in published
        if str(item.get("organisation_number")) in known
        and str(item.get("signal_type")) == GAP_SIGNAL_TYPES["dated_news"]
        and str(item.get("platform")) == REGISTRY_PLATFORM
        and has_registry_announcement_date(item)
    })


def metric_definitions() -> dict[str, str]:
    """One line per published metric, so no consumer has to guess a denominator."""
    return {
        "profiles": "Profile rows read from --profiles.",
        "profile_organisations": "Distinct organisations with a usable organisation_number; the denominator for every coverage ratio.",
        "profiles_missing_organisation_number": "Profile rows skipped because their organisation_number is missing or not a digit string.",
        "observations": "Observation rows read from --observations.",
        "labelled_observations": "Distinct audit label ids read from --labels.",
        "audited_observations": "Observation rows that have an audit label.",
        "validator_accepted_audited": "Audited rows that pass validate_observation.",
        "published_audited": "Validator-accepted audited rows whose label says exact_entity is truthy.",
        "unlabelled_publishable_observations": "Validator-accepted rows with no audit label; they can never be published.",
        "wrong_entity_publications": "Canonical definition: published rows whose audit label is not exact_entity (0 while publication is exact-entity gated).",
        "unsupported_publications": "Canonical definition: published rows that fail validate_observation; structurally 0 because published rows are validator-accepted.",
        "entity_precision": "Canonical definition: (published - wrong_entity_publications) / published.",
        "metric_precision": "Canonical definition: published rows the audit marked metric_correct / published rows.",
        "withheld_wrong_entity_rows": "Validator-accepted audited rows that are not published because the audit could not confirm the exact legal entity.",
        "accepted_entity_yield": "published / validator-accepted audited rows: the share of publishable rows that survive the exact-entity audit.",
        "sentiment_audited": "Published rows that carry a truthy sentiment label.",
        "sentiment_accuracy": "sentiment_correct audited rows / sentiment_audited rows; null when no sentiment row was audited.",
        "coverage": "Per-field organisation coverage over the profile organisation set, computed with the same rules and signal sets as scripts/evaluate_external_footprint.py.",
        "recall_proxy_50": "Mean of the six coverage ratios multiplied by 50 (a proxy: the official Recall/50 field weights are not documented in this tree).",
        "direct_reviewer_gaps": "Organisations with at least one published row per gap kind: social_profile=profile_handle, dated_news=public_post with a publication date, hiring=job_posting.",
        "dated_news": "Organisations with a published public_post row whose date is in metrics.published_at, metrics.published_date or a top-level published_at; BRREG announcements dated only in signal.date are excluded because they are registry events, not news.",
        "direct_reviewer_gap_ratios": "direct_reviewer_gaps divided by the profile organisation count.",
        "direct_reviewer_gap_base_profiles": "Profile organisation count used as the gap denominator.",
        "direct_reviewer_gap_score": "Mean of the three direct_reviewer_gap_ratios (0-1).",
        "dated_registry_announcements": "Organisations with a published public_post row on the brreg platform that carries a date in signal.date.",
        "dated_registry_announcements_ratio": "dated_registry_announcements divided by the profile organisation count.",
        "minimum_audit": "Minimum number of audit labels requested on the command line.",
        "audit_size_gate": "True when the number of audit labels reaches minimum_audit.",
    }


def build_report(
    profiles: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
    minimum_audit: int = 100,
) -> dict[str, Any]:
    labels = label_map(label_rows)

    organisation_numbers: list[str] = []
    profiles_missing_organisation_number = 0
    for profile in profiles:
        raw = profile.get("organisation_number")
        text = str(raw).strip() if raw is not None else ""
        if not text.isdigit():
            profiles_missing_organisation_number += 1
            continue
        organisation_numbers.append(text)
    organisations = sorted(set(organisation_numbers))

    audited = [item for item in observations if str(item.get("id")) in labels]
    accepted_audited = [item for item in audited if publishable_observation(item)]
    published = [item for item in observations if is_published(item, labels)]
    unlabelled_publishable = sum(
        1 for item in observations if str(item.get("id")) not in labels and publishable_observation(item)
    )

    # Canonical precision semantics (scripts/evaluate_external_footprint.py).
    wrong_entity = sum(1 for item in published if not labels[str(item.get("id"))].get("exact_entity"))
    unsupported = sum(1 for item in published if validate_observation(item))
    wrong_metric = sum(1 for item in published if not labels[str(item.get("id"))].get("metric_correct", False))
    sentiment_audited = [item for item in published if has_sentiment_label(item)]
    sentiment_correct = sum(
        1 for item in sentiment_audited if labels[str(item.get("id"))].get("sentiment_correct", False)
    )

    # The stricter measures that the canonical keys cannot express.
    withheld_wrong_entity = len(accepted_audited) - len(published)

    coverage = compute_coverage(published, organisations)
    recall_proxy_50 = sum(coverage.values()) / len(coverage) * 50
    gap_counts, gap_ratios = compute_gaps(published, organisations)
    gap_score = sum(gap_ratios.values()) / len(gap_ratios)
    registry_announcements = registry_announcement_count(published, organisations)

    report = {
        "scorer": "norhound_recall_measurement_v1",
        "claim_boundary": "Held-out observation audit plus full-corpus coverage; it does not validate an unlabelled connector.",
        "metric_definitions": metric_definitions(),
        "profiles": len(profiles),
        "profile_organisations": len(organisations),
        "profiles_missing_organisation_number": profiles_missing_organisation_number,
        "observations": len(observations),
        "labelled_observations": len(labels),
        "audited_observations": len(audited),
        "validator_accepted_audited": len(accepted_audited),
        "published_audited": len(published),
        "unlabelled_publishable_observations": unlabelled_publishable,
        "wrong_entity_publications": wrong_entity,
        "unsupported_publications": unsupported,
        "entity_precision": ratio(len(published) - wrong_entity, len(published)),
        "metric_precision": ratio(len(published) - wrong_metric, len(published)),
        "withheld_wrong_entity_rows": withheld_wrong_entity,
        "accepted_entity_yield": ratio(len(published), len(accepted_audited)),
        "sentiment_audited": len(sentiment_audited),
        "sentiment_accuracy": ratio(sentiment_correct, len(sentiment_audited)) if sentiment_audited else None,
        "coverage": coverage,
        "recall_proxy_50": recall_proxy_50,
        "direct_reviewer_gaps": gap_counts,
        "direct_reviewer_gap_ratios": gap_ratios,
        "direct_reviewer_gap_base_profiles": len(organisations),
        "direct_reviewer_gap_score": gap_score,
        "dated_registry_announcements": registry_announcements,
        "dated_registry_announcements_ratio": ratio(registry_announcements, len(organisations)),
        "minimum_audit": minimum_audit,
        "audit_size_gate": len(labels) >= minimum_audit,
    }
    return report


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
