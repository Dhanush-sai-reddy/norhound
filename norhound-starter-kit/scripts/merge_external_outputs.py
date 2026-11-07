#!/usr/bin/env python3
"""Merge multiple JSONL observation files into one, deduplicating by id."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge JSONL observation files.")
    parser.add_argument("--inputs", required=True, nargs="+", help="Input JSONL files")
    parser.add_argument("--output", required=True, help="Output JSONL file")
    parser.add_argument("--report", help="Optional JSON report path (merge statistics)")
    args = parser.parse_args()

    seen = set()
    rows = []
    for inp in args.inputs:
        path = Path(inp)
        if not path.exists():
            print(f"Skipping missing input: {inp}", flush=True)
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row_id = row.get("id")
                if row_id and row_id in seen:
                    continue
                if row_id:
                    seen.add(row_id)
                rows.append(row)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.output).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    per_file = {}
    for inp in args.inputs:
        path = Path(inp)
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            per_file[inp] = sum(1 for line in f if line.strip())

    report = {
        "merged_rows": len(rows),
        "inputs": len(args.inputs),
        "per_file": per_file,
        "output": args.output,
    }
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Merged {len(rows)} unique observations from {len(args.inputs)} inputs → {args.output}")


if __name__ == "__main__":
    main()
