#!/usr/bin/env python3
"""
Scrape scrapers_lat/norway-companies-scraper for all 1000 companies via direct API.
Requires APIFY_TOKEN environment variable.
"""

import json
import os
import time
import urllib.request
from pathlib import Path

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
if not APIFY_TOKEN:
    raise SystemExit("APIFY_TOKEN environment variable is required")

DATA_DIR = Path("/home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/data")
OUT_DIR = Path("/home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/out")

with open(DATA_DIR / "proff-orgnr-list.json") as f:
    all_orgs = json.load(f)

print(f"Total orgs: {len(all_orgs)}")

# Split into 20 batches of 50
batches = [all_orgs[i:i+50] for i in range(0, len(all_orgs), 50)]
print(f"20 batches of 50")

results = []
total_companies = 0

for i, batch in enumerate(batches):
    # Use company query approach - search by company names and filter client-side
    # Get company names for this batch
    names = []
    for org in batch:
        # Find company name from BRREG data
        profile_file = OUT_DIR / "web1000-profiles.jsonl"
        with open(profile_file) as f:
            for line in f:
                p = json.loads(line)
                if str(p['organisation_number']).zfill(9) == org:
                    names.append(p.get('name', ''))
                    break

    # The scrapers_lat actor accepts orgNumbers array
    payload = {
        "orgNumbers": batch,
        "maxCompanies": 50,
        "withFinancials": True,
    }
    req = urllib.request.Request(
        "https://api.apify.com/v2/acts/scrapers_lat~norway-companies-scraper/run-sync-get-dataset-items",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {APIFY_TOKEN}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", []) if isinstance(data, dict) else data
            if isinstance(items, list):
                results.extend(items)
                total_companies += len(items)
                print(f"  Batch {i+1}/{len(batches)}: {len(items)} companies (total {total_companies})")
            else:
                print(f"  Batch {i+1}/{len(batches)}: unexpected format: {type(items)}")
    except Exception as e:
        print(f"  Batch {i+1}: ERROR: {e}")
    time.sleep(1)  # Rate limiting

# Write results
output_file = DATA_DIR / "norway-companies-scraped.jsonl"
with open(output_file, 'w') as f:
    for item in results:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

print(f"\nTotal companies scraped: {total_companies}")
print(f"Saved to {output_file}")