#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse


NEWS_PATH = re.compile(r"/(?:news|press|aktuelt|nyheter|artikler|blog|media|medier|nyhetsarkiv|pressemeldinger|rapporter|publikasjoner|insights|case|cases|referanser|prosjekter)(?:/|$)", re.I)

ISO_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
NO_MONTHS = {m: i + 1 for i, m in enumerate((
    "januar", "februar", "mars", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "desember"))}
NO_DATE = re.compile(r"(\d{1,2})\.?\s+(" + "|".join(NO_MONTHS) + r")\s+(20\d{2})", re.I)
NUMERIC_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(20\d{2})")


def find_dates(text: str) -> list[str]:
    """Mine ISO, Norwegian-month and numeric dates from page text. Sorted, deduped."""
    found = set()
    for match in ISO_DATE.findall(text or ""):
        found.add(f"{match[0]}-{match[1]}-{match[2]}")
    for day, month, year in NO_DATE.findall(text or ""):
        found.add(f"{year}-{NO_MONTHS[month.casefold()]:02d}-{int(day):02d}")
    for day, month, year in NUMERIC_DATE.findall(text or ""):
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            found.add(f"{year}-{int(month):02d}-{int(day):02d}")
    return sorted(found)


def date_from_page_body(html: str) -> str | None:
    """Strip markup, then mine machine-readable dates from the page body."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text)
    dates = find_dates(text)
    return dates[-1] if dates else None


def fetch_dated_observation(profile: dict, *, body: str | None = None, url: str | None = None) -> dict | None:
    """Refine a news-page observation with a real date mined from the page body.

    The page belongs to the identity-gated official site, so its body is a
    permitted_public_page. When no date can be mined, the existing undated
    observation is returned unchanged rather than inventing one.
    """
    base = observation(profile)
    if base is None:
        return None
    if body:
        base["metrics"] = {**base["metrics"], "body_excerpt": body[:1000]}
    if body is None:
        return base
    date = date_from_page_body(body)
    if not date:
        return base
    base["observed_at"] = date
    base["metrics"] = {**base["metrics"], "published": date, "date_source": "page_body"}
    if url:
        base["metrics"] = {**base["metrics"], "page_url_fetched": url}
    return base


def observation(profile: dict) -> dict | None:
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    if website.get("status") != "available" or not identity.get("publishable"):
        return None
    pages = [
        page for page in (value.get("pages") or [])
        if NEWS_PATH.search(urlparse(str(page.get("url") or "")).path)
    ]
    if not pages:
        return None
    # Prefer an individual article over an archive page when the bounded crawl
    # captured both. One observation is enough to prove site activity without
    # rewarding a site for repeated navigation links.
    pages.sort(key=lambda page: (-len([part for part in urlparse(str(page.get("url") or "")).path.split("/") if part]), str(page.get("url") or "")))
    page = pages[0]
    url = str(page.get("url") or "")
    digest = str(page.get("content_sha256") or "")
    if not url.startswith(("http://", "https://")) or len(digest) != 64:
        return None
    org = str(profile["organisation_number"])
    title = str(page.get("title") or "Company news/activity page").strip()
    dates = find_dates(title + "\n" + str(page.get("main_text_excerpt") or ""))
    item = {
        "id": "company-site-news-" + hashlib.sha256(f"{org}|{url}".encode()).hexdigest()[:24],
        "organisation_number": org,
        "platform": "company_site",
        "signal_type": "public_post",
        "source_url": url,
        "retrieved_at": website.get("retrieved_at"),
        "content_sha256": digest,
        "exact_entity": True,
        "identity_proof": [{"type": "website_identity_gate", "score": identity.get("score"), "method": identity.get("method")}],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_site",
        "evidence_span": title[:1200],
        "metrics": {"captured_news_pages": len(pages), "interpretation": "Company-owned activity; not independent sentiment."},
        "strategy": "company_site_activity",
    }
    if dates:
        item["observed_at"] = dates[-1]
        item["metrics"] = {**item["metrics"], "published": dates[-1]}
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract company-owned activity from exact-site bounded news pages.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--fetch-dates", action="store_true", help="Fetch the news page body to mine real publication dates")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]

    def produce(profile: dict):
        if not args.fetch_dates:
            return observation(profile)
        base = observation(profile)
        if base is None or base.get("observed_at"):
            return base
        url = str(base.get("source_url") or "")
        if not url.startswith(("http://", "https://")):
            return base
        try:
            import urllib.request
            request = urllib.request.Request(url, headers={"User-Agent": "NorHound/1.0 (signalpost research)", "Accept": "text/html,application/xhtml+xml"})
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read(200000).decode("utf-8", "replace")
        except Exception:
            return base
        return fetch_dated_observation(profile, body=body, url=url)

    rows = [item for profile in profiles if (item := produce(profile))]
    dated = sum(1 for r in rows if r.get("observed_at"))
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "exact_company_site_news_activity_v1",
        "profiles": len(profiles),
        "companies_with_activity": len(rows),
        "observations": len(rows),
        "dated_observations": dated,
        "claim_boundary": "Company-owned activity only; dates come from the page body where footnote-free.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
