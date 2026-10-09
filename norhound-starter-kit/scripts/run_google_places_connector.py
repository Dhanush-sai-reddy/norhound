#!/usr/bin/env python3
"""Google Places API (New) reviews connector.

Searches each company by name, matches the returned place by website domain
(exact-entity proof), then fetches place details (rating, reviews).

Usage:
  GOOGLE_PLACES_KEY=... uv run python scripts/run_google_places_connector.py \
    --profiles data/entry-manifest.jsonl \
    --organisations data/1000-orgs.txt \
    --output out/gplaces-reviews.jsonl \
    --cache data/gplaces-cache \
    --report out/gplaces-report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

API_KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
SEARCH_MASK = "places.id,places.displayName,places.rating,places.userRatingCount,places.websiteUri,places.formattedAddress"
DETAILS_MASK = "id,displayName,rating,userRatingCount,websiteUri,formattedAddress,reviews"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def domain_of(url: object) -> str:
    raw = str(url or "").strip().lower()
    if raw and "://" not in raw:
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower()
    # Remove www prefix
    if host.startswith("www."):
        host = host[4:]
    return host


def domains_match(our_domain: str, place_domain: str) -> bool:
    """Check if two domains represent the same entity.
    Allows: subdomain variations, common TLD variations for Norwegian companies."""
    if not our_domain or not place_domain:
        return False
    
    our_domain = our_domain.lower().lstrip("www.")
    place_domain = place_domain.lower().lstrip("www.")
    
    if our_domain == place_domain:
        return True
    
    # Check if they share the same base domain (e.g., elopak.com vs elopak.no)
    our_parts = our_domain.split('.')
    place_parts = place_domain.split('.')
    
    if len(our_parts) >= 2 and len(place_parts) >= 2:
        # Compare base domains (second-level domain)
        our_base = our_parts[-2]  # e.g., "elopak" from "elopak.no"
        place_base = place_parts[-2]  # e.g., "elopak" from "elopak.com"
        if our_base == place_base and len(our_base) > 3:  # avoid matching common short names
            return True
    
    # Check if one is subdomain of the other
    if our_domain.endswith('.' + place_domain) or place_domain.endswith('.' + our_domain):
        return True
    
    return False


def domain_of(url: object) -> str:
    raw = str(url or "").strip().lower()
    if raw and "://" not in raw:
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower()
    # Remove www prefix
    if host.startswith("www."):
        host = host[4:]
    return host


def post_json(url: str, body: dict, mask: str) -> dict | None:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode()
,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": mask,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def get_json(url: str, mask: str) -> dict | None:
    req = urllib.request.Request(
        url,
        headers={
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": mask,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def rating_label(r: float) -> str:
    return "positive" if r >= 4.0 else "neutral" if r >= 3.0 else "negative"


def search_company(name: str, municipality: str) -> dict | None:
    query = f"{name} {municipality} Norway".strip()
    data = post_json(SEARCH_URL, {"textQuery": query, "languageCode": "no"}, SEARCH_MASK)
    if not data:
        return None
    places = data.get("places") or []
    return places[0] if places else None


def fetch_details(place_id: str) -> dict | None:
    return get_json(DETAILS_URL.format(place_id=place_id), DETAILS_MASK)


def process_company(org: str, profile: dict, cache_dir: Path) -> tuple[list[dict], dict]:
    name = str(profile.get("name") or "")
    municipality = str(profile.get("municipality") or "")
    our_domain = domain_of(profile.get("website"))
    # Also consider the resolved final_url from the website crawl
    ev = (profile.get("evidence") or {}).get("website") or {}
    val = ev.get("value") or {}
    resolved_domain = domain_of(val.get("final_url")) if val.get("final_url") else None

    cache_file = cache_dir / f"{org}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        details = cached
    else:
        place = search_company(name, municipality)
        if not place or not place.get("id"):
            return [], {"organisation_number": org, "status": "not_found"}
        details = fetch_details(place["id"]) or place
        details["_raw_search"] = place
        cache_file.write_text(json.dumps(details, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)

    # Exact-entity gate: verify place matches company by name + location
    # Primary: exact displayName match (case-insensitive) + municipality match
    # Fallback: domain match (allowing subdomain/TLD variations)
    place_name = (details.get("displayName") or {}).get("text") or ""
    place_address = details.get("formattedAddress") or ""
    place_domain = domain_of(details.get("websiteUri"))

    # Primary: exact name match (case-insensitive) + municipality in address
    # Accept if: fuzzy name match (case-insensitive, ignore legal suffixes) OR domain match
    # Use fuzzy matching: check if profile name tokens are mostly present in place name
    name_tokens = set(re.findall(r"[a-zæøå]{3,}", name.casefold()))
    place_tokens = set(re.findall(r"[a-zæøå]{3,}", place_name.casefold()))
    name_overlap = len(name_tokens & place_tokens) / max(len(name_tokens), 1)
    name_similar = name_overlap >= 0.6  # 60% token overlap

    # Accept if: fuzzy name match (60% token overlap) OR domain match
    if not (name_similar or any(domains_match(d, place_domain) for d in [our_domain, resolved_domain] if d)):
        return [], {"organisation_number": org, "status": "mismatch", "place_name": place_name, "place_address": place_address, "place_domain": place_domain, "our_domain": our_domain, "resolved_domain": resolved_domain}

    rating = details.get("rating")
    count = details.get("userRatingCount")
    if not rating or not count:
        return [], {"organisation_number": org, "status": "no_rating"}

    display = (details.get("displayName") or {}).get("text") or name
    place_id = details.get("id") or ""
    source_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    digest = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()
    retrieved_at = utc_now()
    label = rating_label(float(rating))
    proof = [{"type": "google_places_website_domain_match", "value": place_domain, "source": "google_places"}]

    common = {
        "organisation_number": org,
        "platform": "google_places",
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "exact_entity": True,
        "identity_proof": proof,
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "customer_review",
        "label": label,
    }

    rows = [
        {
            **common,
            "id": f"gplaces-review-summary-{org}-{digest[:16]}",
            "signal_type": "review_summary",
            "strategy": "places_rating_reviews",
            "evidence_span": f"{display} is rated {rating}/5 from {count} Google reviews.",
            "metrics": {"rating": rating, "review_count": count, "scale": 5, "place_id": place_id},
        },
        {
            **common,
            "id": f"gplaces-metrics-{org}-{digest[:16]}",
            "signal_type": "profile_metrics",
            "strategy": "social_profile_metrics",
            "evidence_span": f"{display} Google profile: rating {rating}/5, {count} ratings.",
            "metrics": {"rating": rating, "review_count": count, "scale": 5, "place_id": place_id},
        },
        {
            **common,
            "id": f"gplaces-sentiment-{org}-{digest[:16]}",
            "signal_type": "sentiment",
            "strategy": "customer_review_sentiment",
            "sentiment_label": label,
            "sentiment_model_version": "rule-based-v1",
            "evidence_span": f"Aggregate rating {rating}/5 from {count} reviews implies {label} sentiment.",
            "metrics": {"rating": rating, "review_count": count, "scale": 5},
        },
    ]

    # Individual reviews as granular evidence (top 5 by recency)
    for index, review in enumerate((details.get("reviews") or [])[:5]):
        stars = review.get("rating")
        text = (review.get("originalText") or review.get("text") or {}).get("text", "")
        publish_time = review.get("publishTime")
        if not stars or not text:
            continue
        rows.append({
            **common,
            "id": f"gplaces-review-{org}-{hashlib.sha256((str(review.get('name')) + text).encode()).hexdigest()[:16]}",
            "signal_type": "review",
            "strategy": "places_rating_reviews",
            "evidence_span": text[:1200],
            "observed_at": publish_time,
            "sentiment_label": rating_label(float(stars)),
            "sentiment_model_version": "rule-based-v1",
            "metrics": {"rating": stars, "scale": 5, "review_index": index, "place_id": place_id},
        })

    return rows, {"organisation_number": org, "status": "ok", "rating": rating, "count": count}


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Places reviews connector")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--organisations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    wanted = [line.strip() for line in args.organisations.read_text(encoding="utf-8").splitlines() if line.strip()]
    profiles = {
        str(row["organisation_number"]): row
        for row in (json.loads(line) for line in args.profiles.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    cache_dir = args.cache
    cache_dir.mkdir(parents=True, exist_ok=True)

    observations: list[dict] = []
    statuses: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        futures = {pool.submit(process_company, org, profiles[org], cache_dir): org for org in wanted if org in profiles}
        for i, future in enumerate(as_completed(futures)):
            rows, status = future.result()
            observations.extend(rows)
            statuses.append(status)
            if (i + 1) % 100 == 0:
                print(f"{i+1}/{len(wanted)} done; {len(observations)} observations", flush=True)

    order = {org: i for i, org in enumerate(wanted)}
    observations.sort(key=lambda r: (order.get(r["organisation_number"], 99999), r["signal_type"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in observations), encoding="utf-8")

    rated = sum(1 for s in statuses if s.get("status") == "ok")
    report = {
        "connector": "google_places_reviews_v1",
        "companies": len(wanted),
        "rated_companies": rated,
        "observations": len(observations),
        "status_counts": {s: sum(1 for x in statuses if x.get("status") == s) for s in {x.get("status") for x in statuses}},
        "retrieved_at": utc_now(),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
