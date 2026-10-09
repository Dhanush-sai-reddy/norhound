#!/usr/bin/env python3
"""Extract social handles from newly probed verified websites.

Takes probe_website_candidates.py output (org -> verified site URL), fetches
each site, and emits profile_handle observations for discovered social links.
Identity basis is linked_from_verified_site (the probe already gated exact).
Offline except for the fetches themselves. No API key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.website import (  # noqa: E402
    _social_links,
    fetch_website,
    structured_social_links,
)
from norway_company_agent.identity import assess_social_identity  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def process(row: dict, profiles: dict) -> list[dict]:
    from bs4 import BeautifulSoup

    org = str(row["organisation_number"])
    url = row["website"]
    profile = profiles.get(org, {"organisation_number": org, "name": ""})
    try:
        rec, _ = fetch_website(url)
    except Exception:
        return []
    val = rec.get("value") or {}
    if rec.get("status") != "available":
        return []
    links = list(val.get("social_links") or [])
    for s in structured_social_links(val.get("structured_organisations") or []):
        if s not in links:
            links.append(s)
    out = []
    seen = set()
    for link in links:
        if not isinstance(link, dict):
            continue
        u, plat = str(link.get("url") or ""), link.get("platform")
        if not u or not plat or (org, plat) in seen:
            continue
        seen.add((org, plat))
        a = assess_social_identity(profile, {"platform": plat, "url": u})
        digest = hashlib.sha256(f"{org}|{plat}|{u}".encode()).hexdigest()[:16]
        out.append({
            "organisation_number": org,
            "platform": plat,
            "source_url": url,
            "retrieved_at": rec.get("retrieved_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "content_sha256": rec.get("content_sha256"),
            "exact_entity": True,
            "identity_proof": [{
                "type": "linked_from_verified_site",
                "company_site_url": url,
                "identity_score": a.get("identity_score"),
                "probe_method": row.get("method"),
            }],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_site",
            "strategy": "probed_site_social_handle",
            "id": f"probed-social-{org}-{plat}-{digest}",
            "signal_type": "profile_handle",
            "evidence_span": f"Social handle linked from the probed verified company website {url}."[:1200],
            "metrics": {"platform": plat, "url": u},
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probed", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--workers", type=int, default=14)
    args = ap.parse_args()

    probed = read_jsonl(Path(args.probed))
    profiles = {str(p["organisation_number"]): p for p in read_jsonl(Path(args.profiles))}
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process, r, profiles): r for r in probed}
        for fut in as_completed(futures):
            out.extend(fut.result() or [])
    write_jsonl(Path(args.output), out)
    report = {"sites": len(probed), "handles": len(out), "orgs": len({o["organisation_number"] for o in out}), "output": args.output}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
