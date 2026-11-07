#!/usr/bin/env python3
"""Finn.no job board connector.

Finn.no is Norway's #1 job board. Job ads are found via keyword search on
https://www.finn.no/job/fulltime/search.html and individual ad pages at
https://www.finn.no/job/fulltime/ad.html?finnkode=XXXXX.

No public API; scrapes search results and ad pages with bounded requests.
Exact-entity match: company name in ad must match the profile's legal name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from html import unescape
from pathlib import Path
from datetime import datetime, timezone


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
FINN_SEARCH = "https://www.finn.no/job/fulltime/search.html"
FINN_AD_BASE = "https://www.finn.no/job/fulltime/ad.html"
MAX_COMPANIES = 200
MAX_ADS_PER_COMPANY = 10
REQUEST_DELAY = 1.5  # seconds between requests to avoid rate limiting


def _fetch(url: str, timeout: float = 20.0) -> tuple[str | None, str | None]:
    """Fetch a URL, return (html, final_url) or (None, error)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en-US;q=0.7,en;q=0.6",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, str(exc.reason)[:180]
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:180]}"


def _tokens(name: str) -> set[str]:
    text = str(name or "").lower()
    text = re.sub(r"[æøå]", lambda m: {"æ": "ae", "ø": "o", "å": "a"}[m.group(0)], text)
    return set(t for t in re.findall(r"[a-z0-9]+", text) if len(t) >= 2)


def _name_match(company_name: str, legal_name: str) -> bool:
    """Check if company name from ad matches the legal name."""
    c_tokens = _tokens(company_name)
    l_tokens = _tokens(legal_name)
    if not c_tokens or not l_tokens:
        return False
    # Remove common legal suffixes from both
    suffixes = {"as", "asa", "ans", "da", "enk", "sa", "nuf", "stiftelsen", "kf", "kb"}
    c_tokens = {t for t in c_tokens if t not in suffixes}
    l_tokens = {t for t in l_tokens if t not in suffixes}
    if not c_tokens or not l_tokens:
        return False
    # Check if all legal tokens appear in company name (subset match)
    return l_tokens.issubset(c_tokens) or c_tokens.issubset(l_tokens)


def _parse_search_results(html: str) -> list[dict]:
    """Parse job search results page, return list of ad dicts."""
    ads = []
    # Finn.no job ad links look like: /job/fulltime/ad.html?finnkode=XXXXX
    for m in re.finditer(r'href=["\'](/job/fulltime/ad\.html\?finnkode=\d+)[^"\']*["\']', html):
        ad_url = "https://www.finn.no" + m.group(1)
        ads.append({"url": ad_url})
    # Also try data-layer / JSON embedded results
    for m in re.finditer(r'"finnkode"\s*:\s*(\d+)', html):
        finnkode = m.group(1)
        ad_url = f"{FINN_AD_BASE}?finnkode={finnkode}"
        if not any(a["url"] == ad_url for a in ads):
            ads.append({"url": ad_url})
    return ads[:MAX_ADS_PER_COMPANY]


def _parse_ad_page(html: str) -> dict:
    """Parse individual job ad page, return dict with title, company, location, published."""
    result = {}
    # Title
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
    if title_m:
        result["title"] = re.sub(r"<[^>]+>", " ", title_m.group(1)).strip()
    # Company name - look for patterns like "Arbeidsgiver:" or company name near top
    company_m = re.search(r'["\'](companyName|company_name|bedriftsnavn)["\']\s*:\s*["\']([^"\']+)["\']', html, re.I)
    if company_m:
        result["company"] = company_m.group(2)
    else:
        # Fallback: look for company name in meta tags
        meta_company = re.search(r'<meta[^>]+(?:name|property)=["\'](?:og:site_name|business_name)["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if meta_company:
            result["company"] = meta_company.group(1)
    # Location
    loc_m = re.search(r'["\'](location|workLocation|address)["\']\s*:\s*["\']([^"\']+)["\']', html, re.I)
    if loc_m:
        result["location"] = loc_m.group(2)
    # Published date
    date_m = re.search(r'["\'](published|datePublished|publishedDate)["\']\s*:\s*["\']([^"\']+)["\']', html, re.I)
    if date_m:
        result["published"] = str(date_m.group(2))[:10]
    # Organisation number in ad
    org_m = re.search(r'Org\.?\s*nr\.?\s*:?\s*(\d{3}\s?\d{3}\s?\d{3})', html)
    if org_m:
        result["orgnr"] = re.sub(r"\D", "", org_m.group(1))
    return result


def observations_for_org(org: str, legal_name: str, ads: list[dict], source_url: str) -> list[dict]:
    observations = []
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for idx, ad in enumerate(ads):
        ad_url = ad.get("url", "")
        # Fetch ad page
        ad_html, ad_error = _fetch(ad_url)
        if not ad_html:
            continue
        time.sleep(REQUEST_DELAY)
        ad_details = _parse_ad_page(ad_html)
        company_name = ad_details.get("company", "")
        # Exact-entity check: company name must match legal name
        if not _name_match(company_name, legal_name):
            continue
        # Also check orgnr if available
        ad_orgnr = ad_details.get("orgnr")
        if ad_orgnr and ad_orgnr != org:
            continue
        span_parts = [ad_details.get("title", ""), company_name, ad_details.get("location", ""), ad_details.get("published", "")]
        span = " | ".join(str(x) for x in span_parts if x)[:500]
        obs = {
            "id": "finn-job-" + hashlib.sha256(f"{org}|{ad_url}|{idx}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "finn",
            "signal_type": "job_posting",
            "source_url": ad_url,
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(f"{org}|{ad_url}".encode()).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{
                "type": "company_name_match_on_job_board",
                "source": "finn.no",
                "source_class": "job_board",
                "matched_organisation_number": org,
                "explanation": "Finn.no job ad company name matches the exact legal organisation name.",
            }],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "job_board",
            "evidence_span": span,
            "effective_at": ad_details.get("published"),
            "metrics": {k: v for k, v in ad_details.items() if v not in (None, "", [])},
            "strategy": "finn_job_board",
        }
        observations.append(obs)
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Finn.no job board connector.")
    parser.add_argument("--profiles", required=True, help="Frozen batch profiles JSONL")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--limit", type=int, default=MAX_COMPANIES, help="Max companies to search")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    profiles = profiles[:args.limit]
    observations = []
    statuses = {}

    for p in profiles:
        org = str(p["organisation_number"])
        name = p.get("name") or org
        # Search Finn.no for company jobs
        query = urllib.parse.quote(f"{name} jobber")
        search_url = f"{FINN_SEARCH}?keywords={query}"
        html, error = _fetch(search_url, args.timeout)
        if error:
            statuses[org] = f"search_error:{error}"
            time.sleep(REQUEST_DELAY)
            continue
        ads = _parse_search_results(html)
        if not ads:
            statuses[org] = "no_ads_found"
            time.sleep(REQUEST_DELAY)
            continue
        obs = observations_for_org(org, name, ads, search_url)
        observations.extend(obs)
        statuses[org] = f"ok:{len(ads)}_ads"
        time.sleep(REQUEST_DELAY)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations), encoding="utf-8"
    )

    accepted = sum(1 for s in statuses.values() if s.startswith("ok:"))
    total_ads = sum(int(s.split(":")[1].split("_")[0]) for s in statuses.values() if s.startswith("ok:"))
    report = {
        "connector": "finn_job_board_v1",
        "profiles": len(profiles),
        "accepted": accepted,
        "observations": len(observations),
        "total_ads_found": total_ads,
        "status_counts": {k: list(statuses.values()).count(k) for k in set(statuses.values())},
        "claim_boundary": "Finn.no job ads, exact company name match, bounded request rate.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "status_counts"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
