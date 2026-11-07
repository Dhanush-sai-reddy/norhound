#!/usr/bin/env python3
"""Measure company recall per official fact family, the way the rubric counts it.

The challenge scores Recall/50 as company recall per fact family against the
union of every participant's and Builderr's discoveries. A family with 577
opportunities is one where 577 of the 1,000 companies have a match somewhere
in that union; the score for the family is the share of those companies for
which we publish at least one fact of that family.

This script is additive: it does not change the pipeline, the publication gate
or `scripts/measure_recall.py`. It reads the published contract envelopes,
because the envelope is the publication surface and its claims carry the
family they belong to, and it reports:

* `family_company_recall` - covered companies, opportunities and recall for
  every official family, including `reviews`.
* `scored_family_recall_proxy_50` - the opportunity-weighted mean of the
  scored families, in points out of 50. `reviews` is left out of the headline
  because the rubric does not score ratings, reviews or sentiment, and the
  keyless sources cover at most 32 of the 323 companies that have one
  (`docs/evidence/keyless-review-sources.md`). The review numbers are still
  reported, so the choice is visible rather than baked in.
* `scored_group_recall` - the same families grouped into the six decision
  families the brief names: identity, accounts, people, website, hiring and
  activity.

The report carries no timestamp and no unordered iteration, so the same
inputs always produce a byte-identical report.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any, Iterable

# The official evaluation set is 1,000 companies. The opportunity counts are
# the number of companies for which that family has a match somewhere in the
# union of all participants' and Builderr's discoveries (the challenge corpus
# family counts recorded in AGENTS.md).
EVALUATION_BATCH_SIZE = 1000

OFFICIAL_FAMILY_OPPORTUNITIES: dict[str, int] = {
    "identity": 1000,
    "roles": 1000,
    "financials": 1000,
    "other": 1000,
    "news": 998,
    "website": 577,
    "reviews": 323,
    "social": 177,
    "hiring": 84,
}

# Every family the rubric scores. `reviews` is excluded on purpose: the rubric
# does not score ratings, reviews or sentiment, and no keyless source reaches
# more than 32 of the 323 companies that have a rating.
SCORED_FAMILIES: tuple[str, ...] = (
    "identity",
    "financials",
    "roles",
    "website",
    "hiring",
    "news",
    "other",
    "social",
)

# The six decision families named in the brief, mapped onto the official
# families. `activity` is the dated and undated activity of a company: news,
# other and social.
SCORED_FAMILY_GROUPS: dict[str, tuple[str, ...]] = {
    "identity": ("identity",),
    "accounts": ("financials",),
    "people": ("roles",),
    "website": ("website",),
    "hiring": ("hiring",),
    "activity": ("news", "other", "social"),
}


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = sanitize_line_separators(path.read_text(encoding="utf-8"))
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def scale_opportunities(batch_size: int) -> dict[str, int]:
    """The official opportunity counts, scaled to the batch actually measured.

    The counts belong to the 1,000-company evaluation set. A smaller batch is
    a subset of it, so the denominator is scaled proportionally; the counts
    stay integers and never fall below one.
    """
    if batch_size <= 0:
        return {family: 0 for family in OFFICIAL_FAMILY_OPPORTUNITIES}
    if batch_size == EVALUATION_BATCH_SIZE:
        return dict(OFFICIAL_FAMILY_OPPORTUNITIES)
    return {
        family: max(1, round(count * batch_size / EVALUATION_BATCH_SIZE))
        for family, count in OFFICIAL_FAMILY_OPPORTUNITIES.items()
    }


def covered_companies(envelopes: list[dict[str, Any]]) -> dict[str, set[str]]:
    """The companies that publish at least one claim of each family."""
    covered: dict[str, set[str]] = {family: set() for family in OFFICIAL_FAMILY_OPPORTUNITIES}
    for envelope in envelopes:
        org = str(envelope.get("organisation_number") or "").strip()
        if not org:
            continue
        for claim in envelope.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            family = str(claim.get("family") or "").strip()
            if family in covered:
                covered[family].add(org)
    return covered


# Hosts that serve the Norwegian register itself. Everything else is a source
# outside the register: the company's own site, a public directory, a job
# board, a public identity registry.
REGISTRY_HOSTS = {"brreg.no", "data.brreg.no", "w2.brreg.no", "www.brreg.no"}


def is_registry_source(url: str) -> bool:
    """True when the evidence came from the Norwegian company register."""
    host = (urllib.parse.urlparse(str(url or "")).hostname or "").lower()
    return host in REGISTRY_HOSTS or host.endswith(".brreg.no")


def claim_is_external(claim: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> bool:
    """True when at least one piece of evidence for the claim is outside the register.

    A claim with no resolvable evidence is not counted as external: the point
    of the external measurement is to prove that a fact came from somewhere
    other than the register, and an unresolved reference proves nothing.
    """
    for evidence_id in claim.get("evidence_ids") or []:
        evidence = evidence_by_id.get(str(evidence_id))
        if evidence is None:
            continue
        if not is_registry_source(str(evidence.get("source_url") or "")):
            return True
    return False


def covered_companies_external(envelopes: list[dict[str, Any]]) -> dict[str, set[str]]:
    """The companies that publish at least one claim backed by a non-register source."""
    covered: dict[str, set[str]] = {family: set() for family in OFFICIAL_FAMILY_OPPORTUNITIES}
    for envelope in envelopes:
        org = str(envelope.get("organisation_number") or "").strip()
        if not org:
            continue
        evidence_by_id = {
            str(record.get("id")): record
            for record in (envelope.get("evidence") or [])
            if isinstance(record, dict)
        }
        for claim in envelope.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            family = str(claim.get("family") or "").strip()
            if family in covered and claim_is_external(claim, evidence_by_id):
                covered[family].add(org)
    return covered


def family_recall(
    covered: dict[str, set[str]], opportunities: dict[str, int]
) -> dict[str, dict[str, Any]]:
    """Covered companies, opportunities and recall for every family."""
    report: dict[str, dict[str, Any]] = {}
    for family in sorted(opportunities):
        total = opportunities[family]
        hits = len(covered.get(family, set()))
        report[family] = {
            "covered": hits,
            "opportunities": total,
            "recall": (hits / total) if total else 0.0,
        }
    return report


def opportunity_weighted_mean(
    recalls: dict[str, float],
    opportunities: dict[str, int],
    families: Iterable[str],
) -> float:
    """The family recalls averaged in proportion to their opportunity counts."""
    members = [family for family in families if opportunities.get(family)]
    total = sum(opportunities[family] for family in members)
    if not total:
        return 0.0
    weighted = sum(recalls.get(family, 0.0) * opportunities[family] for family in members)
    return weighted / total


def group_recall(
    recalls: dict[str, dict[str, Any]],
    opportunities: dict[str, int],
) -> dict[str, dict[str, Any]]:
    """The six decision families, each the weighted mean of its members."""
    report: dict[str, dict[str, Any]] = {}
    for group in sorted(SCORED_FAMILY_GROUPS):
        members = SCORED_FAMILY_GROUPS[group]
        score = opportunity_weighted_mean(
            {family: recalls[family]["recall"] for family in members},
            opportunities,
            members,
        )
        report[group] = {
            "families": list(members),
            "opportunities": sum(opportunities.get(family, 0) for family in members),
            "recall": score,
        }
    return report


def metric_definitions() -> dict[str, str]:
    """One line per reported metric, so no consumer has to guess a denominator."""
    return {
        "companies": "Distinct organisation numbers in the measured envelopes.",
        "batch_size": "The batch the measurement ran on; the opportunity counts are scaled to it.",
        "opportunities": "Official per-family opportunity counts (companies with a match in the union of all participants' and Builderr's discoveries), scaled to the batch size.",
        "family_company_recall": "Per family: companies publishing at least one claim of that family, the opportunity count, and covered/opportunities.",
        "scored_family_recall": "family_company_recall restricted to the scored families.",
        "scored_family_recall_proxy_50": "Opportunity-weighted mean of the scored families' recall, in points out of 50. The rubric's other half (claim recall against the union) is not computable without the official union, so this is the company-recall half only.",
        "scored_group_recall": "The six decision families (identity, accounts, people, website, hiring, activity), each the opportunity-weighted mean of its official families.",
        "scored_group_recall_proxy_50": "Opportunity-weighted mean of the six decision families' recall, in points out of 50.",
        "reviews_excluded_from_headline": "True: the rubric does not score ratings, reviews or sentiment, and the keyless sources reach at most 32 of the 323 review opportunities.",
        "claims_without_family": "Published claims that carry no family; they count towards no family.",
        "external_family_company_recall": "Per family: companies publishing at least one claim of that family whose evidence comes from a source outside the Norwegian register (data.brreg.no, w2.brreg.no). A claim with no resolvable evidence is not counted as external.",
        "scored_external_family_recall_proxy_50": "The external-only family recalls, opportunity-weighted, in points out of 50. This is the number that tracks external recall: the all-claims variant counts the register's own facts, which every company has.",
        "external_scored_group_recall": "The six decision families, restricted to claims backed by a non-register source.",
        "scored_external_group_recall_proxy_50": "The external-only six decision families, opportunity-weighted, in points out of 50.",
        "metric_definitions": "This mapping.",
    }


def build_report(envelopes: list[dict[str, Any]], batch_size: int = EVALUATION_BATCH_SIZE) -> dict[str, Any]:
    organisations = {
        str(envelope.get("organisation_number") or "").strip()
        for envelope in envelopes
    }
    organisations.discard("")
    if batch_size <= 0:
        batch_size = len(organisations)

    opportunities = scale_opportunities(batch_size)
    covered = covered_companies(envelopes)
    recalls = family_recall(covered, opportunities)
    external_covered = covered_companies_external(envelopes)
    external_recalls = family_recall(external_covered, opportunities)
    scored = {family: recalls[family] for family in SCORED_FAMILIES}
    groups = group_recall(recalls, opportunities)
    external_groups = group_recall(external_recalls, opportunities)

    claims_without_family = 0
    for envelope in envelopes:
        for claim in envelope.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            family = str(claim.get("family") or "").strip()
            if family not in OFFICIAL_FAMILY_OPPORTUNITIES:
                claims_without_family += 1

    return {
        "scorer": "norhound_family_recall_measurement_v1",
        "claim_boundary": "Company recall per family over the published contract envelopes; the rubric's claim-recall half needs the official union and is not computed here.",
        "companies": len(organisations),
        "batch_size": batch_size,
        "opportunities": opportunities,
        "family_company_recall": recalls,
        "scored_family_recall": scored,
        "scored_family_recall_proxy_50": opportunity_weighted_mean(
            {family: recalls[family]["recall"] for family in SCORED_FAMILIES},
            opportunities,
            SCORED_FAMILIES,
        ) * 50,
        "scored_group_recall": groups,
        "scored_group_recall_proxy_50": opportunity_weighted_mean(
            {group: value["recall"] for group, value in groups.items()},
            {group: value["opportunities"] for group, value in groups.items()},
            tuple(groups),
        ) * 50,
        "reviews_excluded_from_headline": True,
        "claims_without_family": claims_without_family,
        "external_family_company_recall": external_recalls,
        "scored_external_family_recall_proxy_50": opportunity_weighted_mean(
            {family: external_recalls[family]["recall"] for family in SCORED_FAMILIES},
            opportunities,
            SCORED_FAMILIES,
        ) * 50,
        "external_scored_group_recall": external_groups,
        "scored_external_group_recall_proxy_50": opportunity_weighted_mean(
            {group: value["recall"] for group, value in external_groups.items()},
            {group: value["opportunities"] for group, value in external_groups.items()},
            tuple(external_groups),
        ) * 50,
        "metric_definitions": metric_definitions(),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Measure company recall per official fact family."
    )
    parser.add_argument("--envelopes", required=True, help="Published contract envelopes JSONL")
    parser.add_argument("--output", required=True, help="Where to write the JSON report")
    parser.add_argument("--batch-size", type=int, default=0, help="Batch size the opportunity counts are scaled to (default: the number of companies in the envelopes)")
    args = parser.parse_args(argv)

    envelopes = read_jsonl(Path(args.envelopes))
    report = build_report(envelopes, batch_size=args.batch_size)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
