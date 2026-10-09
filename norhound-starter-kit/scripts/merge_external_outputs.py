#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import publishable_observation  # noqa: E402


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge pre-computed external observation outputs, deduped by id.")
    parser.add_argument("--inputs", nargs="+", required=True, help="Observation JSONL files, first wins on id collision.")
    parser.add_argument("--output", required=True, help="Merged observation JSONL")
    parser.add_argument("--report", required=True, help="Merge report JSON")
    args = parser.parse_args()

    merged: dict[str, dict] = {}
    per_file: dict[str, int] = {}
    duplicates = 0
    for raw in args.inputs:
        path = Path(raw)
        rows = read_jsonl(path)
        per_file[path.name] = len(rows)
        for row in rows:
            key = str(row.get("id"))
            if key in merged:
                duplicates += 1
                continue
            merged[key] = row

    rows = list(merged.values())
    write_jsonl(Path(args.output), rows)
    report = {
        "merged_rows": len(rows),
        "duplicates_dropped": duplicates,
        "per_file": per_file,
        "output": args.output,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
