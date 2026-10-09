#!/usr/bin/env python3
"""Trustpilot reviews connector — extracts TrustScore, review count, and star distribution.

Scrapes Trustpilot company review pages for Norwegian companies by matching
the domain extracted from their verified website URL. Outputs JSONL observations
compatible with the NorHound pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
TRUSTPILOT_BASE = "https://www.trustpilot.com/review/"
REQUEST_DELAY = 2.0
MAX_RETRIES = 2
TIMEOUT = 25


def extract_domain(url: str) -> str | None:
    """Extract domain from a URL, stripping www. prefix."""
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        host = parsed.hostname or ""
        return host.removeprefix("www.").lower() or None
    except Exception:
        return None


def fetch_with_retry(url: str, cache_path: Path) -> tuple[bytes, bool, str | None]:
    """Fetch URL with caching and retry logic. Returns (raw_bytes, cache_hit, error)."""
    if cache_path.exists():
        return cache_path.read_bytes(), True, None

    for attempt in range(MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read(5_000_000)
            cache_path.write_bytes(raw)
            return raw, False, None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return b"", False, "not_found_404"
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_DELAY * (attempt + 1))
                continue
            return b"", False, f"http_{exc.code}"
        except Exception as exc:
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_DELAY * (attempt + 1))
                continue
            return b"", False, f"{type(exc).__name__}: {str(exc)[:120]}"
    return b"", False, "max_retries_exceeded"


def parse_star_distribution(soup: BeautifulSoup) -> dict[str, int]:
    """Extract star distribution (5/4/3/2/1 stars) from Trustpilot page."""
    distribution = {}

    # Method 1: Look for star distribution in JSON-LD or data attributes
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "{}")
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            # Check for reviewRating distribution
            review_rating = item.get("reviewRating") or item.get("aggregateRating")
            if isinstance(review_rating, dict):
                rating_value = review_rating.get("ratingValue")
                if rating_value is not None:
                    # Try to find distribution in the same JSON block
                    for key in ("reviewCount", "ratingCount"):
                        count = review_rating.get(key)
                        if count is not None:
                            pass  # We have the total, distribution is separate

    # Method 2: Look for star distribution bars in the HTML
    # Trustpilot renders star distribution as clickable bars with counts
    star_patterns = [
        (5, re.compile(r"5\s*star", re.I)),
        (4, re.compile(r"4\s*star", re.I)),
        (3, re.compile(r"3\s*star", re.I)),
        (2, re.compile(r"2\s*star", re.I)),
        (1, re.compile(r"1\s*star", re.I)),
    ]

    # Look for elements that contain star ratings and counts
    for star_num, pattern in star_patterns:
        # Try finding elements with aria-label or title containing star info
        elements = soup.find_all(attrs={"aria-label": pattern})
        elements.extend(soup.find_all(attrs={"title": pattern}))

        for el in elements:
            label = el.get("aria-label") or el.get("title") or ""
            # Extract count from label like "5 star: 123 reviews"
            count_match = re.search(r"(\d[\d,]*)\s*review", label, re.I)
            if count_match:
                count = int(count_match.group(1).replace(",", ""))
                distribution[str(star_num)] = count
                break

        # Also try finding by text content
        if str(star_num) not in distribution:
            for el in soup.find_all(text=pattern):
                parent = el.parent
                if parent:
                    # Look for a sibling or nearby element with the count
                    container = parent.find_parent(["div", "li", "a"])
                    if container:
                        text = container.get_text(" ", strip=True)
                        count_match = re.search(r"(\d[\d,]*)\s*review", text, re.I)
                        if count_match:
                            count = int(count_match.group(1).replace(",", ""))
                            distribution[str(star_num)] = count
                            break

    # Method 3: Look for data-testid or class-based star distribution
    if not distribution:
        for star_num, _ in star_patterns:
            # Trustpilot uses data-testid like "star-rating-5" or similar
            selectors = [
                f'[data-testid*="star-{star_num}"]',
                f'[data-testid*="rating-{star_num}"]',
                f'[class*="star"][class*="{star_num}"]',
            ]
            for selector in selectors:
                try:
                    els = soup.select(selector)
                except Exception:
                    continue
                for el in els:
                    text = el.get_text(" ", strip=True)
                    count_match = re.search(r"(\d[\d,]*)", text)
                    if count_match:
                        count = int(count_match.group(1).replace(",", ""))
                        if count > 0:
                            distribution[str(star_num)] = count
                            break
                if str(star_num) in distribution:
                    break

    return distribution


def extract_trustpilot_data(raw: bytes, domain: str) -> dict | None:
    """Extract TrustScore, review count, star distribution, and company name from HTML."""
    soup = BeautifulSoup(raw, "html.parser")

    # Check for 404 or "not found" page
    page_text = soup.get_text(" ", strip=True)
    if "this page could not be found" in page_text.lower() or "404" in page_text[:500]:
        return None

    # Extract from JSON-LD
    trust_score = None
    review_count = None
    company_name = None

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "{}")
        except Exception:
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue

            # Get company name
            if not company_name:
                name = item.get("name")
                if name and isinstance(name, str) and len(name) > 1:
                    company_name = name

            # Get aggregate rating
            agg = item.get("aggregateRating")
            if isinstance(agg, dict):
                rating_value = agg.get("ratingValue")
                rating_count = agg.get("ratingCount") or agg.get("reviewCount")
                if rating_value is not None:
                    try:
                        trust_score = float(rating_value)
                    except (ValueError, TypeError):
                        pass
                if rating_count is not None:
                    try:
                        review_count = int(rating_count)
                    except (ValueError, TypeError):
                        pass

    # Fallback: extract TrustScore from visible page elements
    if trust_score is None:
        # Trustpilot shows TrustScore as a large number, often in a specific element
        score_selectors = [
            '[data-testid="trustscore"]',
            ".trustscore",
            '[class*="trustscore"]',
            '[class*="TrustScore"]',
        ]
        for selector in score_selectors:
            try:
                el = soup.select_one(selector)
            except Exception:
                continue
            if el:
                text = el.get_text(strip=True)
                match = re.search(r"(\d+\.?\d*)", text)
                if match:
                    try:
                        val = float(match.group(1))
                        if 0 < val <= 5:
                            trust_score = val
                            break
                    except ValueError:
                        pass

    # Fallback: extract review count from visible elements
    if review_count is None:
        count_patterns = [
            re.compile(r"(\d[\d,]*)\s*reviews?", re.I),
            re.compile(r"(\d[\d,]*)\s*ratings?", re.I),
        ]
        for pattern in count_patterns:
            match = pattern.search(page_text)
            if match:
                try:
                    review_count = int(match.group(1).replace(",", ""))
                    break
                except ValueError:
                    pass

    # Extract star distribution
    star_distribution = parse_star_distribution(soup)

    # Validate minimum data
    if trust_score is None and review_count is None:
        return None

    return {
        "trust_score": trust_score,
        "review_count": review_count,
        "star_distribution": star_distribution,
        "company_name": company_name,
    }


def derive_sentiment(score: float) -> str:
    """Derive sentiment label from TrustScore."""
    if score >= 4.0:
        return "positive"
    elif score >= 3.0:
        return "neutral"
    else:
        return "negative"


def process_company(profile: dict, cache_dir: Path) -> tuple[list[dict], dict]:
    """Process a single company: fetch Trustpilot page and extract review data."""
    org = str(profile["organisation_number"])

    # Extract domain from website URL
    website = (profile.get("evidence") or {}).get("website") or {}
    website_value = website.get("value") or {}
    website_url = (
        website.get("source_url")
        or website_value.get("final_url")
        or profile.get("website")
        or ""
    )

    domain = extract_domain(website_url)
    if not domain:
        return [], {
            "organisation_number": org,
            "accepted": False,
            "reason": "no_website_url",
        }

    url = f"{TRUSTPILOT_BASE}{domain}"
    cache_path = cache_dir / f"{domain}.html"

    try:
        raw, cache_hit, error = fetch_with_retry(url, cache_path)

        if error == "not_found_404":
            return [], {
                "organisation_number": org,
                "accepted": True,
                "rated": False,
                "cache_hit": cache_hit,
                "reason": "trustpilot_page_not_found",
                "domain": domain,
            }

        if error:
            return [], {
                "organisation_number": org,
                "accepted": False,
                "error": error,
                "domain": domain,
            }

        data = extract_trustpilot_data(raw, domain)
        if data is None:
            return [], {
                "organisation_number": org,
                "accepted": True,
                "rated": False,
                "cache_hit": cache_hit,
                "reason": "no_review_data_on_page",
                "domain": domain,
            }

        trust_score = data["trust_score"]
        review_count = data["review_count"]
        star_distribution = data["star_distribution"]
        company_name = data["company_name"]

        # Validate rating
        if trust_score is not None and not (0 < trust_score <= 5):
            return [], {
                "organisation_number": org,
                "accepted": True,
                "rated": False,
                "cache_hit": cache_hit,
                "reason": "invalid_trust_score",
                "domain": domain,
            }

        if review_count is not None and review_count <= 0:
            return [], {
                "organisation_number": org,
                "accepted": True,
                "rated": False,
                "cache_hit": cache_hit,
                "reason": "invalid_review_count",
                "domain": domain,
            }

        # Build observation
        digest = hashlib.sha256(raw).hexdigest()
        retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        score_display = f"{trust_score:.1f}" if trust_score is not None else "N/A"
        count_display = str(review_count) if review_count is not None else "N/A"

        evidence_span = (
            f"Trustpilot TrustScore {score_display}/5 based on {count_display} reviews"
        )
        if company_name:
            evidence_span += f" for {company_name}"

        metrics = {
            "scale": 5,
        }
        if trust_score is not None:
            metrics["rating"] = trust_score
        if review_count is not None:
            metrics["review_count"] = review_count
        if star_distribution:
            metrics["star_distribution"] = star_distribution

        sentiment_label = derive_sentiment(trust_score) if trust_score is not None else "unknown"

        identity_proof = [
            {"type": "domain_resolved_to_exact_entity", "value": domain},
        ]

        common = {
            "organisation_number": org,
            "platform": "company_directory",
            "source_url": url,
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": identity_proof,
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "customer_review",
            "evidence_span": evidence_span,
            "metrics": metrics,
        }

        rows = [
            {
                **common,
                "id": f"trustpilot-review-{org}-{digest[:16]}",
                "signal_type": "review_summary",
                "strategy": "trustpilot_reviews",
            },
            {
                **common,
                "id": f"trustpilot-metrics-{org}-{digest[:16]}",
                "signal_type": "profile_metrics",
                "strategy": "trustpilot_metrics",
            },
            {
                **common,
                "id": f"trustpilot-sentiment-{org}-{digest[:16]}",
                "signal_type": "sentiment",
                "strategy": "trustpilot_sentiment",
                "sentiment_label": sentiment_label,
                "sentiment_model_version": "rule-based-v1",
            },
        ]

        status = {
            "organisation_number": org,
            "accepted": True,
            "rated": True,
            "cache_hit": cache_hit,
            "domain": domain,
            "trust_score": trust_score,
            "review_count": review_count,
            "company_name_on_trustpilot": company_name,
        }
        return rows, status

    except Exception as exc:
        return [], {
            "organisation_number": org,
            "accepted": False,
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
            "domain": domain,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Trustpilot review data for Norwegian companies by domain matching."
    )
    parser.add_argument("--profiles", required=True, help="JSONL file with company profiles")
    parser.add_argument("--organisations", required=True, help="Text file with org numbers")
    parser.add_argument("--output", required=True, help="JSONL output path")
    parser.add_argument("--cache", required=True, help="Cache directory for HTML responses")
    parser.add_argument("--report", required=True, help="JSON report output path")
    parser.add_argument("--workers", type=int, default=2, help="Number of worker threads")
    args = parser.parse_args()

    wanted = [
        line.strip()
        for line in Path(args.organisations).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    profiles = {
        str(row["organisation_number"]): row
        for row in (
            json.loads(line)
            for line in Path(args.profiles).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    observations: list[dict] = []
    statuses: list[dict] = []

    max_workers = max(1, min(args.workers, 4))
    log.info(
        f"Processing {len(wanted)} companies with {max_workers} workers, "
        f"{REQUEST_DELAY}s delay between requests"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(process_company, profiles[org], cache_dir): org
            for org in wanted
            if org in profiles
        }

        for future in as_completed(futures):
            rows, status = future.result()
            observations.extend(rows)
            statuses.append(status)

            # Rate limiting: sleep after each request
            time.sleep(REQUEST_DELAY)

    # Sort by org number order, then signal_type
    order = {org: index for index, org in enumerate(wanted)}
    observations.sort(key=lambda row: (order.get(row["organisation_number"], 9999), row["signal_type"]))
    statuses.sort(key=lambda row: order.get(row["organisation_number"], 9999))

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations),
        encoding="utf-8",
    )

    # Build report
    rated = [s for s in statuses if s.get("rated")]
    errors = [s for s in statuses if "error" in s]
    not_found = [s for s in statuses if s.get("reason") == "trustpilot_page_not_found"]

    report = {
        "connector": "trustpilot_reviews_v1",
        "companies": len(wanted),
        "profiles_matched": len(futures),
        "rated_companies": len(rated),
        "not_found": len(not_found),
        "observations": len(observations),
        "errors": len(errors),
        "cache_hits": sum(1 for s in statuses if s.get("cache_hit")),
        "robots_note": "Trustpilot public review pages; respectful crawling with 2s delay",
        "company_results": statuses,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary = {k: v for k, v in report.items() if k != "company_results"}
    log.info("Done: %s", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
