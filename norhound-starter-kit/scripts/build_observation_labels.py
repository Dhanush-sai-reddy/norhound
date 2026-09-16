#!/usr/bin/env python3
"""Build a label worksheet from consolidated external observations.

Turns frozen observations (id, exact_entity, metric_correct, sentiment_correct)
into a stable human-readable sheet. The generated labels file can be populated
and then fed back to evaluate_external_footprint.py for the >=300-prediction
audit gate. The worksheet itself is reproducible from frozen observations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a label worksheet + empty-but-cued labels template from observations.")
    parser.add_argument("--observations", required=True, help="Consolidated external observations JSONL")
    parser.add_argument("--worksheet", required=True, help="Human-read label worksheet (markdown)")
    parser.add_argument("--labels", required=True, help="Labels JSONL path the evaluator reads")
    parser.add_argument("--limit", type=int, default=0, help="Optional row cap for the worksheet")
    args = parser.parse_args()

    observations = read_jsonl(Path(args.observations))
    if args.limit:
        observations = observations[: args.limit]

    lines = ["# NorHound external-footprint label worksheet", ""]
    lines.append(f"Rows: {len(observations)}. Label each row `exact_entity` (0/1) and `metric_correct` (0/1);")
    lines.append("add `sentiment_correct` only when a sentiment_label is present. Skipping a row in the")
    lines.append("labels file means it cannot pass the audit. Precision gates require >=99.5% exact-entity")
    lines.append("precision and >=98% metric correctness on audited rows.", )
    lines.append("")

    labels_rows = []
    for index, item in enumerate(observations, start=1):
        identity = item.get("identity_proof") or []
        proof = "; ".join(f"{p.get('type')}: {p.get('value')}" for p in identity[:4])
        lines.append(f"## {index}. {item.get('signal_type')} @ {item.get('platform')}")
        lines.append(f"- id: `{item.get('id')}`")
        lines.append(f"- organisation_number: {item.get('organisation_number')}")
        lines.append(f"- signal_type: {item.get('signal_type')}")
        lines.append(f"- source_url: {item.get('source_url')}")
        lines.append(f"- claimed: {item.get('evidence_span') or '(no span)'}")
        lines.append(f"- proof: {proof or '(none)'}")
        lines.append("- exact_entity: [?]")
        lines.append("- metric_correct: [?]")
        if item.get("sentiment_label"):
            lines.append(f"- sentiment_label: {item.get('sentiment_label')} (model {item.get('sentiment_model_version')})")
            lines.append("- sentiment_correct: [?]")
        # Empty-but-cued template row so eval loads every id without guessing.
        labels_rows.append({
            "id": item.get("id"),
            "exact_entity": None,
            "metric_correct": None,
            "sentiment_correct": None,
        })
        lines.append("")

    Path(args.worksheet).parent.mkdir(parents=True, exist_ok=True)
    Path(args.worksheet).write_text("\n".join(lines), encoding="utf-8")
    Path(args.labels).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.labels).open("w", encoding="utf-8") as handle:
        for row in labels_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"worksheet": args.worksheet, "labels": args.labels, "rows": len(labels_rows)}, indent=2))


if __name__ == "__main__":
    main()