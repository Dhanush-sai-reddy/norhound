#!/usr/bin/env python3
"""Process Apify Google Maps reviews into observations with exact-entity proof."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"


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


def domains_match(our_domain: str, place_domain: str) -> bool:
    if not our_domain or not place_domain:
        return False
    our_domain = our_domain.lower().lstrip("www.")
    place_domain = place_domain.lower().lstrip("www.")
    if our_domain == place_domain:
        return True
    our_parts = our_domain.split('.')
    place_parts = place_domain.split('.')
    if len(our_parts) >= 2 and len(place_parts) >= 2:
        our_base = our_parts[-2]
        place_base = place_parts[-2]
        if our_base == place_base and len(our_base) > 3:
            return True
    if our_domain.endswith('.' + place_domain) or place_domain.endswith('.' + our_domain):
        return True
    return False


def rating_to_label(r):
    if r >= 4.0:
        return "positive"
    elif r >= 3.0:
        return "neutral"
    else:
        return "negative"


def process_apify_results(apify_items: list[dict], profiles: dict[str, dict]) -> list[dict]:
    """Match Apify reviews to our companies by domain and create observations."""
    # Build domain -> org mapping from profiles
    domain_to_org: dict[str, str] = {}
    for org, profile in profiles.items():
        domain = extract_domain(profile.get("website", "") or "")
        if not domain:
            reg = ((profile.get("evidence") or {}).get("registry") or {}).get("value") or {}
            domain = extract_domain(reg.get("hjemmeside", "") or "")
        if domain:
            domain_to_org[domain] = org

    observations = []
    for review in apify_items:
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
    parser = argparse.ArgumentParser(description="Process Apify Google Maps reviews into observations")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    profiles = {
        str(row["organisation_number"]): row
        for row in (json.loads(line) for line in args.profiles.read_text(encoding="utf-8").splitlines() if line.strip())
    }

    # Fetch all items from the dataset
    import urllib.request
    APIFY_TOKEN = "<REDACTED>"
    url = f"https://api.apify.com/v2/datasets/{args.dataset_id}/items?clean=true&format=json"
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        apify_items = json.loads(resp.read())

    print(f"Fetched {len(apify_items)} Apify items")
    observations = process_apify_results(apify_items, profiles)
    print(f"Created {len(observations)} observations")

    args.output.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in observations), encoding="utf-8")
    
    # Report
    orgs = {o["organisation_number"] for o in observations}
    report = {
        "apify_items": len(apify_items),
        "observations": len(observations),
        "organisations_with_reviews": len(orgs),
        "organisations": sorted(orgs),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
