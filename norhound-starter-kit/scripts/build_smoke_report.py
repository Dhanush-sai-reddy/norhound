#!/usr/bin/env python3
"""Build the 100-company smoke-test deliverable from a finished run.

The challenge asks for "a 100-company smoke-test result or run report showing
that your agent returns one complete result per input". This script takes a
completed run directory and emits that report without re-running the pipeline:

* `smoke-envelopes.jsonl` — one terminal envelope per requested organisation
* `smoke-report.json` — requested vs returned, every missing or duplicated
  organisation, and the per-company claim/evidence/source counts

The selection is deterministic (organisation numbers sorted, first `--count`)
so the same run always yields the same smoke test. Completeness is checked
against the contract, not assumed: an envelope only counts when it carries the
organisation number, at least one claim, at least one evidence record, and
every claim names a source URL and a retrieval time.

Usage:
    python scripts/build_smoke_report.py \
        --run-dir out/run-fresh-20261116T102232Z \
        --count 100 \
        --output-dir out/smoke-100

Exit code is 1 when the smoke test is incomplete, so it can gate a submission.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def envelope_problems(envelope: dict[str, Any]) -> list[str]:
    """Contract checks for one terminal envelope.

    Claims do not carry a URL themselves: they point at evidence records by id,
    and the evidence record is what holds source_url, retrieved_at and the
    content hash. So completeness means every claim resolves to evidence, and
    every referenced evidence record is fully cited.
    """
    problems: list[str] = []
    if not str(envelope.get("organisation_number") or "").strip():
        problems.append("missing organisation_number")

    claims = envelope.get("claims") or []
    if not claims:
        problems.append("no claims")

    evidence = envelope.get("evidence") or []
    if not evidence:
        problems.append("no evidence")

    by_id = {str(item.get("id")): item for item in evidence if item.get("id")}
    unresolved = 0
    uncited = 0
    for claim in claims:
        availability = str(claim.get("availability") or "available")
        if availability != "available":
            # Explicit absence states (not_available / blocked / failed) are
            # correct by design and carry no evidence.
            continue
        ids = claim.get("evidence_ids") or []
        if not ids:
            unresolved += 1
            continue
        for evidence_id in ids:
            record = by_id.get(str(evidence_id))
            if record is None:
                unresolved += 1
                continue
            if not str(record.get("source_url") or "").strip() or not str(record.get("retrieved_at") or "").strip():
                uncited += 1
    if unresolved:
        problems.append(f"{unresolved} claim(s) without a resolvable evidence record")
    if uncited:
        problems.append(f"{uncited} evidence record(s) without source_url or retrieved_at")
    return problems


def build(run_dir: Path, count: int, output_dir: Path) -> dict[str, Any]:
    manifest = run_dir / "entry.jsonl"
    envelopes_path = run_dir / "envelopes-final.jsonl"
    if not manifest.exists():
        raise SystemExit(f"missing manifest: {manifest}")
    if not envelopes_path.exists():
        raise SystemExit(f"missing envelopes: {envelopes_path}")

    requested = sorted(
        {
            str(row.get("organisation_number") or "").zfill(9)
            for row in read_jsonl(manifest)
            if str(row.get("organisation_number") or "").strip()
        }
    )[:count]
    wanted = set(requested)

    by_org: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for envelope in read_jsonl(envelopes_path):
        org = str(envelope.get("organisation_number") or "").zfill(9)
        if org not in wanted:
            continue
        if org in by_org:
            duplicates.append(org)
            continue
        by_org[org] = envelope

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "smoke-envelopes.jsonl").open("w", encoding="utf-8") as handle:
        for org in requested:
            if org in by_org:
                handle.write(json.dumps(by_org[org], ensure_ascii=False) + "\n")

    missing: list[str] = []
    incomplete: dict[str, list[str]] = {}
    per_company: list[dict[str, Any]] = []
    for org in requested:
        envelope = by_org.get(org)
        if envelope is None:
            missing.append(org)
            continue
        problems = envelope_problems(envelope)
        if problems:
            incomplete[org] = problems
        claims = envelope.get("claims") or []
        evidence = envelope.get("evidence") or []
        per_company.append(
            {
                "organisation_number": org,
                "claims": len(claims),
                "evidence": len(evidence),
                "source_hosts": sorted(
                    {
                        str(item.get("source_url") or "").split("/")[2]
                        for item in evidence
                        if str(item.get("source_url") or "").count("/") >= 2
                    }
                ),
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_run": run_dir.name,
        "requested": len(requested),
        "returned": len(by_org),
        "complete": not missing and not incomplete and not duplicates,
        "missing": missing,
        "duplicated": sorted(set(duplicates)),
        "incomplete": incomplete,
        "claims_total": sum(row["claims"] for row in per_company),
        "evidence_total": sum(row["evidence"] for row in per_company),
        "per_company": per_company,
        "selection": "organisation numbers sorted ascending, first N of the run manifest",
    }
    (output_dir / "smoke-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit the 100-company smoke-test deliverable from a finished run.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    report = build(args.run_dir, args.count, args.output_dir)
    summary = {key: report[key] for key in ("source_run", "requested", "returned", "complete", "claims_total", "evidence_total")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if report["missing"]:
        print(f"missing organisations: {report['missing'][:10]}")
    if report["incomplete"]:
        print(f"incomplete envelopes: {list(report['incomplete'])[:10]}")
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
