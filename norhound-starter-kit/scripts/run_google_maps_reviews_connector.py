#!/usr/bin/env python3
"""Google Maps reviews connector via Apify Actor.

Searches Google Maps for each company name, extracts reviews and place details,
matches results to our companies by domain, and outputs observations.

Usage:
  uv run python scripts/run_google_maps_reviews_connector.py \
    --profiles data/entry-manifest.jsonl \
    --organisations data/1000-orgs.txt \
    --output out/gmaps-reviews.jsonl \
    --cache data/gmaps-cache \
    --report out/gmaps-report.json \
    --batch-size 100
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ACTOR_ID = "memo23/google-maps-reviews-scraper"
API_BASE = "https://api.apify.com/v2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_domain(url: str) -> str | None:
    if not url:
        return None
    url = str(url).lower().strip()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    url = url.split("/")[0]
    return url or None


def run_actor(queries: list[str], batch_dir: Path) -> list[dict]:
    """Run the Google Maps Actor and return results."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    input_data = {
        "searchQueries": queries,
        "searchLocation": "Norway",
        "region": "NO",
        "language": "no",
        "maxPlacesPerQuery": 20,
        "maxItems": 2000,
        "maxReviewsPerPlace": 20,
        "includePlaceDetails": True,
        "personalData": False,
    }
    input_path = batch_dir / "input.json"
    input_path.write_text(json.dumps(input_data, ensure_ascii=False), encoding="utf-8")

    # Start actor run
    url = f"{API_BASE}/acts/{urllib.parse.quote(ACTOR_ID, safe='')}/run-sync-get-dataset-items"
    headers = {
        "Authorization": f"Bearer {APIFY_TOKEN}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=json.dumps(input_data).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        print(f"Actor run failed: {exc}")
        return []


def match_reviews_to_companies(reviews: list[dict], profiles: dict[str, dict]) -> list[dict]:
    """Match Google Maps reviews to our companies by domain."""
    # Build domain -> org mapping
    domain_to_org: dict[str, str] = {}
    for org, profile in profiles.items():
        domain = extract_domain(profile.get("website", ""))
        if domain:
            domain_to_org[domain] = org

    observations = []
    for review in reviews:
        place_website = review.get("place_website", "")
        place_domain = extract_domain(place_website)
        if not place_domain:
            continue
        org = domain_to_org.get(place_domain)
        if not org:
            continue
        profile = profiles[org]
        place_name = review.get("placeName", "")
        place_rating = review.get("place_rating")
        place_reviews_count = review.get("place_reviews_count")
        rating = review.get("rating")
        review_text = review.get("review_text", "") or review.get("review_text_original", "")
        time_published = review.get("time_published")
        place_address = review.get("place_address", "")
        place_city = review.get("place_city", "")
        place_categories = review.get("place_categories", [])
        review_id = review.get("review_id", "")
        search_string = review.get("searchString", "")

        digest = hashlib.sha256(json.dumps(review, sort_keys=True).encode()).hexdigest()
        retrieved_at = utc_now()

        # Sentiment from rating
        def rating_to_label(r):
            if r >= 4.0:
                return "positive"
            elif r >= 3.0:
                return "neutral"
            else:
                return "negative"

        sentiment_label = rating_to_label(rating) if rating else None

        common = {
            "organisation_number": org,
            "platform": "google_maps",
            "source_url": f"https://www.google.com/maps/place/{review.get('placeId', '')}",
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": [{"type": "domain_resolved_to_exact_entity", "value": place_domain}],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "customer_review",
            "evidence_span": f"Google Maps review of {place_name}: {review_text[:200]}" if review_text else f"Google Maps rating {rating}/5 for {place_name}",
            "metrics": {
                "rating": rating,
                "place_rating": place_rating,
                "place_reviews_count": place_reviews_count,
                "scale": 5,
                "place_name": place_name,
                "place_address": place_address,
                "place_city": place_city,
                "place_categories": place_categories,
            },
        }

        if sentiment_label:
            common["sentiment_label"] = sentiment_label
            common["sentiment_model_version"] = "rule-based-v1"

        observations.append({
            **common,
            "id": f"gmaps-review-{org}-{review_id[:16] if review_id else digest[:16]}",
            "signal_type": "review",
            "strategy": "places_rating_reviews",
        })

        if place_rating and place_reviews_count:
            observations.append({
                **common,
                "id": f"gmaps-rating-{org}-{digest[:16]}",
                "signal_type": "review_summary",
                "strategy": "places_rating_reviews",
                "evidence_span": f"Google Maps rating {place_rating}/5 based on {place_reviews_count} reviews for {place_name}",
            })

    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Maps reviews connector")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--organisations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    wanted = [line.strip() for line in args.organisations.read_text(encoding="utf-8").splitlines() if line.strip()]
    profiles = {
        str(row["organisation_number"]): row
        for row in (json.loads(line) for line in args.profiles.read_text(encoding="utf-8").splitlines() if line.strip())
    }

    print(f"Processing {len(wanted)} companies in batches of {args.batch_size}")

    all_observations = []
    cache_dir = args.cache
    cache_dir.mkdir(parents=True, exist_ok=True)

    for i in range(0, len(wanted), args.batch_size):
        batch = wanted[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(wanted) + args.batch_size - 1) // args.batch_size
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} companies)...")

        batch_dir = cache_dir / f"batch-{batch_num:03d}"
        batch_cache = batch_dir / "results.json"

        if batch_cache.exists():
            reviews = json.loads(batch_cache.read_text(encoding="utf-8"))
            print(f"    Cached: {len(reviews)} reviews")
        else:
            queries = [f"{profiles[org]['name']} {profiles[org].get('municipality', '')} Norway" for org in batch if org in profiles]
            reviews = run_actor(queries, batch_dir)
            batch_cache.write_text(json.dumps(reviews, ensure_ascii=False), encoding="utf-8")
            print(f"    Fetched: {len(reviews)} reviews")
            time.sleep(2)

        observations = match_reviews_to_companies(reviews, profiles)
        all_observations.extend(observations)
        print(f"    Matched: {len(observations)} observations")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(obs, ensure_ascii=False) + "\n" for obs in all_observations),
        encoding="utf-8",
    )

    # Write report
    report = {
        "connector": "google_maps_reviews_v1",
        "companies": len(wanted),
        "observations": len(all_observations),
        "companies_with_reviews": len(set(obs["organisation_number"] for obs in all_observations)),
        "retrieved_at": utc_now(),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nDone: {report}")


if __name__ == "__main__":
    main()
