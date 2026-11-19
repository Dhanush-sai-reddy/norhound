#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
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
    """Refine the company's primary news observation with a date mined from the page body.

    The page belongs to the identity-gated official site, so its body is a
    permitted_public_page. When no date can be mined, the existing undated
    observation is returned unchanged rather than inventing one.
    """
    base = observation(profile)
    if base is None:
        return None
    if not body:
        return base
    primary_url = str(base.get("source_url") or "")
    rows = observations(profile, fetched={primary_url: body})
    refined = rows[0] if rows else None
    if refined is None:
        return base
    if url:
        refined["metrics"] = {**refined["metrics"], "page_url_fetched": url}
    return refined


# How many captured news pages one company may contribute, and how many dated
# items one company may publish. A dated item is a fact; an undated navigation
# page is not, so undated pages are never published beyond one per company.
MAX_NEWS_PAGES = 12
MAX_DATED_ITEMS = 8
BODY_EXCERPT_LIMIT = 5000


def candidate_pages(profile: dict) -> list[dict]:
    """The captured pages under a news path, deepest first, bounded."""
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    pages = [
        page for page in (value.get("pages") or [])
        if NEWS_PATH.search(urlparse(str(page.get("url") or "")).path)
    ]
    # Prefer an individual article over an archive page when the bounded crawl
    # captured both, and keep the order stable so a rerun is byte-identical.
    pages.sort(key=lambda page: (-len([part for part in urlparse(str(page.get("url") or "")).path.split("/") if part]), str(page.get("url") or "")))
    return pages[:MAX_NEWS_PAGES]


def _page_observation(profile: dict, page: dict, *, captured_pages: int, published: str | None = None,
                      date_source: str | None = None, date_precision: str | None = None,
                      body: str | None = None, fetched_at: str | None = None,
                      item_role: str = "primary") -> dict | None:
    """One observation for one captured news page."""
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    url = str(page.get("url") or "")
    digest = str(page.get("content_sha256") or "")
    if not url.startswith(("http://", "https://")) or len(digest) != 64:
        return None
    org = str(profile["organisation_number"])
    title = str(page.get("title") or "Company news/activity page").strip()
    excerpt = str(page.get("main_text_excerpt") or "").strip()
    full_span = f"{title}\n\n{excerpt}" if excerpt else title
    captured_dates = find_dates(title + "\n" + excerpt)
    if published is None and captured_dates:
        # The captured page text carries a date the crawl already saw.
        published = captured_dates[-1]
        date_source = date_source or "captured_text"
        date_precision = date_precision or "mined_from_text"
    metrics: dict = {
        "title": title,
        "captured_news_pages": captured_pages,
        "item_role": item_role,
        "interpretation": "Company-owned activity; not independent sentiment.",
    }
    if body:
        metrics["body_excerpt"] = body[:BODY_EXCERPT_LIMIT]
    if body and fetched_at:
        metrics["body_fetched_at"] = fetched_at
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
        "metrics": metrics,
        "strategy": "company_site_activity",
    }
    if published:
        item["observed_at"] = published
        metrics["published"] = published
        metrics["date_source"] = date_source or "page_body"
        metrics["date_precision"] = date_precision or "mined_from_text"
        if date_precision == "machine_readable":
            metrics["published_at"] = published
    return item


def observations(profile: dict, *, fetched: dict[str, str] | None = None,
                 fetched_at: str | None = None) -> list[dict]:
    """Every publishable activity observation for one company.

    The primary (deepest) captured news page is published once: undated when
    the page states no date, dated when the body states a publication date.
    An additional page is published only when its body carries a
    machine-readable publication timestamp. A date mined from prose can be a
    copyright year or a date mentioned in passing, so it stays reserved for
    the primary page.
    """
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    if website.get("status") != "available" or not identity.get("publishable"):
        return []
    pages = candidate_pages(profile)
    if not pages:
        return []
    fetched = fetched or {}
    rows: list[dict] = []
    dated = 0
    for index, page in enumerate(pages):
        primary = index == 0
        url = str(page.get("url") or "")
        body = fetched.get(url)
        published = None
        date_source = None
        precision = None
        if body:
            machine = find_publication_datetime(body)
            if machine:
                published, date_source, precision = machine, "page_body", "machine_readable"
            elif primary:
                mined = date_from_page_body(body)
                if mined:
                    published, date_source, precision = mined, "page_body", "mined_from_text"
        if published is None and not primary:
            continue
        if not primary and dated >= MAX_DATED_ITEMS:
            break
        row = _page_observation(profile, page, captured_pages=len(pages), published=published,
                                date_source=date_source, date_precision=precision, body=body,
                                fetched_at=fetched_at, item_role="primary" if primary else "additional")
        if row is None:
            continue
        rows.append(row)
        if row.get("observed_at"):
            dated += 1
    return rows


def observation(profile: dict) -> dict | None:
    """The company's primary activity observation: its deepest captured news page."""
    rows = observations(profile)
    return rows[0] if rows else None


def fetch_bodies(profiles: list[dict], *, workers: int = 12, timeout: float = 15.0) -> dict[str, dict[str, str]]:
    """Retrieve the body of every candidate news page, keyed by organisation."""
    tasks: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for profile in profiles:
        org = str(profile.get("organisation_number") or "")
        for page in candidate_pages(profile):
            url = str(page.get("url") or "")
            if not url.startswith(("http://", "https://")):
                continue
            key = (org, url)
            if key in seen:
                continue
            seen.add(key)
            tasks.append(key)

    def retrieve(task: tuple[str, str]):
        org, url = task
        return org, url, fetch_page_body(url, timeout=timeout)

    bodies: dict[str, dict[str, str]] = {}
    if not tasks:
        return bodies
    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for org, url, body in pool.map(retrieve, tasks):
                if body:
                    bodies.setdefault(org, {})[url] = body
    else:
        for task in tasks:
            org, url, body = retrieve(task)
            if body:
                bodies.setdefault(org, {})[url] = body
    return bodies


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract company-owned activity from exact-site bounded news pages.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--fetch-dates", action="store_true", help="Fetch the news page bodies to mine real publication dates")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]

    fetched: dict[str, dict[str, str]] = {}
    fetched_at = None
    if args.fetch_dates:
        fetched_at = datetime.now(timezone.utc).isoformat()
        fetched = fetch_bodies(profiles, workers=args.workers, timeout=args.timeout)

    rows: list[dict] = []
    for profile in profiles:
        org = str(profile.get("organisation_number") or "")
        rows.extend(observations(profile, fetched=fetched.get(org, {}), fetched_at=fetched_at))

    dated = sum(1 for r in rows if r.get("observed_at"))
    datetime_dated = sum(1 for r in rows if (r.get("metrics") or {}).get("published_at"))
    body_retained = sum(1 for r in rows if (r.get("metrics") or {}).get("body_excerpt"))
    companies = {r.get("organisation_number") for r in rows}
    companies_dated = {r.get("organisation_number") for r in rows if r.get("observed_at")}
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "exact_company_site_news_activity_v2",
        "profiles": len(profiles),
        "companies_with_activity": len(companies),
        "companies_with_dated_activity": len(companies_dated),
        "observations": len(rows),
        "dated_observations": dated,
        "datetime_observations": datetime_dated,
        "bodies_retained": body_retained,
        "candidate_pages": sum(len(candidate_pages(profile)) for profile in profiles),
        "pages_fetched": sum(len(bodies) for bodies in fetched.values()),
        "per_company_dated_cap": MAX_DATED_ITEMS,
        "claim_boundary": "Company-owned activity only. A dated item needs a publication date stated by the page itself; only the primary page may carry a date mined from prose.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
