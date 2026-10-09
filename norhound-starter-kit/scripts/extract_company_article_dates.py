#!/usr/bin/env python3
"""Extract dated news articles from a verified company site.

Two hops: homepage -> news section -> article detail. Parses schema.org
NewsArticle/BlogPosting/Article JSON-LD (headline + datePublished), with
<time datetime> and og:published_time/og:article:published_time fallbacks.
Only dated items are emitted. Bounded and robots-aware. No API key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.website import USER_AGENT, _robots_allowed, assert_public_url  # noqa: E402

NEWS_SECTION = re.compile(r"(nyhet|nyheter|aktuelt|aktuell|news|press|pressemelding|presse|media|blogg|artikel|artikkel|innsikt|insight|fag-og-forskning|siste|meld)", re.I)
ARTICLE_LIKE = re.compile(r"(/20\d\d/|nyhet|artikkel|artikel|blogg|story|sak/|/p/|/nyheter/[^/]+/|/[a-z0-9-]{12,}/?$)", re.I)
SPAM_URL = re.compile(r"(/comments/feed|#comment|replytocom=|/feed/?$)", re.I)
SPAM_TITLE = re.compile(r"^(comment on|kommentar til|hello world|hei verden|sample page|eksempelside)\b", re.I)
_NO_MONTHS = ("januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "desember")
_NO_MONTH_RE = re.compile(r"\b(\d{1,2})\.\s*(januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember)\s*(\d{4})\b", re.I)
_NUMERIC_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
ARTICLE_TYPES = {"NewsArticle", "ReportageNewsArticle", "BlogPosting", "Article", "TechArticle", "PressRelease", "OpinionNewsArticle", "AnalysisNewsArticle"}
DATE_META = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|og:published_time|datePublished|date)["\'][^>]+content=["\']([^"\']+)["\']', re.I)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def fetch(url: str, timeout: float = 8.0, max_bytes: int = 600_000) -> str | None:
    try:
        assert_public_url(url)
    except ValueError:
        return None
    if not _robots_allowed(url, timeout):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
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
    if dt.year < 2000 or dt > datetime.now(timezone.utc) + timedelta(days=2):
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def jsonld_articles(html: str) -> list[dict]:
    import html as _html
    html = _html.unescape(html.replace("&#x2B;", "+").replace("&#43;", "+"))
    out: list[dict] = []
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node); continue
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            typ = node.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if any(t in ARTICLE_TYPES for t in types if t):
                headline = node.get("headline") or node.get("name")
                date = node.get("datePublished") or node.get("dateModified")
                dd = parse_date(date if isinstance(date, str) else None)
                if headline and dd:
                    out.append({"title": str(headline).strip(), "date": dd, "desc": str(node.get("description") or "")[:2000]})
    return out


def date_from_html(html: str) -> str | None:
    m = DATE_META.search(html)
    if m:
        d = parse_date(m.group(1))
        if d:
            return d
    m = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.I)
    if m:
        d = parse_date(m.group(1))
        if d:
            return d
    # Norwegian textual dates: "1. januar 2024" (first 4000 chars, like noneedofit)
    text = re.sub(r"<[^>]+>", " ", html[:4000])
    m = _NO_MONTH_RE.search(text)
    if m:
        try:
            day, month, year = int(m.group(1)), _NO_MONTHS.index(m.group(2).lower()) + 1, int(m.group(3))
            return parse_date(f"{year:04d}-{month:02d}-{day:02d}")
        except Exception:
            pass
    m = _NUMERIC_DATE_RE.search(text)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return parse_date(f"{year:04d}-{month:02d}-{day:02d}")
        except Exception:
            pass
    return None


def links(html: str, base: str) -> list[str]:
    urls = []
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', html, re.I):
        u = urllib.parse.urljoin(base, href)
        p = urllib.parse.urlparse(u)
        if p.scheme in ("http", "https") and p.netloc == urllib.parse.urlparse(base).netloc:
            urls.append(u.split("?")[0])
    return urls


def process(profile: dict, max_articles: int) -> list[dict]:
    ev = (profile.get("evidence") or {}).get("website") or {}
    if ev.get("status") != "available":
        return []
    val = ev.get("value") or {}
    ident = val.get("identity_assessment") or {}
    if str(ident.get("status") or "").lower() != "exact":
        return []
    site = ev.get("source_url") or val.get("final_url") or ""
    if not site:
        return []
    home = fetch(site, max_bytes=400_000)
    if not home:
        return []
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(site))
    home_links = links(home, site)
    sections = [u for u in home_links if NEWS_SECTION.search(urllib.parse.urlparse(u).path)][:6]
    sections += [base + p for p in ("/nyheter", "/aktuelt", "/news", "/nyheter/", "/aktuelt/", "/presse")]
    seen = set()
    article_urls: list[tuple[str, str]] = []  # (url, section_html)
    section_html: dict[str, str] = {}
    for sec in sections:
        if sec in seen:
            continue
        seen.add(sec)
        html = fetch(sec)
        if not html:
            continue
        section_html[sec] = html
        for u in links(html, sec):
            up = urllib.parse.urlparse(u)
            if up.netloc == urllib.parse.urlparse(sec).netloc and ARTICLE_LIKE.search(up.path) and u not in seen and not SPAM_URL.search(u):
                article_urls.append((u, sec))
    org = str(profile["organisation_number"])
    rows: list[dict] = []
    used = set()
    for url, sec in article_urls:
        if len(rows) >= max_articles or url in used:
            break
        used.add(url)
        html = fetch(url)
        if not html:
            continue
        arts = jsonld_articles(html)
        title = None; date = None; desc = ""
        if arts:
            title, date, desc = arts[0]["title"], arts[0]["date"], arts[0]["desc"]
        else:
            date = date_from_html(html)
            mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
            title = re.sub(r"\s+", " ", mt.group(1)).strip() if mt else url
            if date and not title:
                continue
        if not (title and date):
            continue
        if SPAM_TITLE.search(title):
            continue
        digest = hashlib.sha256(f"{org}|{url}|{date}".encode()).hexdigest()[:16]
        rows.append({
            "organisation_number": org,
            "platform": "company_site",
            "source_url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "content_sha256": hashlib.sha256((title + date).encode()).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{"type": "website_identity_gate", "status": "exact", "score": ident.get("score")}],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_site",
            "strategy": "company_article_date",
            "id": f"site-article-news-{org}-{digest}",
            "signal_type": "public_post",
            "evidence_span": title[:1200],
            "metrics": {"published_at": date, "date_source": "jsonld_or_meta", "body_excerpt": desc[:2000]},
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--max-articles", type=int, default=8)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    if args.limit:
        profiles = profiles[: args.limit]
    out: list[dict] = []
    stats = {"profiles": 0, "companies": 0, "dated_items": 0}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process, p, args.max_articles): p for p in profiles}
        for fut in as_completed(futures):
            stats["profiles"] += 1
            rows = fut.result() or []
            out.extend(rows)
    stats["companies"] = len({r["organisation_number"] for r in out})
    stats["dated_items"] = len(out)
    write_jsonl(Path(args.output), out)
    stats["output"] = args.output
    Path(args.report).write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
