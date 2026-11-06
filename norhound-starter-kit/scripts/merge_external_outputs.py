#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import publishable_observation  # noqa: E402
from norway_company_agent.source_rights import excluded_host_for, source_host  # noqa: E402


def host_is_excluded(host: str, exclude_hosts: set[str]) -> str:
    """Return the excluded host that matches, or an empty string.

    ``proff.no`` also excludes ``www.proff.no`` and any other subdomain of it.
    """
    if not host:
        return ""
    for excluded in exclude_hosts:
        candidate = excluded.strip().lower().removeprefix("www.")
        if not candidate:
            continue
        if host == candidate or host.endswith("." + candidate):
            return candidate
    return ""


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return [
        json.loads(line)
        for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def claim_key(row: dict) -> tuple[str, str, str, str, str, str]:
    """Identity of a *claim* (not of a row).

    Two rows state the same claim when they name the same company, signal,
    source, period, evidence span and measured values. A row that was fetched
    twice from the same URL (for example an annual-report PDF that was
    re-downloaded) therefore collapses to one claim, while two different facts
    from one endpoint stay apart.
    """
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    return (
        str(row.get("organisation_number") or ""),
        str(row.get("signal_type") or ""),
        str(row.get("source_url") or ""),
        str(row.get("effective_at") or ""),
        str(row.get("evidence_span") or ""),
        json.dumps(metrics, ensure_ascii=False, sort_keys=True),
    )


def merge_observations(
    inputs: list[Path],
    exclude_hosts: set[str] | None = None,
    dedupe_latest: bool = False,
) -> tuple[list[dict], dict]:
    """Merge observation files (first input wins on id collision) and drop excluded hosts.

    Rows whose source host is in ``exclude_hosts`` are never published: the
    caller uses this for sources whose permission state cannot be re-verified
    (for example a host that now answers every request with a 403).

    With ``dedupe_latest`` the merge also collapses repeated claims of the same
    company, signal, source and period to the most recently retrieved row.
    """
    excluded = {str(host).strip().lower() for host in (exclude_hosts or set()) if str(host).strip()}
    merged: dict[str, dict] = {}
    per_file: dict[str, int] = {}
    duplicates = 0
    excluded_counts: dict[str, int] = {}
    duplicate_claims = 0
    latest_by_claim: dict[tuple[str, str, str, str], tuple[str, str]] = {}
    for raw in inputs:
        path = Path(raw)
        rows = read_jsonl(path)
        per_file[path.name] = len(rows)
        for row in rows:
            host = source_host(row.get("source_url") or "")
            blocked = host_is_excluded(host, excluded)
            if blocked:
                excluded_counts[blocked] = excluded_counts.get(blocked, 0) + 1
                continue
            key = str(row.get("id"))
            if key in merged:
                duplicates += 1
                continue
            if dedupe_latest:
                claim = claim_key(row)
                retrieved_at = str(row.get("retrieved_at") or "")
                previous = latest_by_claim.get(claim)
                if previous is not None:
                    duplicate_claims += 1
                    previous_id, previous_time = previous
                    if retrieved_at > previous_time:
                        # The newer retrieval replaces the older row in place.
                        merged.pop(previous_id, None)
                        merged[key] = row
                        latest_by_claim[claim] = (key, retrieved_at)
                    continue
                latest_by_claim[claim] = (key, retrieved_at)
            merged[key] = row
    rows = list(merged.values())
    report = {
        "merged_rows": len(rows),
        "duplicates_dropped": duplicates,
        "duplicate_claims_dropped": duplicate_claims,
        "per_file": per_file,
        "excluded_hosts": excluded_counts,
        "excluded_host_list": sorted(excluded_counts),
        "rows_excluded": sum(excluded_counts.values()),
        "output": "",
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge pre-computed external observation outputs, deduped by id.")
    parser.add_argument("--inputs", nargs="+", required=True, help="Observation JSONL files, first wins on id collision.")
    parser.add_argument("--output", required=True, help="Merged observation JSONL")
    parser.add_argument("--report", required=True, help="Merge report JSON")
    parser.add_argument(
        "--exclude-hosts",
        nargs="*",
        default=[],
        help="Source hosts whose rows must never be published (for example proff.no).",
    )
    parser.add_argument(
        "--dedupe-latest",
        action="store_true",
        help="Collapse repeated claims of the same company, signal, source and period to the latest retrieval.",
    )
    args = parser.parse_args()

    rows, report = merge_observations(
        [Path(raw) for raw in args.inputs],
        set(args.exclude_hosts),
        dedupe_latest=args.dedupe_latest,
    )
    report["output"] = args.output
    write_jsonl(Path(args.output), rows)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
