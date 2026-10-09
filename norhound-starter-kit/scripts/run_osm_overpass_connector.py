#!/usr/bin/env python3
"""OSM Overpass connector - extracts companies with ref:NO:orgnr tag."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.identity import assess_social_identity  # noqa: E402

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY_TEMPLATE = '[out:json][timeout:60];nwr["ref:NO:orgnr"="{orgnr}"](57.8,4.0,71.5,31.5);out tags;'

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)

def fetch(url: str, timeout: float = 120.0) -> str | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SignalpostOSM/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  [fetch] {url}: {e}")
        return None

def process(profile: dict) -> list[dict]:
    org = str(profile["organisation_number"])
    name = profile.get("name", "")
    
    query = f'[out:json][timeout:60];nwr["ref:NO:orgnr"="{org}"];out tags;'
    data = urllib.parse.urlencode({"data": query}).encode()
    url = "https://overpass-api.de/api/interpreter"
    
    raw = fetch(f"https://overpass-api.de/api/interpreter?data={urllib.parse.quote_plus('[out:json][timeout:60];nwr[\"ref:NO:orgnr\"=\"{org}\"](57.8,4.0,71.5,31.5);out tags;')}")
    if not raw:
        return []
    
    try:
        data = json.loads(raw)
    except Exception:
        return []
    
    out = []
    for elem in raw.get("elements", []):
        tags = elem.get("tags", {})
        if tags.get("ref:NO:orgnr") != str(profile["organisation_number"]):
            continue
        
        website = tags.get("website") or tags.get("contact:website")
        facebook = tags.get("contact:facebook")
        instagram = tags.get("contact:instagram")
        linkedin = tags.get("contact:linkedin")
        twitter = tags.get("contact:twitter") or tags.get("contact:x")
        youtube = tags.get("contact:youtube")
        
        social = []
        for plat, url in [("facebook", facebook), ("instagram", instagram), ("linkedin", linkedin), ("twitter", twitter), ("x", twitter), ("youtube", youtube)]:
            if url:
                digest = hashlib.sha256(f"{profile['organisation_number']}|{plat}|{url}".encode()).hexdigest()[:16]
                out.append({
                    "organisation_number": profile["organisation_number"],
                    "platform": plat,
                    "source_url": url,
                    "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "content_sha256": hashlib.sha256(f"{plat}|{url}".encode()).hexdigest(),
                    "exact_entity": True,
                    "identity_proof": [{"type": "osm_ref_orgnr", "source": "openstreetmap.org", "matched_orgnr": profile["organisation_number"]}],
                    "acquisition_mode": "permitted_public_page",
                    "rights_status": "approved",
                    "source_class": "company_directory",
                    "strategy": "osm_overpass_ref_orgnr",
                    "id": f"osm-social-{profile['organisation_number']}-{plat}-{hashlib.sha256(f'{url}|{profile[\"organisation_number\"]}'.encode()).hexdigest()[:16]}",
                    "signal_type": "profile_handle",
                    "evidence_span": f"OSM tag ref:NO:orgnr={profile['organisation_number']} on {tags.get('name', 'unknown')}",
                    "metrics": {"platform": "openstreetmap", "url": url},
                })
    return out


def main():
    import argparse, urllib.request
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profiles = []
    with open(args.profiles, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                profiles.append(json.loads(line))
    
    if args.limit:
        profiles = profiles[:args.limit]

    out = []
    stats = {"profiles": 0, "companies": 0, "handles": 0}
    
    with ThreadPoolExecutor(max_workers=max(1, 8)) as pool:
        futures = {pool.submit(fetch_osm, p): p for p in (profiles[:args.limit] if args.limit else profiles)}
        for fut in as_completed(futures):
            try:
                rows = fut.result() or []
                for r in rows:
                    out.append(r)
            if len(out) % 100 == 0:
                print(f"  collected {len(out)} handles...")
    
    write_jsonl(Path(args.output), out)
    print(json.dumps({"companies": len(set(r["organisation_number"] for r in out)), "handles": len(out)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
