#!/usr/bin/env python3
"""Live Proff.no enrichment via Apify for any organisation batch.

Reads organisation numbers from a profiles file, calls the
`vhsgreed/proff-no-company-data-scraper` Apify actor via the sync API,
and writes raw results to JSONL. Then `store_proff_ratings.py` converts
them into observation rows.

    APIFY_TOKEN=... python scripts/fetch_proff_live.py \
        --profiles out/submission/profiles.jsonl \
        --output data/proff-latest.jsonl

If APIFY_TOKEN is unset the script exits 0 with a notice, so the
one-shot pipeline below continues with whatever pre-computed data is
already committed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ACTOR = "vhsgreed~proff-no-company-data-scraper"
SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
BATCH_SIZE = 100  # Actor handles up to 1000 orgnr per call; 100 keeps latency sane


def read_orgs(profiles: Path) -> list[str]:
    orgs = []
    with open(profiles, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            org = row.get("organisation_number")
            if org:
                orgs.append(str(org).zfill(9))
    return orgs


def fetch_batch(token: str, orgs: list[str]) -> list[dict]:
    payload = {"orgnrList": orgs, "fetchDetails": True, "maxResults": 1000}
    req = urllib.request.Request(
        SYNC_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, list):
        return data
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Live Proff.no enrichment via Apify actor")
    ap.add_argument("--profiles", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = ap.parse_args()

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("APIFY_TOKEN not set — skipping live Proff.no fetch; "
              "pipeline will use committed pre-computed data instead.")
        return 0

    orgs = read_orgs(args.profiles)
    print(f"Fetching Proff.no data for {len(orgs)} orgs in batches of {args.batch_size}")

    all_items: list[dict] = []
    for i in range(0, len(orgs), args.batch_size):
        batch = orgs[i:i + args.batch_size]
        try:
            items = fetch_batch(token, batch)
            all_items.extend(items)
            print(f"  batch {i // args.batch_size + 1}: +{len(items)} (total {len(all_items)})")
        except urllib.error.HTTPError as exc:
            print(f"  batch {i // args.batch_size + 1}: HTTP {exc.code} — skipped", file=sys.stderr)
        except Exception as exc:  # network hiccup etc.
            print(f"  batch {i // args.batch_size + 1}: {type(exc).__name__}: {exc} — skipped",
                  file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Wrote {len(all_items)} company records to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
