#!/usr/bin/env python3
"""Store Gulesider ratings results in our observation pipeline format.

Reads Apify dataset output from crawlerbros/gulesider-scraper
and writes JSONL compatible with the external pipeline consolidation step.

Usage:
  uv run python scripts/store_gulesider_ratings.py \
    --apify-dataset /path/to/dataset.json \
    --profiles out/web1000-profiles.jsonl \
    --output data/gulesider-ratings.jsonl

Employer org numbers come from Gulesider's profile page metadata.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_hex(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rating_to_label(r: float) -> str:
    if r >= 4.5:
        return "positive"
    elif r >= 3.0:
        return "neutral"
    else:
        return "negative"


def apify_gulesider_to_observations(
    records: list[dict],
    profiles: list[dict],
) -> list[dict]:
    """
    Convert Gulesider scraper output to our observation schema.

    Gulesider scraper returns business profiles with fields like:
    - name, address, phone, email, website, category, rating, reviewCount
    - organisationNumber (in details mode)
    - url, businessId, etc.

    Returns observations for companies with org numbers that match our batch.
    """
    # Build org number → profile map
    profile_map = {}
    for p in profiles:
        org = str(p.get("organisation_number") or "").zfill(9)
        if org not in profile_map:
            profile_map[org] = p

    observations = []
    seen_ids = set()
    retrieved_at = _now()

    for record in records:
        if record.get("error"):
            continue

        org_num = _extract_org_number(record)
        if not org_num:
            continue

        org = str(org_num).zfill(9)
        profile = profile_map.get(org)
        if not profile:
            continue  # Not in our batch

        rating = record.get("rating") or record.get("ratingValue") or record.get("aggregateRating", {}).get("ratingValue")
        review_count = record.get("reviewCount") or record.get("reviewCount") or record.get("reviewsCount") or record.get("aggregateRating", {}).get("reviewCount")
        business_id = record.get("businessId") or record.get("id") or org
        source_url = record.get("url") or record.get("sourceUrl") or f"https://www.gulesider.no/{business_id}"
        name = record.get("name") or record.get("businessName") or record.get("name", {}).get("value")

        content = json.dumps(record, ensure_ascii=False, sort_keys=True)
        content_sha256 = sha256_hex(content)
        retrieved_at = _now()

        # Build identity proof
        proof = [
            {"type": "organisation_number_on_directory_page", "value": org},
        ]
        if name:
            proof.append({"type": "exact_legal_name_on_directory_page", "value": name})

        # Common fields
        common = {
            "organisation_number": org,
            "platform": "company_directory",
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "observed_at": retrieved_at[:10],
            "content_sha256": content_sha256,
            "exact_entity": True,
            "identity_proof": proof,
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "customer_review",
            "strategy": "gulesider_review_directory",
        }

        label = rating_to_label(rating) if rating is not None else None

        # 1. Rating + Sentiment observation (for ratings_reviews + sentiment)
        if rating is not None:
            label = rating_to_label(rating)
            sentiment_common = {**common, "sentiment_label": label, "sentiment_model_version": "rule-based-v1"}
            rows = [
                {**sentiment_common, "id": f"gulesider-review-{org}-{sha256_hex(content)[:16]}", "signal_type": "review_summary", "evidence_span": f"Gulesider rating {rating}/5 based on {review_count or 0} reviews, embedded on exact Gulesider company page.", "metrics": {"rating": rating, "review_count": review_count, "scale": 5, "google_review_url": record.get("google_review_url")}},
                {**sentiment_common, "id": f"gulesider-sentiment-{org}-{sha256_hex(content)[:16]}", "signal_type": "sentiment", "evidence_span": f"Gulesider rating {rating}/5 ({review_count} reviews) for {name or org}", "metrics": {"rating": rating, "review_count": review_count, "scale": 5}},
            ]
            for row in rows:
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    observations.append(row)

        # 2. Company Profile observation (company_profile signal)
        profile_obs = {
            **common,
            "id": f"gulesider-profile-{org}-{sha256_hex(content)[:16]}",
            "signal_type": "company_profile",
            "evidence_span": f"Gulesider company profile for {name or org}",
            "metrics": {
                "source": "gulesider_directory",
                **_extract_firmographics(record),
                **_extract_contact_info(record),
                "coordinates": _extract_coordinates(record),
            },
        }
        if profile_obs["id"] not in seen_ids:
            seen_ids.add(profile_obs["id"])
            observations.append(profile_obs)

        # 3. Place Summary observation (places_identity + contact info)
        place_obs = {
            **common,
            "id": f"gulesider-place-{org}-{sha256_hex(content)[:16]}",
            "signal_type": "place_summary",
            "evidence_span": f"Gulesider place summary for {name or org}",
            "metrics": {
                "source": "gulesider_directory",
                "address": _first_nonempty(record.get("address"), record.get("addressLine1"), record.get("streetAddress"), record.get("visitingAddress"), record.get("postalAddress")),
                "city": record.get("city") or record.get("postalCity") or record.get("poststed"),
                "postal_code": record.get("postalCode") or record.get("postnummer"),
                "municipality": record.get("municipality") or record.get("kommune"),
                "country": record.get("country") or "NO",
                "coordinates": _extract_coordinates(record),
                "opening_hours": _extract_opening_hours(record),
                "phone": _first_nonempty(record.get("phone"), record.get("phoneNumber"), record.get("telephone"), record.get("mobile"), record.get("tlf")),
                "email": _first_nonempty(record.get("email"), record.get("eMail"), record.get("emailAddress"), record.get("epost")),
                "website": _first_nonempty(record.get("website"), record.get("webSite"), record.get("homepage"), record.get("url"), record.get("urlHomepage")),
                "opening_hours_structured": _extract_opening_hours(record),
            },
        }
        if place_obs["id"] not in seen_ids:
            seen_ids.add(place_obs["id"])
            observations.append(place_obs)

        # 4. Profile Metrics observation (profile_metrics + social)
        metrics_obs = {
            **common,
            "id": f"gulesider-metrics-{org}-{sha256_hex(content)[:16]}",
            "signal_type": "profile_metrics",
            "evidence_span": f"Gulesider profile metrics for {name or org}",
            "metrics": {
                "source": "gulesider_directory",
                "rating": float(rating) if rating else None,
                "review_count": int(review_count) if review_count else None,
                "scale": 5,
                "categories": record.get("categories") or record.get("category"),
                "gulesider_categories": record.get("gulesiderCategories") or record.get("categoryList"),
                "employee_range": _first_nonempty(record.get("employeeRange"), record.get("employeeCount"), record.get("numberOfEmployees"), record.get("employees"), record.get("antallAnsatte"), record.get("ansatte")),
                "founding_date": _first_nonempty(record.get("foundingDate"), record.get("foundedDate"), record.get("establishedDate"), record.get("startDate"), record.get("etableringsdato"), record.get("stiftelsesdato")),
                "vat_status": _first_nonempty(record.get("vatStatus"), record.get("vatRegistration"), record.get("mvaStatus"), record.get("mvaRegistrert"), record.get("merverdiavgift")),
                "legal_form": _first_nonempty(record.get("legalForm"), record.get("companyForm"), record.get("organisasjonsform"), record.get("orgForm")),
                "status": _first_nonempty(record.get("status"), record.get("companyStatus"), record.get("entityStatus"), record.get("aktivitet")),
                "verified": record.get("verified") or record.get("verifiedOnly") or record.get("isVerified"),
                "social_handles": _extract_social_handles(record),
            },
        }
        if metrics_obs["id"] not in seen_ids:
            seen_ids.add(metrics_obs["id"])
            observations.append(metrics_obs)

        # 5. Social handles as profile_handle signals
        for handle in _extract_social_handles(record):
            handle_obs = {
                **common,
                "id": f"gulesider-handle-{org}-{sha256_hex(json.dumps(handle))[:16]}",
                "signal_type": "profile_handle",
                "platform": handle["platform"],
                "source_url": handle["url"],
                "retrieved_at": retrieved_at,
                "observed_at": retrieved_at[:10],
                "content_sha256": sha256_hex(json.dumps(handle)),
                "exact_entity": True,
                "identity_proof": proof,
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "company_directory",
                "evidence_span": f"Social handle {handle['platform']} for {name or org}: {handle['url']}",
                "metrics": {"handle": handle["url"], "platform": handle["platform"]},
                "strategy": "verified_handle_extraction",
            }
            if handle_obs["id"] not in seen_ids:
                seen_ids.add(handle_obs["id"])
                observations.append(handle_obs)

        # 6. Contact email/phone as separate signals
        contact = _extract_contact_info(record)
        if contact.get("email"):
            email_obs = {
                **common,
                "id": f"gulesider-email-{org}-{sha256_hex(content)[:16]}",
                "signal_type": "contact_email",
                "platform": "company_directory",
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "observed_at": retrieved_at[:10],
                "content_sha256": content_sha256,
                "exact_entity": True,
                "identity_proof": proof,
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "customer_review",
                "evidence_span": f"Contact email for {name or org}",
                "metrics": {"email": contact["email"]},
                "strategy": "gulesider_contact_extraction",
            }
            if email_obs["id"] not in seen_ids:
                seen_ids.add(email_obs["id"])
                observations.append(email_obs)

        if contact.get("phone"):
            phone_obs = {
                **common,
                "id": f"gulesider-phone-{org}-{sha256_hex(content)[:16]}",
                "signal_type": "contact_phone",
                "platform": "company_directory",
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "observed_at": retrieved_at[:10],
                "content_sha256": content_sha256,
                "exact_entity": True,
                "identity_proof": proof,
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "customer_review",
                "evidence_span": f"Contact phone for {name or org}",
                "metrics": {"phone": contact["phone"]},
                "strategy": "gulesider_contact_extraction",
            }
            if phone_obs["id"] not in seen_ids:
                seen_ids.add(phone_obs["id"])
                observations.append(phone_obs)

        # 7. Rating + Sentiment (if rating exists)
        if rating is not None:
            label = rating_to_label(rating)
            sentiment_obs = {
                **common,
                "id": f"gulesider-sentiment-{org}-{sha256_hex(content)[:16]}",
                "signal_type": "sentiment",
                "evidence_span": f"Gulesider rating {rating}/5 ({review_count or 'N/A'} reviews) for {name or org}",
                "metrics": {"rating": float(rating), "review_count": int(review_count) if review_count else None, "scale": 5},
                "sentiment_label": label,
                "sentiment_model_version": "rule-based-v1",
            }
            if sentiment_obs["id"] not in seen_ids:
                seen_ids.add(sentiment_obs["id"])
                observations.append(sentiment_obs)

    return observations


def main():
    parser = argparse.ArgumentParser(description="Store Gulesider ratings in pipeline format.")
    parser.add_argument("--apify-dataset", type=Path, help="Path to Apify dataset JSONL")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    profiles = load_jsonl(Path(args.profiles))
    print(f"Loaded {len(profiles)} profiles")

    records = load_jsonl(args.apify_dataset)
    print(f"Loaded {len(records)} Gulesider records")

    observations = apify_gulesider_to_observations(records, profiles)
    print(f"Converted {len(observations)} observations (exact org matches only)")

    from collections import Counter
    org_counts = Counter(obs["organisation_number"] for obs in observations)
    print(f"Companies with ratings: {len(org_counts)}")

    write_jsonl(Path(args.output), observations)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
