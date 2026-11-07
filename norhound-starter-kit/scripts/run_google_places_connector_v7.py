#!/usr/bin/env python3
"""Google Places with address-grounded matching.

Requires GOOGLE_PLACES_KEY. A place is accepted only when at least two of
three independent signals agree: company name, registered address, and
website domain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
SEARCH_MASK = "places.id,places.displayName,places.rating,places.userRatingCount,places.websiteUri,places.formattedAddress,places.location"
DETAILS_MASK = "id,displayName,rating,userRatingCount,websiteUri,formattedAddress,reviews,location"

REQUIRED_SIGNALS = 2


class QuotaExhausted(Exception):
    """Raised when Google Places API quota is exhausted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def domain_of(url: object) -> str:
    raw = str(url or "").strip().lower()
    if raw and "://" not in raw:
        raw = "https://" + raw
    host = (urllib.parse.urlparse(raw).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def domains_match(our_domain: str, place_domain: str) -> bool:
    """Check if two domains represent the same entity."""
    if not our_domain or not place_domain:
        return False
    our_domain = our_domain.lower().removeprefix("www.")
    place_domain = place_domain.lower().removeprefix("www.")
    if our_domain == place_domain:
        return True
    our_parts = our_domain.split(".")
    place_parts = place_domain.split(".")
    if len(our_parts) >= 2 and len(place_parts) >= 2:
        our_base = our_parts[-2]
        place_base = place_parts[-2]
        if our_base == place_base and len(our_base) > 3:
            return True
    if our_domain.endswith("." + place_domain) or place_domain.endswith("." + our_domain):
        return True
    return False


def tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9æøå]+", str(value or "").casefold())


def address_match(our_addr: str, place_addr: str) -> bool:
    """Match on postcode equality first, then on address-token overlap."""
    if not our_addr or not place_addr:
        return False
    our_tokens = tokens(our_addr)
    place_tokens = tokens(place_addr)
    if not our_tokens or not place_tokens:
        return False
    our_postcode = next((t for t in our_tokens if len(t) == 4 and t.isdigit()), None)
    place_postcode = next((t for t in place_tokens if len(t) == 4 and t.isdigit()), None)
    if our_postcode and place_postcode and our_postcode == place_postcode:
        return True
    overlap = len(set(our_tokens) & set(place_tokens)) / max(len(our_tokens), len(place_tokens))
    return overlap >= 0.5


def name_match(our_name: str, place_name: str) -> bool:
    our = set(tokens(our_name))
    place = set(tokens(place_name))
    if not our or not place:
        return False
    overlap = len(our & place) / max(len(our), len(place))
    return overlap >= 0.5


def post_json(url: str, body: dict, mask: str) -> dict | None:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
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
    except urllib.error.HTTPError as e:
        if e.code in (429, 403, 503):
            raise QuotaExhausted(f"Google Places quota exhausted: HTTP {e.code}")
        return None
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
    except urllib.error.HTTPError as e:
        if e.code in (429, 403, 503):
            raise QuotaExhausted(f"Google Places quota exhausted: HTTP {e.code}")
        return None
    except Exception:
        return None


def rating_label(r: float) -> str:
    return "positive" if r >= 4.0 else "neutral" if r >= 3.0 else "negative"


def search_company_extended(profile: dict) -> dict | None:
    query_parts = [str(profile.get("name") or "")]
    mun = profile.get("municipality")
    if mun:
        query_parts.append(str(mun))
    query_parts.append("Norway")
    body = {"textQuery": " ".join(query_parts), "languageCode": "no"}
    body["locationBias"] = {
        "rectangle": {
            "low": {"latitude": 57.8, "longitude": 4.0},
            "high": {"latitude": 71.5, "longitude": 31.5},
        }
    }
    data = post_json(SEARCH_URL, body, SEARCH_MASK)
    if not data:
        return None
    places = data.get("places") or []
    return places[0] if places else None


def fetch_details(place_id: str) -> dict | None:
    return get_json(DETAILS_URL.format(place_id=place_id), DETAILS_MASK)


def registered_address(profile: dict) -> str:
    registry = ((profile.get("evidence") or {}).get("registry") or {}).get("value") or {}
    address = registry.get("business_address") or registry.get("postal_address") or {}
    if not isinstance(address, dict):
        return str(address)
    parts = [
        str(address.get("postnummer") or ""),
        str(address.get("poststed") or ""),
        str(address.get("adressenavn") or ""),
        str(address.get("husnummer") or ""),
    ]
    return " ".join(part for part in parts if part)


def process_company(org: str, profile: dict, cache_dir: Path) -> tuple[list[dict], dict]:
    name = str(profile.get("name") or "")
    our_domain = domain_of(profile.get("website"))
    website_value = ((profile.get("evidence") or {}).get("website") or {}).get("value") or {}
    resolved_domain = domain_of(website_value.get("final_url"))
    our_address = registered_address(profile)

    cache_file = cache_dir / f"{org}.json"
    if cache_file.exists():
        details = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        place = search_company_extended(profile)
        if not place or not place.get("id"):
            return [], {"organisation_number": org, "status": "not_found"}
        details = fetch_details(place["id"]) or place
        cache_file.write_text(json.dumps(details, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)

    place_name = (details.get("displayName") or {}).get("text") or ""
    place_address = details.get("formattedAddress") or ""
    place_domain = domain_of(details.get("websiteUri"))

    name_similar = name_match(name, place_name)
    addr_match = address_match(our_address, place_address)
    domain_ok = any(domains_match(d, place_domain) for d in [our_domain, resolved_domain] if d)
    score = int(name_similar) + int(addr_match) + int(domain_ok)

    if score < REQUIRED_SIGNALS:
        return [], {
            "organisation_number": org,
            "status": "mismatch",
            "score": score,
            "place_name": place_name,
        }

    rating = details.get("rating")
    count = details.get("userRatingCount")
    if not rating or not count:
        return [], {"organisation_number": org, "status": "no_rating"}

    display = place_name or name
    place_id = details.get("id") or ""
    source_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    digest = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()
    label = rating_label(float(rating))
    proof = [
        {
            "type": "google_places_address_grounded_match",
            "value": place_domain or place_address,
            "source": "google_places",
            "signals": {"name": name_similar, "address": addr_match, "domain": domain_ok},
        }
    ]

    common = {
        "organisation_number": org,
        "platform": "google_places",
        "source_url": source_url,
        "retrieved_at": utc_now(),
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
            "id": f"gplaces-v7-review-summary-{org}-{digest[:16]}",
            "signal_type": "review_summary",
            "strategy": "places_rating_reviews",
            "evidence_span": f"{display} is rated {rating}/5 from {count} Google reviews.",
            "metrics": {"rating": rating, "review_count": count, "scale": 5, "place_id": place_id},
        },
        {
            **common,
            "id": f"gplaces-v7-metrics-{org}-{digest[:16]}",
            "signal_type": "profile_metrics",
            "strategy": "social_profile_metrics",
            "evidence_span": f"{display} Google profile: rating {rating}/5, {count} ratings.",
            "metrics": {"rating": rating, "review_count": count, "scale": 5, "place_id": place_id},
        },
        {
            **common,
            "id": f"gplaces-v7-sentiment-{org}-{digest[:16]}",
            "signal_type": "sentiment",
            "strategy": "customer_review_sentiment",
            "sentiment_label": label,
            "sentiment_model_version": "rule-based-v1",
            "evidence_span": f"Aggregate rating {rating}/5 from {count} reviews implies {label} sentiment.",
            "metrics": {"rating": rating, "review_count": count, "scale": 5},
        },
    ]

    for index, review in enumerate((details.get("reviews") or [])[:5]):
        stars = review.get("rating")
        text = (review.get("originalText") or review.get("text") or {}).get("text", "")
        if not stars or not text:
            continue
        rows.append({
            **common,
            "id": f"gplaces-v7-review-{org}-{hashlib.sha256((str(review.get('name')) + text).encode()).hexdigest()[:16]}",
            "signal_type": "review",
            "strategy": "places_rating_reviews",
            "evidence_span": text[:1200],
            "observed_at": review.get("publishTime"),
            "sentiment_label": rating_label(float(stars)),
            "sentiment_model_version": "rule-based-v1",
            "metrics": {"rating": stars, "scale": 5, "review_index": index, "place_id": place_id},
        })

    return rows, {"organisation_number": org, "status": "ok", "rating": rating, "count": count, "score": score}


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Places address-grounded reviews connector")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    profiles = [
        json.loads(line)
        for line in args.profiles.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cache_dir = args.cache
    cache_dir.mkdir(parents=True, exist_ok=True)

    observations: list[dict] = []
    statuses: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        futures = {
            pool.submit(process_company, str(profile["organisation_number"]), profile, cache_dir): profile
            for profile in profiles
        }
        for index, future in enumerate(as_completed(futures)):
            try:
                rows, status = future.result()
            except QuotaExhausted:
                order = {str(p["organisation_number"]): i for i, p in enumerate(profiles)}
                observations.sort(key=lambda r: (order.get(r["organisation_number"], 99999), r["signal_type"]))
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in observations),
                    encoding="utf-8",
                )
                report = {
                    "connector": "google_places_address_grounded_v7",
                    "companies": len(profiles),
                    "rated_companies": sum(1 for s in statuses if s.get("status") == "ok"),
                    "observations": len(observations),
                    "status_counts": {
                        s: sum(1 for x in statuses if x.get("status") == s)
                        for s in {x.get("status") for x in statuses}
                    },
                    "retrieved_at": utc_now(),
                    "quota_exhausted": True,
                    "quota_exhausted_at": index + 1,
                }
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(json.dumps(report, indent=2))
                return
            observations.extend(rows)
            statuses.append(status)
            if (index + 1) % 100 == 0:
                print(f"{index + 1}/{len(profiles)} done; {len(observations)} observations", flush=True)

    order = {str(p["organisation_number"]): i for i, p in enumerate(profiles)}
    observations.sort(key=lambda r: (order.get(r["organisation_number"], 99999), r["signal_type"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in observations),
        encoding="utf-8",
    )

    report = {
        "connector": "google_places_address_grounded_v7",
        "companies": len(profiles),
        "rated_companies": sum(1 for s in statuses if s.get("status") == "ok"),
        "observations": len(observations),
        "status_counts": {
            s: sum(1 for x in statuses if x.get("status") == s)
            for s in {x.get("status") for x in statuses}
        },
        "retrieved_at": utc_now(),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
