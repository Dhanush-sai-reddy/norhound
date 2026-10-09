#!/usr/bin/env python3
"""NAV arbeidsplassen live-search job connector.

Searches the public stillinger API per company legal name, fetches ad detail
records for name-matched candidates, and publishes only ads whose
employer.orgnr exactly equals the target organisation number.

Modeled on the approach used by the top-scoring entry: name-gated search plus
org-number confirmation in the ad detail.

Usage:
  uv run python scripts/run_nav_search_connector.py \
    --profiles data/entry-manifest.jsonl \
    --organisations data/1000-orgs.txt \
    --output out/nav-search.jsonl \
    --cache data/nav-search-cache \
    --report out/nav-search-report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

SEARCH_API = "https://arbeidsplassen.nav.no/stillinger/api/search"
AD_API = "https://arbeidsplassen.nav.no/stillinger/api/stilling/{uuid}"
AD_URL = "https://arbeidsplassen.nav.no/stillinger/stilling/{uuid}"
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
LEGAL_FORM_TOKENS = {"as", "asa", "ans", "da", "sa", "nuf", "ba", "enk", "ks", "se", "sti", "brl", "iks", "kf"}
MAX_CANDIDATES = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fold(name) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).casefold()
    s = s.replace("æ", "ae").replace("ø", "o").replace("å", "a")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def names_match(legal_name: str, candidate: str) -> bool:
    a, b = fold(legal_name), fold(candidate)
    if not a or not b:
        return False
    if a == b:
        return True
    # legal name minus trailing legal-form token
    toks = a.split()
    if len(toks) > 1 and toks[-1] in LEGAL_FORM_TOKENS and " ".join(toks[:-1]) == b:
        return True
    # candidate contains full folded legal name (e.g., "Wegger AS, Oslo")
    return a in b or b in a


def get_json(url: str, timeout: float = 25) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def fetch_company(org: str, profile: dict, cache_dir: Path) -> tuple[list[dict], dict]:
    name = str(profile.get("name") or "").strip()
    if not name:
        return [], {"organisation_number": org, "status": "no_name"}
    cache = cache_dir / f"{org}.json"
    if cache.exists():
        ads = json.loads(cache.read_text(encoding="utf-8"))
    else:
        q = urllib.parse.urlencode({"q": name, "size": 25})
        data = get_json(f"{SEARCH_API}?{q}")
        hits = (((data or {}).get("content")) or []) if isinstance(data, dict) else []
        cands = [h for h in hits if isinstance(h, dict)][:MAX_CANDIDATES]
        ads = []
        for hit in cands:
            employer = str((hit.get("employer") or {}).get("name") or hit.get("businessName") or "")
            if not names_match(name, employer):
                continue
            uuid = hit.get("uuid") or hit.get("id")
            if not uuid:
                continue
            detail = get_json(AD_API.format(uuid=urllib.parse.quote(str(uuid))))
            if not detail:
                continue
            empl = detail.get("employer") or {}
            orgnr = re.sub(r"\D", "", str(empl.get("orgnr") or empl.get("organisationNumber") or ""))
            if orgnr != org:
                continue
            ads.append(detail)
            time.sleep(0.2)
        cache.write_text(json.dumps(ads, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)

    rows = []
    retrieved_at = utc_now()
    for ad in ads:
        uuid = str(ad.get("uuid") or hashlib.sha256(json.dumps(ad, sort_keys=True).encode()).hexdigest()[:16])
        digest = hashlib.sha256(json.dumps(ad, sort_keys=True).encode()).hexdigest()
        title = str(ad.get("title") or "")
        loc = None
        for loc_item in ad.get("locationList") or []:
            if isinstance(loc_item, dict) and (loc_item.get("city") or loc_item.get("municipal")):
                loc = loc_item.get("city") or loc_item.get("municipal")
                break
        published = (ad.get("published") or "")[:10] or None
        expires = (ad.get("expires") or "")[:10] or None
        rows.append({
            "id": f"nav-job-{org}-{uuid[:24]}",
            "organisation_number": org,
            "signal_type": "job_posting",
            "platform": "job_board",
            "source_url": AD_URL.format(uuid=uuid),
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": [
                {"type": "organisation_number_on_official_api", "source": "arbeidsplassen.nav.no",
                 "matched_organisation_number": org, "explanation": "employer.orgnr in NAV ad detail record"}
            ],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "job_board",
            "strategy": "nav_search_org_confirmed",
            "evidence_span": f"{title}" + (f" — {loc}" if loc else ""),
            "observed_at": published,
            "metrics": {"title": title, "location": loc, "published": published, "deadline": expires,
                        "job_uuid": uuid, "apply_url": (ad.get("properties") or {}).get("applicationurl")},
        })
    return rows, {"organisation_number": org, "status": "ok" if ads else "no_confirmed_ads", "ads": len(ads)}


def main() -> None:
    parser = argparse.ArgumentParser(description="NAV arbeidsplassen live-search job connector")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--organisations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    wanted = [l.strip() for l in args.organisations.read_text(encoding="utf-8").splitlines() if l.strip()]
    profiles = {str(r["organisation_number"]): r for r in
                (json.loads(l) for l in args.profiles.read_text(encoding="utf-8").splitlines() if l.strip())}
    cache_dir = args.cache
    cache_dir.mkdir(parents=True, exist_ok=True)

    observations, statuses = [], []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futures = {pool.submit(fetch_company, org, profiles[org], cache_dir): org for org in wanted if org in profiles}
        for i, fut in enumerate(as_completed(futures)):
            rows, status = fut.result()
            observations.extend(rows)
            statuses.append(status)
            if (i + 1) % 100 == 0:
                print(f"{i+1}/{len(wanted)}; ads={len(observations)}", flush=True)

    order = {org: i for i, org in enumerate(wanted)}
    observations.sort(key=lambda r: (order.get(r["organisation_number"], 99999), r["id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in observations), encoding="utf-8")
    report = {
        "connector": "nav_stillinger_search_org_confirmed_v1",
        "companies": len(wanted),
        "companies_with_ads": sum(1 for s in statuses if s.get("ads")),
        "observations": len(observations),
        "retrieved_at": utc_now(),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
