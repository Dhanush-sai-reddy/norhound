#!/usr/bin/env python3
"""Merge promoted discovery websites back into a frozen profile set.

The discovery connector (run_firecrawl_discovery.py --promote-verified) already
applies the identity gate and, for publishable exact-entity sites, stores the
website under `evidence.website`. This script copies that evidence into the
base profile set so the external pipeline sees the newly discovered site.

Rows that only carry `website_discovered` (verified but not identity-promotable)
are retained under the same key but NOT promoted into `evidence.website`.
Rate-limited provider rows (provider_status != 200) are skipped in full.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge promoted discovery websites into a profile set.")
    parser.add_argument("--profiles", required=True, help="Base profile set (JSONL)")
    parser.add_argument("--discovery", required=True, help="Discovery result rows (JSONL)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    profiles = {str(p["organisation_number"]): p for p in read_jsonl(Path(args.profiles))}
    promoted = 0
    retained_discovered = 0
    failed_provider = 0
    untouched = 0
    notes: list[str] = []

    for row in read_jsonl(Path(args.discovery)):
        org = str(row["organisation_number"])
        if org not in profiles:
            continue
        disc = (row.get("evidence") or {}).get("website_discovery") or {}
        value = disc.get("value") or {}
        if value.get("provider_status") != 200 or disc.get("status") == "not_found":
            failed_provider += 1
            continue
        promoted_website = (row.get("evidence") or {}).get("website")
        discovered = (row.get("evidence") or {}).get("website_discovered")
        merged = False
        if promoted_website and promoted_website.get("status") != "source_error":
            profiles[org].setdefault("evidence", {})["website"] = promoted_website
            promoted += 1
            merged = True
            notes.append(f"{org}: promoted {promoted_website.get('source_url')}")
        if discovered:
            profiles[org].setdefault("evidence", {})["website_discovered"] = discovered
            retained_discovered += 1
        if not merged and not discovered:
            untouched += 1

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in profiles.values()), encoding="utf-8")
    report = {
        "connector": "merge_discovery_sites_v2",
        "profiles_in": len(profiles),
        "promoted_websites": promoted,
        "retained_discovered": retained_discovered,
        "failed_or_missing_rows": failed_provider,
        "untouched_rows": untouched,
        "notes": notes,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()