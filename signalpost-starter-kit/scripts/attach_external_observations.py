#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import aggregate_footprint, publishable_observation, validate_observation  # noqa: E402


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def read_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in sanitize_line_separators(Path(path).read_text(encoding="utf-8")).splitlines() if line.strip()]


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach publishable external-footprint observations to terminal envelopes.")
    parser.add_argument("--envelopes", required=True, help="Terminal envelopes from run_competition_batch.py")
    parser.add_argument("--observations", nargs="*", default=[], help="Observation JSONL files produced by external connectors")
    parser.add_argument("--output", required=True, help="Enriched terminal envelope JSONL")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    envelopes = read_jsonl(args.envelopes)
    by_org: dict[str, list[dict]] = defaultdict(list)
    source_files: list[str] = []
    for source in args.observations:
        rows = read_jsonl(source)
        source_files.append(str(source))
        for item in rows:
            by_org[str(item.get("organisation_number"))].append(item)

    all_added = 0
    all_rejected = 0
    org_counts: dict[str, dict[str, int]] = {}
    for envelope in envelopes:
        org = str(envelope.get("organisation_number"))
        observations = by_org.get(org, [])
        accepted = [item for item in observations if publishable_observation(item)]
        rejected = [{"id": item.get("id"), "reasons": validate_observation(item)} for item in observations if not publishable_observation(item)]
        profile = envelope.setdefault("profile", {})
        evidence = profile.setdefault("evidence", {})
        evidence["external_observations"] = accepted
        evidence["external_rejected_observations"] = rejected
        if accepted:
            evidence["external_footprint"] = aggregate_footprint(accepted, as_of=envelope.get("completed_at") or envelope.get("started_at"))
        all_added += len(accepted)
        all_rejected += len(rejected)
        org_counts[org] = {"accepted": len(accepted), "rejected": len(rejected)}

    write_jsonl(args.output, envelopes)
    report = {
        "assembler": "attach_external_observations_v1",
        "envelopes": len(envelopes),
        "observation_sources": source_files,
        "organisations_with_observations": sum(bool(org_counts[org]["accepted"]) for org in org_counts),
        "observations_accepted": all_added,
        "observations_rejected": all_rejected,
        "company_counts": org_counts,
        "claim_boundary": "Only publishable observations (approved rights, exact identity, hash+span) are attached; rejections are retained with reasons.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "company_counts"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()