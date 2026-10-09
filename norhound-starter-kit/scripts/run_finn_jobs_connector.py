#!/usr/bin/env python3
"""Finn.no job-board connector.

Scrapes Finn.no (Norway's largest job board) for job postings by company.
For each company, searches Finn.no job search, extracts job ad URLs, fetches
detail pages, and matches by organisation number.

Only job ads where the org number on the page exactly matches one of the
target companies are emitted as observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
HTTP_TIMEOUT = 30
RATE_LIMIT_SECONDS = 1.0
MAX_ADS_PER_COMPANY = 50
MAX_WORKERS = 4

logger = logging.getLogger("finn_jobs_connector")


def _norm_name(name: str) -> str:
    return str(name or "").translate(
        str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A", "æ": "ae", "Æ": "AE"})
    ).casefold()


def _fetch_url(url: str, cache_path: Path | None = None) -> tuple[bytes, bool]:
    """Fetch URL with caching. Returns (content, cache_hit)."""
    if cache_path and cache_path.exists():
        return cache_path.read_bytes(), True

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        raw = response.read(5_000_000)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(raw)

    return raw, False


def _extract_org_numbers(text: str) -> set[str]:
    """Extract all 9-digit Norwegian org numbers from text."""
    return set(re.findall(r"\b(\d{9})\b", text))


def _extract_job_ad_urls(search_html: bytes) -> list[str]:
    """Extract job ad URLs from search results page HTML."""
    soup = BeautifulSoup(search_html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Job ads link to /job/ad/{ad_id}
        match = re.search(r"/job/ad/([a-zA-Z0-9]+)", href)
        if match:
            ad_id = match.group(1)
            url = f"https://www.finn.no/job/ad/{ad_id}"
            if url not in seen:
                seen.add(url)
                urls.append(url)

    return urls[:MAX_ADS_PER_COMPANY]


def _parse_job_ad(html: bytes) -> dict[str, Any]:
    """Parse a job ad detail page and extract structured data."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {}

    # Try JSON-LD first
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("@type") or "")
            if "JobPosting" in item_type:
                result["title"] = item.get("title") or result.get("title")
                result["published_at"] = item.get("datePosted") or result.get("published_at")
                result["deadline"] = item.get("validThrough") or result.get("deadline")

                hiring_org = item.get("hiringOrganization") or {}
                if isinstance(hiring_org, dict):
                    result["company"] = hiring_org.get("name") or result.get("company")

                job_location = item.get("jobLocation") or {}
                if isinstance(job_location, dict):
                    address = job_location.get("address") or {}
                    if isinstance(address, dict):
                        locality = address.get("addressLocality") or ""
                        region = address.get("addressRegion") or ""
                        result["location"] = ", ".join(p for p in [locality, region] if p) or result.get("location")

    # Fallback: extract from page text
    page_text = soup.get_text(" ", strip=True)

    # Org number patterns: "Org.nr.: XXXXXXXXX", "Org nr: XXXXXXXXX", "organisasjonsnummer"
    org_match = re.search(
        r"(?:org\.?\s*nr\.?|organisasjonsnummer|org\.?\s*nr)\s*[:.]?\s*(\d{9})",
        page_text,
        re.IGNORECASE,
    )
    if org_match:
        result["org_number"] = org_match.group(1)

    # Also check for org number in any meta tags or data attributes
    if "org_number" not in result:
        for meta in soup.find_all("meta"):
            content = meta.get("content") or ""
            org_nums = _extract_org_numbers(content)
            if org_nums:
                result["org_number"] = sorted(org_nums)[0]
                break

    # Title fallback
    if not result.get("title"):
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

    # Company name fallback: look for common patterns
    if not result.get("company"):
        # Try h1 or h2 with company-like text
        for tag in soup.find_all(["h1", "h2"]):
            text = tag.get_text(strip=True)
            if text and len(text) > 2 and "finn" not in text.casefold():
                result["company"] = text
                break

    # Location fallback
    if not result.get("location"):
        loc_match = re.search(
            r"(?:sted|arbeidssted|locality)\s*[:.]?\s*([A-ZÆØÅ][a-zæøåA-ZÆØÅ\s,]+)",
            page_text,
            re.IGNORECASE,
        )
        if loc_match:
            result["location"] = loc_match.group(1).strip()

    # Published date fallback
    if not result.get("published_at"):
        pub_match = re.search(
            r"(?:publisert|published|lagt ut)\s*[:.]?\s*(\d{1,2}\.\s*\w+\s*\d{4}|\d{4}-\d{2}-\d{2})",
            page_text,
            re.IGNORECASE,
        )
        if pub_match:
            result["published_at"] = pub_match.group(1)

    # Deadline fallback
    if not result.get("deadline"):
        deadline_match = re.search(
            r"(?:søknadsfrist|deadline|frist)\s*[:.]?\s*(\d{1,2}\.\s*\w+\s*\d{4}|\d{4}-\d{2}-\d{2})",
            page_text,
            re.IGNORECASE,
        )
        if deadline_match:
            result["deadline"] = deadline_match.group(1)

    return result


def _process_company(
    org: str,
    profile: dict,
    cache_dir: Path,
    target_orgs: set[str],
) -> tuple[list[dict], dict]:
    """Process a single company: search, fetch ads, match, emit observations."""
    company_name = str(profile.get("name") or "")
    if not company_name:
        return [], {"organisation_number": org, "accepted": False, "reason": "no_company_name"}

    search_url = (
        f"https://www.finn.no/job/search?"
        f"q={urllib.parse.quote(company_name)}&sort=PUBLISHED_DESC"
    )
    search_cache = cache_dir / f"search-{org}.html"

    try:
        search_html, search_cache_hit = _fetch_url(search_url, search_cache)
    except Exception as exc:
        return [], {
            "organisation_number": org,
            "accepted": False,
            "error": f"search_failed: {type(exc).__name__}: {str(exc)[:120]}",
        }

    ad_urls = _extract_job_ad_urls(search_html)
    if not ad_urls:
        return [], {
            "organisation_number": org,
            "accepted": True,
            "cache_hit": search_cache_hit,
            "ads_found": 0,
            "reason": "no_job_ads_in_search_results",
        }

    observations: list[dict] = []
    ads_matched = 0
    ads_processed = 0

    for ad_url in ad_urls:
        if ads_processed >= MAX_ADS_PER_COMPANY:
            break
        ads_processed += 1

        # Rate limiting
        time.sleep(RATE_LIMIT_SECONDS)

        ad_cache = cache_dir / f"ad-{org}-{hashlib.sha256(ad_url.encode()).hexdigest()[:12]}.html"

        try:
            ad_html, ad_cache_hit = _fetch_url(ad_url, ad_cache)
        except Exception as exc:
            logger.debug("Failed to fetch ad %s: %s", ad_url, exc)
            continue

        parsed = _parse_job_ad(ad_html)
        ad_org = str(parsed.get("org_number") or "")

        # Match: org number must be in our target set
        if ad_org not in target_orgs:
            continue

        # Only emit if it matches THIS company
        if ad_org != org:
            continue

        ads_matched += 1
        retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        content_hash = hashlib.sha256(ad_html).hexdigest()

        title = str(parsed.get("title") or "")
        company = str(parsed.get("company") or "")
        location = str(parsed.get("location") or "")
        published_at = str(parsed.get("published_at") or "")
        deadline = str(parsed.get("deadline") or "")

        evidence_span = " | ".join(p for p in [title, company, location] if p)[:1200]

        obs_id = f"finn-job-{org}-{hashlib.sha256(ad_url.encode()).hexdigest()[:16]}"

        observation = {
            "id": obs_id,
            "organisation_number": org,
            "signal_type": "job_posting",
            "platform": "job_board",
            "source_url": ad_url,
            "source_class": "job_board",
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "exact_entity": True,
            "identity_proof": [
                {
                    "type": "exact_organisation_number_on_job_ad",
                    "value": ad_org,
                }
            ],
            "evidence_span": evidence_span,
            "metrics": {
                "title": title,
                "company": company,
                "location": location,
                "published_at": published_at,
                "deadline": deadline,
            },
            "retrieved_at": retrieved_at,
            "content_sha256": content_hash,
        }
        observations.append(observation)

    status = {
        "organisation_number": org,
        "accepted": True,
        "cache_hit": search_cache_hit,
        "ads_found": len(ad_urls),
        "ads_processed": ads_processed,
        "ads_matched": ads_matched,
        "observations": len(observations),
    }
    return observations, status


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Finn.no for job postings by company."
    )
    parser.add_argument("--profiles", required=True, help="JSONL with company profiles")
    parser.add_argument("--organisations", required=True, help="Text file with org numbers")
    parser.add_argument("--output", required=True, help="JSONL output path")
    parser.add_argument("--cache", required=True, help="Cache directory")
    parser.add_argument("--report", required=True, help="Report JSON output path")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

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

    target_orgs = set(wanted)

    logger.info("Starting Finn.no job connector for %d companies", len(wanted))

    all_observations: list[dict] = []
    all_statuses: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, MAX_WORKERS))) as pool:
        futures = {
            pool.submit(_process_company, org, profiles[org], cache_dir, target_orgs): org
            for org in wanted
            if org in profiles
        }

        for i, future in enumerate(as_completed(futures), 1):
            org = futures[future]
            try:
                observations, status = future.result()
            except Exception as exc:
                observations = []
                status = {
                    "organisation_number": org,
                    "accepted": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:180]}",
                }
            all_observations.extend(observations)
            all_statuses.append(status)

            if i % 50 == 0 or i == len(futures):
                logger.info("Progress: %d/%d companies processed", i, len(futures))

    # Sort by org order
    order = {org: idx for idx, org in enumerate(wanted)}
    all_observations.sort(key=lambda r: (order.get(r["organisation_number"], 9999), r["id"]))
    all_statuses.sort(key=lambda r: order.get(r["organisation_number"], 9999))

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in all_observations
        ),
        encoding="utf-8",
    )

    # Write report
    companies_with_jobs = sum(1 for s in all_statuses if s.get("ads_matched", 0) > 0)
    report = {
        "connector": "finn_jobs_v1",
        "companies_processed": len(wanted),
        "companies_with_jobs": companies_with_jobs,
        "total_observations": len(all_observations),
        "errors": sum(1 for s in all_statuses if "error" in s),
        "claim_boundary": (
            "Job ads from Finn.no matched by exact organisation number on the ad page. "
            "Only ads where the org number matches the target company are published."
        ),
        "company_results": all_statuses,
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    logger.info(
        "Done: %d observations from %d companies",
        len(all_observations),
        companies_with_jobs,
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "company_results"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
