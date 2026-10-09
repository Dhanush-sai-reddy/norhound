#!/usr/bin/env python3
"""Proff.no company scraper.

Searches Proff.no for each company, extracts org number from search results,
matches to our companies, and fetches profile pages for financials, owners, board.

Usage:
  uv run python scripts/run_proff_scraper.py \
    --profiles data/entry-manifest.jsonl \
    --organisations data/1000-orgs.txt \
    --output out/proff-profiles.jsonl \
    --cache data/proff-cache \
    --report out/proff-report.json
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

from bs4 import BeautifulSoup


UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", """")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_url(url: str, use_browser: bool = True) -> str | None:
    """Fetch URL content. Use Apify web-fetch for browser-based fetching."""
    if use_browser:
        # Use Apify API for browser-based fetching
        api_url = "https://api.apify.com/v2/acts/apify~web-fetch/run-sync-get-dataset-items"
        input_data = {"url": url, "formats": ["markdown"]}
        headers = {
            "Authorization": f"Bearer {APIFY_TOKEN}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(api_url, data=json.dumps(input_data).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                results = json.loads(resp.read())
                if results and isinstance(results, list):
                    return results[0].get("markdown", "")
        except Exception:
            return None
    else:
        headers = {"User-Agent": UA, "Accept": "text/html"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None
    return None


def search_proff(name: str, use_browser: bool = False) -> dict | None:
    """Search Proff.no for a company and return the first result."""
    query = urllib.parse.quote(name)
    url = f"https://www.proff.no/s%C3%B8k-etter-firmanavn?q={query}"
    html = fetch_url(url, use_browser=use_browser)
    if not html:
        return None

    # Try __NEXT_DATA__ JSON first (more reliable)
    next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if next_data_match:
        try:
            data = json.loads(next_data_match.group(1))
            # Navigate the JSON structure to find results
            def find_results(obj, depth=0):
                if depth > 10:
                    return None
                if isinstance(obj, dict):
                    for key in ("results", "companies", "items", "data"):
                        if key in obj and isinstance(obj[key], list) and obj[key]:
                            return obj[key]
                    for v in obj.values():
                        r = find_results(v, depth + 1)
                        if r:
                            return r
                elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
                    return obj
                return None
            results = find_results(data)
            if results:
                first = results[0]
                org = str(first.get("orgNumber") or first.get("org_number") or first.get("organizationNumber") or "")
                org = re.sub(r"\D", "", org)
                profile_url = first.get("url") or first.get("profileUrl") or first.get("sourceUrl") or ""
                company_name = first.get("name") or first.get("companyName") or ""
                if org and profile_url:
                    return {
                        "name": company_name,
                        "url": profile_url if profile_url.startswith("http") else f"https://www.proff.no{profile_url}",
                        "org_number": org,
                    }
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # Fallback: parse HTML
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=re.compile(r"/selskap/")):
        href = link.get("href", "")
        match = re.search(r"/selskap/[^/]+/[^/]+/[^/]+/(\w+)", href)
        if match:
            org_hash = match.group(1)
            name_text = link.get_text(strip=True)
            if name_text:
                return {
                    "name": name_text,
                    "url": f"https://www.proff.no{href}" if href.startswith("/") else href,
                    "org_hash": org_hash,
                }
    return None


def fetch_profile(url: str, use_browser: bool = True) -> dict | None:
    """Fetch a Proff.no company profile page and extract data."""
    html = fetch_url(url, use_browser=use_browser)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    data = {"url": url}

    # Extract org number from page
    org_match = re.search(r"Org\.nr[.:]\s*(\d{9})", html)
    if org_match:
        data["org_number"] = org_match(1)

    # Extract company name
    name_tag = soup.find("h1")
    if name_tag:
        data["name"] = name_tag.get_text(strip=True)

    # Extract revenue
    revenue_match = re.search(r"Driftsinntekter[.:]?\s*([\d\s]+)", html)
    if revenue_match:
        data["revenue"] = revenue_match(1).strip()

    # Extract employees
    emp_match = re.search(r"Ansatte[.:]?\s*(\d+)", html)
    if emp_match:
        data["employees"] = int(emp_match(1))

    # Extract CEO
    ceo_match = re.search(r"Administrerende direktør[.:]?\s*([^<\n]+)", html)
    if ceo_match:
        data["ceo"] = ceo_match(1).strip()

    # Extract industry
    ind_match = re.search(r"Næring[.:]?\s*([^<\n]+)", html)
    if ind_match:
        data["industry"] = ind_match(1).strip()

    return data


def process_company(org: str, profile: dict, cache_dir: Path, use_browser: bool = True) -> tuple[dict | None, dict]:
    """Process a single company."""
    name = profile.get("name", "")
    cache_file = cache_dir / f"{org}.json"

    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data, {"organisation_number": org, "cached": True, "status": "ok" if data.get("org_number") else "no_org"}

    # Search for the company
    result = search_proff(name, use_browser=use_browser)
    if not result:
        return None, {"organisation_number": org, "status": "not_found"}

    # Fetch the profile page
    profile_data = fetch_profile(result["url"], use_browser=use_browser)
    if not profile_data:
        return None, {"organisation_number": org, "status": "fetch_failed"}

    profile_data["search_url"] = result["url"]
    profile_data["retrieved_at"] = utc_now()
    profile_data["content_sha256"] = hashlib.sha256(json.dumps(profile_data, sort_keys=True).encode()).hexdigest()

    # Cache the result
    cache_file.write_text(json.dumps(profile_data, ensure_ascii=False), encoding="utf-8")

    return profile_data, {"organisation_number": org, "status": "ok" if profile_data.get("org_number") else "no_org"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Proff.no company scraper")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--organisations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--use-browser", action="store_true", help="Use browser-based fetching")
    args = parser.parse_args()

    wanted = [line.strip() for line in args.organisations.read_text(encoding="utf-8").splitlines() if line.strip()]
    profiles = {
        str(row["organisation_number"]): row
        for row in (json.loads(line) for line in args.profiles.read_text(encoding="utf-8").splitlines() if line.strip())
    }

    cache_dir = args.cache
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing {len(wanted)} companies with {args.workers} workers")

    results = []
    statuses = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_company, org, profiles[org], cache_dir, args.use_browser): org
            for org in wanted
            if org in profiles
        }
        for i, future in enumerate(as_completed(futures)):
            org = futures[future]
            try:
                data, status = future.result()
                if data:
                    results.append(data)
                statuses.append(status)
                if (i + 1) % 50 == 0:
                    print(f"  {i + 1}/{len(wanted)} done, {len(results)} found")
            except Exception as exc:
                statuses.append({"organisation_number": org, "status": "error", "error": str(exc)[:100]})
            time.sleep(args.delay)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results),
        encoding="utf-8",
    )

    # Write report
    found = sum(1 for s in statuses if s.get("status") == "ok")
    report = {
        "connector": "proff_no_scraper_v1",
        "companies": len(wanted),
        "found": found,
        "observations": len(results),
        "statuses": {s.get("status"): sum(1 for x in statuses if x.get("status") == s.get("status")) for s in statuses},
        "retrieved_at": utc_now(),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nDone: {report}")


if __name__ == "__main__":
    main()
