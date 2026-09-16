#!/usr/bin/env python3
"""Select a reproducible entry batch from the public NorHound universe."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
from pathlib import Path


def _registered_org_numbers(path: Path) -> set[str]:
    """Return the set of valid 9-digit organisation numbers from the Brreg CSV."""
    if not path.exists():
        return set()
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        return {
            "".join(c for c in row.get("organisasjonsnummer", row.get("Organisasjonsnummer", "")) if c.isdigit())
            for row in csv.DictReader(handle, dialect=dialect)
            if len("".join(c for c in row.get("organisasjonsnummer", row.get("Organisasjonsnummer", "")) if c.isdigit())) == 9
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True, help="Public .jsonl or .jsonl.gz universe")
    parser.add_argument("--output", required=True, help="Output JSONL manifest")
    parser.add_argument("--count", type=int, default=1000, help="At least 1000 for a valid entry")
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--bulk", default=None, help="Frozen Brreg bulk CSV; when supplied, organisations absent from the registry are auto-replaced")
    parser.add_argument("--website-only", action="store_true", help="Sample only companies with a website field in the universe")
    args = parser.parse_args()
    if args.count < 1000:
        raise SystemExit("NorHound entries must cover at least 1,000 companies")

    path = Path(args.universe)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if args.website_only:
        rows = [row for row in rows if row.get("website") or row.get("nettside")]
    if args.count > len(rows):
        raise SystemExit(f"Requested {args.count}; filtered universe contains {len(rows)}")

    rng = random.Random(args.seed)
    chosen = rng.sample(rows, args.count)

    if args.bulk:
        valid = _registered_org_numbers(Path(args.bulk))
        if not valid:
            raise SystemExit(f"Could not load organisation numbers from {args.bulk}")
        missing = {row.get("organisation_number", "") for row in chosen} - valid
        if missing:
            by_org = {row.get("organisation_number", ""): row for row in chosen}
            remaining = [row for row in rows if row.get("organisation_number", "") not in by_org and row.get("organisation_number", "") in valid]
            rng.shuffle(remaining)
            for bad_org in sorted(missing):
                if not remaining:
                    raise SystemExit(f"No valid replacement found for absent organisation {bad_org}")
                by_org[bad_org] = remaining.pop()
            chosen = [by_org[row.get("organisation_number", "")] for row in chosen]
            still_missing = {row.get("organisation_number", "") for row in chosen} - valid
            if still_missing:
                raise SystemExit(f"Could not replace all absent organisations: {sorted(still_missing)[:5]}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in chosen:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Wrote {len(chosen):,} companies to {output}")


if __name__ == "__main__":
    main()
