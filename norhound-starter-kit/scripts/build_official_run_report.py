#!/usr/bin/env python3
"""Build the machine-readable run report for an official run.

The official submission contract asks for "a machine-readable run report with
runtime, request count and third-party cost":

  https://builderr.ai/starter-briefs/signalpost.md  (retrieved 2026-11-17)
  https://builderr.ai/signalpost-starter-kit.tar.gz (retrieved 2026-11-18)

This script reads a finished run directory and writes one JSON file that
answers those three questions and states where each number came from. A number
that was not measured is reported as a bound or as "not instrumented" with the
reason, never as a guess.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def iso(path: Path) -> str | None:
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return stamp.isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def count_jsonl(path: Path) -> tuple[int, int, int, int, int]:
    """Rows, claims, evidence, requests and cost summed over a JSONL file."""
    rows = claims = evidence = requests = 0
    cost = 0.0
    if not path.exists():
        return rows, claims, evidence, requests, int(cost)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(
                    line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
                )
            except json.JSONDecodeError:
                continue
            rows += 1
            claims += len(row.get("claims") or [])
            evidence += len(row.get("evidence") or [])
            operations = row.get("operations") or {}
            requests += int(operations.get("requests") or 0)
            cost += float(operations.get("third_party_cost_usd") or 0)
    return rows, claims, evidence, requests, int(cost)


def build(run_dir: Path) -> dict:
    base = read_json(run_dir / "run-report.json")
    evaluation = read_json(run_dir / "eval-final.json")
    measure = read_json(run_dir / "measure-final.json")
    family = read_json(run_dir / "measure-family-final.json")
    merge = read_json(run_dir / "merge-report.json")
    refresh = read_json(run_dir / "refresh-report.json")
    requests_file = read_json(run_dir / "requests.json")

    envelopes_path = run_dir / "envelopes-final.jsonl"
    observations_path = run_dir / "external-final.jsonl"
    envelopes, claims, evidence, envelope_requests, envelope_cost = count_jsonl(
        envelopes_path
    )
    observations, _, _, _, _ = count_jsonl(observations_path)

    started = parse_iso(base.get("started_at"))
    completed = parse_iso(base.get("completed_at"))
    stamps = []
    for candidate in sorted(run_dir.glob("*")):
        stamp = parse_iso(iso(candidate))
        if stamp:
            stamps.append(stamp)
            if started is None or stamp < started:
                started = stamp
    # The run finishes when its last artifact was written, not when this report
    # is generated: re-reporting an old run must not report the time since.
    if stamps:
        newest = max(stamps)
        if completed is None or newest > completed:
            completed = newest
    if started is None or completed is None:
        completed = datetime.now(timezone.utc)
    runtime_ms = int((completed - started).total_seconds() * 1000) if started else 0

    registry_requests = int((base.get("operations") or {}).get("requests") or 0)
    measured_external = requests_file.get("requests")
    requests: dict[str, Any]
    if isinstance(measured_external, int):
        requests = {
            "registry_and_website": registry_requests,
            "external_connectors": measured_external,
            "total": registry_requests + measured_external,
            "measured": True,
        }
    else:
        requests = {
            "registry_and_website": registry_requests,
            "external_connectors": None,
            "external_lower_bound": observations,
            "total_lower_bound": registry_requests + observations,
            "measured": False,
            "note": (
                "The external connectors do not keep a per-request counter, so the "
                "external request count is a lower bound: every published observation "
                "needed at least one request. The registry and website-capture stage "
                "is measured exactly."
            ),
        }

    report: dict[str, Any] = {
        "run_id": run_dir.name.removeprefix("run-"),
        "started_at": started.isoformat().replace("+00:00", "Z") if started else None,
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "runtime_ms": runtime_ms,
        "requests": requests,
        "third_party_cost_usd": envelope_cost,
        "cost_note": (
            "No paid API, no model key, no login: every source is a public page or "
            "an official open registry. The declared external cost is $0."
        ),
        "outputs": {
            "envelopes": envelopes,
            "claims": claims,
            "evidence_records": evidence,
            "observations": observations,
            "manifest_rows": count_jsonl(run_dir / "entry.jsonl")[0],
        },
        "identity_precision": evaluation.get("entity_precision"),
        "wrong_company_publications": evaluation.get("wrong_entity_publications"),
        "unsupported_publications": evaluation.get("unsupported_publications"),
        "published_observations": evaluation.get("published_audited"),
        "recall_proxy_50": round(float(measure.get("recall_proxy_50") or 0), 4),
        "family_company_recall": {
            name: {
                "covered": row.get("covered"),
                "opportunities": row.get("opportunities"),
                "recall": row.get("recall"),
            }
            for name, row in (family.get("family_company_recall") or {}).items()
        },
        "refresh": refresh or {
            "note": "No previous snapshot was supplied, so this run is a baseline."
        },
        "merge": {
            "merged_rows": merge.get("merged_rows"),
            "duplicates_dropped": merge.get("duplicates_dropped"),
            "rows_excluded": merge.get("rows_excluded"),
            "observed_at_stamped": merge.get("observed_at_stamped"),
        },
        "source_rights": {
            "model_keys": False,
            "logins": False,
            "paid_accounts": False,
            "official_registries": [
                "Brønnøysund Enhetsregisteret (bulk dump + entity API)",
                "Brønnøysund Kunngjoringer (announcements feed)",
                "NAV Arbeidsplassen (official public job feed)",
            ],
            "open_registries": ["Wikidata/Wikipedia (CC0)", "GLEIF (public LEI registry)"],
            "public_pages": [
                "Fagfolkguiden directory pages",
                "public ATS job boards",
                "the companies' own websites (robots.txt honoured)",
            ],
            "excluded": [
                "Google Places (needs a key; scraped rows removed)",
                "LinkedIn, Meta, Indeed, Glassdoor (access restrictions)",
                "Finn.no (no organisation numbers; terms forbid the use)",
                "proff.no (permission state cannot be re-verified)",
            ],
        },
        "reproduce": {
            "command": "scripts/run_official_batch.sh --batch <organisations.jsonl>",
            "dependencies": "pinned in pyproject.toml and uv.lock",
            "python": "3.12+",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="The finished run directory")
    parser.add_argument("--output", required=True, help="Where to write the report JSON")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    report = build(run_dir)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "runtime_ms": report["runtime_ms"],
                "requests": report["requests"],
                "third_party_cost_usd": report["third_party_cost_usd"],
                "envelopes": report["outputs"]["envelopes"],
                "entity_precision": report["identity_precision"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
