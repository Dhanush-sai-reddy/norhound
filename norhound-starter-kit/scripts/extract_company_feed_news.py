#!/usr/bin/env python3
"""Extract dated news from a verified company site's RSS/Atom feeds.

Discovers a feed via <link rel="alternate" type="application/rss+xml"> on the
homepage and on news-term subpages (nyheter/aktuelt/presse/blogg/artikler/news),
else common Norwegian/WordPress feed paths, plus a WordPress /feed/ guess under
discovered news pages. Only items that carry a
machine-readable date are emitted; undated items are dropped (never fabricated).
Network access is bounded and robots-aware. No API key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

USER_AGENT = "Mozilla/5.0 (compatible; NorHound-Signalpost/0.1; +https://builderr.ai)"
FEED_PATHS = ("/feed/", "/rss", "/feed.xml", "/nyheter/feed/", "/aktuelt/feed/")
NEWS_PATH_RE = re.compile(r"/(?:nyheter|aktuelt|presse|blogg|blog|artikler|news|media)(?:/|$|\?)", re.I)
NEWS_PAGE_FETCH_LIMIT = 2
NEWS_PAGE_LINK_LIMIT = 5
NS = {"atom": "http://www.w3.org/2005/Atom", "content": "http://purl.org/rss/1.0/modules/content/", "dc": "http://purl.org/dc/elements/1.1/"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def fetch(url: str, timeout: float = 8.0, max_bytes: int = 500_000) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read(max_bytes).decode("utf-8", "replace")
    except Exception:
        return None


def parse_date(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = parsedate_to_datetime(text)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.year < 2000 or dt > datetime.now(timezone.utc).replace(microsecond=0) + __import__("datetime").timedelta(days=2):
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def discover_feed(home_html: str, base: str) -> list[str]:
    urls: list[str] = []
    for m in re.finditer(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', home_html, re.I):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if href:
            urls.append(urllib.parse.urljoin(base, href.group(1)))
    return urls


def collect_news_pages(home_html: str, site: str) -> list[str]:
    site_netloc = urllib.parse.urlparse(site).netloc
    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', home_html, re.I):
        url = urllib.parse.urljoin(site, m.group(1).strip())
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc != site_netloc:
            continue
        if not NEWS_PATH_RE.search(parsed.path):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= NEWS_PAGE_LINK_LIMIT:
            break
    return out


def feed_guesses_for(page_url: str) -> list[str]:
    path = urllib.parse.urlparse(page_url).path
    if re.search(r"/(?:feed|rss)(?:/|$)", path, re.I):
        return []
    return [page_url.rstrip("/") + "/feed/"]


def parse_feed(xml: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml.encode("utf-8", "replace"))
    except Exception:
        return items
    # RSS
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date = parse_date(item.findtext("pubDate") or item.findtext("dc:date", namespaces=NS) or item.findtext("{http://purl.org/dc/elements/1.1/}date"))
        desc = (item.findtext("description") or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or "").strip()
        if title and date:
            items.append({"title": title, "url": link, "date": date, "desc": re.sub(r"<[^>]+>", " ", desc)})
    # Atom
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.get("href") if link_el is not None else ""
        date = parse_date(entry.findtext("{http://www.w3.org/2005/Atom}updated") or entry.findtext("{http://www.w3.org/2005/Atom}published"))
        desc = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or entry.findtext("{http://www.w3.org/2005/Atom}content") or "").strip()
        if title and date:
            items.append({"title": title, "url": link, "date": date, "desc": re.sub(r"<[^>]+>", " ", desc)})
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--exact-only", action="store_true")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    profiles = read_jsonl(Path(args.profiles))

    def process(p: dict) -> list[dict]:
        ev = (p.get("evidence") or {}).get("website") or {}
        if ev.get("status") != "available":
            return []
        val = ev.get("value") or {}
        ident = val.get("identity_assessment") or {}
        status = str(ident.get("status") or "").lower()
        if args.exact_only and status != "exact":
            return []
        if status not in {"exact", "verified", "related_or_uncertain"}:
            return []
        site = ev.get("source_url") or val.get("final_url") or ""
        if not site:
            return []
        home = fetch(site, max_bytes=400_000)
        feeds = discover_feed(home, site) if home else []
        if home:
            for news_page in collect_news_pages(home, site)[:NEWS_PAGE_FETCH_LIMIT]:
                page_html = fetch(news_page, max_bytes=300_000)
                if page_html:
                    feeds += discover_feed(page_html, news_page)
                feeds += feed_guesses_for(news_page)
        parsed_site = urllib.parse.urlparse(site)
        base = f"{parsed_site.scheme}://{parsed_site.netloc}"
        feeds += [base + path for path in FEED_PATHS]
        seen_feed: set[str] = set()
        found_items: list[dict] = []
        feed_used = None
        for feed in feeds:
            if feed in seen_feed:
                continue
            seen_feed.add(feed)
            xml = fetch(feed)
            if not xml or ("<rss" not in xml[:500].lower() and "<feed" not in xml[:500].lower() and "<rdf" not in xml[:500].lower()):
                continue
            items = parse_feed(xml)
            if items:
                found_items = items[:10]
                feed_used = feed
                break
        if not found_items:
            return []
        org = str(p["organisation_number"])
        rows = []
        for it in found_items:
            digest = hashlib.sha256(f"{org}|{it['url']}|{it['date']}".encode()).hexdigest()[:16]
            rows.append({
                "organisation_number": org,
                "platform": "company_site",
                "source_url": it["url"] or site,
                "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "content_sha256": hashlib.sha256((it["title"] + it["date"]).encode()).hexdigest(),
                "exact_entity": True,
                "identity_proof": [{"type": "website_identity_gate", "status": status, "score": ident.get("score")}],
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "company_site",
                "strategy": "company_feed_news",
                "id": f"site-feed-news-{org}-{digest}",
                "signal_type": "public_post",
                "evidence_span": it["title"][:1200],
                "metrics": {"published_at": it["date"], "date_source": "rss_atom", "body_excerpt": it["desc"][:2000], "feed_url": feed_used},
            })
        return rows

    targets = profiles[: args.limit] if args.limit else profiles
    out: list[dict] = []
    stats = {"profiles": 0, "feeds_found": 0, "dated_items": 0, "companies": 0}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process, p): p for p in targets}
        for fut in as_completed(futures):
            stats["profiles"] += 1
            rows = fut.result() or []
            if rows:
                stats["feeds_found"] += 1
                stats["dated_items"] += len(rows)
                out.extend(rows)
    stats["companies"] = len({r["organisation_number"] for r in out})

    write_jsonl(Path(args.output), out)
    stats["output"] = args.output
    Path(args.report).write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
