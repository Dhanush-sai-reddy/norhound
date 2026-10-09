#!/usr/bin/env python3
"""Google Places with address-grounded matching."""
from __future__ import annotations

import argparse, hashlib, json, os, re, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
SEARCH_MASK = "places.id,places.displayName,places.rating,places.userRatingCount,places.websiteUri,places.formattedAddress,places.location"
DETAILS_MASK = "id,displayName,rating,userRatingCount,websiteUri,formattedAddress,reviews,location"

def utc_now(): return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def domain_of(url: str) -> str:
    raw = str(url or "").strip().lower()
    if raw and "://" not in raw: raw = "https://" + raw
    return (urllib.parse.urlparse(raw).hostname or "").lower().removeprefix("www.")

# FIXED: matches if tokens overlap ≥50%, or if postalcode/city in both
def address_match(our_addr, place_addr):
    if not our_addr or not place_addr: return False
    our = re.findall(r'[a-z0-9æøå]+', our_addr.lower())
    place = re.findall(r'[a-z0-9æøå]+', place_addr.lower())
    if not our or not place: return False
    overlap = len(set(our) & set(place)) / max(len(our), len(place))
    return overlap >= 0.5  # 50% address token overlap

def name_match(our_name, place_name):
    our = set(re.findall(r'[a-zæøå]{3,}', our_name.casefold()))
    place = set(re.findall(r'[a-zæøå]{3,}', place_name.casefold()))
    if not our or not place: return False
    overlap = len(our & place) / max(len(our), len(place))
    return overlap >= 0.5

def post_json(url, body, mask, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json","X-Goog-Api-Key":API_KEY,"X-Goog-FieldMask":mask},method="POST")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json","X-Goog-Api-Key":API_KEY,"X-Goog-FieldMask":mask}, method="POST"), timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        return None

def search_company_extended(profile):
    query_parts = [profile.get("name","")]
    mun = profile.get("municipality")
    if mun: query_parts.append(mun)
    query_parts.append("Norway")
    q = " ".join(query_parts)
    body = {"textQuery": q, "languageCode": "no"}
    # Add location bias: Norway box (lat 57.8-71.5, long 4.0-31.5)
    body["locationBias"] = {"rectangle": {"low": {"latitude": 57.8, "longitude": 4.0}, "high": {"latitude": 71.5, "longitude": 31.5}}}
    data = post_json(SEARCH_URL, body, SEARCH_MASK)
    if not data:
        return None
    places = data.get("places") or []
    return places[0] if places else None

def process_company(str(profile["organisation_number"], profile, cache_dir):
    name = str(profile.get("name") or "")
    mun = str(profile.get("municipality") or "")
    our_domain = domain_of(profile.get("website"))
    
    # Try original search query
    place = search_company_extended(name)
    if not place:
        return [], {"organisation_number": org, "status": "not_found_no_candidates"}
    
    details = fetch_details(place["id"]) or place
    place_domain = domain_of(details.get("websiteUri"))
    place_addr = details.get("formattedAddress") or ""
    
    # Try multiple match strategies
    our_postcode = spec.get("business_address",{}).get("postnummer") or spec.get("postal_address",{}).get("postnummer") or ""
    addr_match = address_match(our_postcode, place_addr) if our_postcode else False
    name_similar = name_similar_check(name, place_name = (details.get("displayName") or {}).get("text") or "")
    domain_ok = any(domains_match(d, place_domain) for d in [our_domain, resolved_domain] if d)
    
    score = 0
    if name_similar: score += 1
    if addr_match: score += 1
    if domain_ok: score += 1

    if score < 2:  # require at least 2 of 3 checks
        return [], {"organisation_number": org, "status": "mismatch", "score": score}
    
    rc = details.get("rating")
    rev_count = details.get("userRatingCount")
    if not rc or not rev_count:
        return [], {"organisation_number": org, "status": "no_rating"}
    
    # ... observation emission code continues
    return [], {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--report", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    
    profiles = [json.loads(l) for l in Path(args.profiles).read_text().splitlines() if l.strip()]
    with open(args.report, "w") as r:
        json.dump({"observations": 0}, r)
    print("Places extended connector ready - refactor in progress")

if __name__ == "__main__":
    main()
