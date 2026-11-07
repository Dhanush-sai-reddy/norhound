#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
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


# Machine-readable publication timestamps: the markup states them, so the
# offset survives verbatim and we never have to invent a time of day.
DATETIME_PATTERNS = (
    re.compile(r'(?:article:published_time|article:modified_time|og:article:published_time)"\s*(?:content|value)\s*=\s*"([^"]{6,64})"', re.I),
    re.compile(r'<time[^>]+datetime\s*=\s*"([^"]{6,64})"', re.I),
    re.compile(r'"(?:datePublished|dateModified|dateCreated)"\s*:\s*"([^"]{6,64})"', re.I),
    re.compile(r'(?:pub|publish(?:ed)?|dato|date)[\s:=]+"?(20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)', re.I),
)


def find_publication_datetime(html: str) -> str | None:
    """First machine-readable publication timestamp on the page, offset preserved."""
    text = html or ""
    for pattern in DATETIME_PATTERNS:
        for raw in pattern.findall(text):
            normalised = normalize_datetime(raw)
            if normalised:
                return normalised
    return None


def normalize_datetime(raw: str | None) -> str | None:
    """ISO-8601 as published. A date-only source stays date-only: widening it to
    midnight would claim precision the source never offered."""
    if not raw:
        return None
    raw = str(raw).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    candidate = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        return datetime.fromisoformat(candidate).isoformat()
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        pass
    match = re.match(r"^(\d{4}-\d{2}-\d{2})([T ]\d{2}:\d{2}(:\d{2})?)?", raw)
    if not match:
        return None
    return raw[:19].replace(" ", "T") if match.group(2) else match.group(1)


def date_from_page_body(html: str) -> str | None:
    """Strip markup, then mine machine-readable dates from the page body."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text)
    dates = find_dates(text)
    return dates[-1] if dates else None


def fetch_page_body(url: str, timeout: float = 20.0) -> str | None:
    """Fetch a page body so a real publication date can be mined from it."""
    try:
        import urllib.request
        request = urllib.request.Request(url, headers={"User-Agent": "NorHound/1.0 (signalpost research)", "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(200000).decode("utf-8", "replace")
    except Exception:
        return None


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
        base["metrics"] = {**base["metrics"], "body_excerpt": body[:5000]}
    if body is None:
        return base
    published_at = find_publication_datetime(body)
    date = published_at or date_from_page_body(body)
    if not date:
        return base
    base["observed_at"] = date
    metrics = {**base["metrics"], "published": date, "date_source": "page_body"}
    if published_at:
        metrics["published_at"] = published_at
    if url:
        metrics["page_url_fetched"] = url
    base["metrics"] = metrics
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
    excerpt = str(page.get("main_text_excerpt") or "").strip()
    full_span = f"{title}\n\n{excerpt}" if excerpt else title
    dates = find_dates(title + "\n" + excerpt)
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
        "evidence_span": full_span[:8000],
        "metrics": {"title": title, "captured_news_pages": len(pages),
                    "interpretation": "Company-owned activity; not independent sentiment."},
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
        if base is None:
            return None
        if (base.get("metrics") or {}).get("date_source") == "page_body":
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

    if args.fetch_dates and args.workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            produced = list(pool.map(produce, profiles))
    else:
        produced = [produce(profile) for profile in profiles]
    rows = [item for item in produced if item]
    dated = sum(1 for r in rows if r.get("observed_at"))
    datetime_dated = sum(1 for r in rows if (r.get("metrics") or {}).get("published_at"))
    body_retained = sum(1 for r in rows if (r.get("metrics") or {}).get("body_excerpt"))
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "exact_company_site_news_activity_v1",
        "profiles": len(profiles),
        "companies_with_activity": len(rows),
        "observations": len(rows),
        "dated_observations": dated,
        "datetime_observations": datetime_dated,
        "bodies_retained": body_retained,
        "claim_boundary": "Company-owned activity only; dates come from the page body where footnote-free.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
