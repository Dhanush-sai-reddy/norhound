#!/usr/bin/env python3
"""Company-site RSS/Atom + WordPress REST feed discovery for dated news.

Fetches the identity-gated company website, finds <link rel="alternate"> feed
links, WordPress /feed/ or /wp-json/wp/v2/posts, parses dated items, and
publishes activity observations. Only dated items are published.

Adapted from noneedofit/provenance activity/feeds.py (competitor repo).
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
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.evidence import utc_now  # noqa: E402
from norway_company_agent.identity import apply_website_identity_gate  # noqa: E402
from norway_company_agent.website import fetch_website  # noqa: E402

UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
MAX_ITEMS = 20
NO_MONTHS = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}
NO_MONTH_RE = re.compile(r"\b(\d{1,2})\.\s*(" + "|".join(NO_MONTHS) + r")\s*(\d{4})\b", re.I)
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(elem, *names):
    wanted = {n.lower() for n in names}
    for child in list(elem):
        if _local(child.tag) in wanted and child.text and child.text.strip():
            return child.text.strip()
    return None


def normalize_iso_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt.date().isoformat()
    except Exception:
        pass
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    return None


def normalize_datetime(raw: str | None) -> str | None:
    """Publication timestamp exactly as the source published it.

    The verified-pool key for a dated-news fact is the lower-cased string
    ``"<title> (<published datetime>)"``, and the reference example carries the
    source's own UTC offset (``2025-09-22T20:00:00+02:00``). Converting to UTC
    or dropping the time makes the value unmatchable, so the offset the feed
    published is kept verbatim and never invented: a naive timestamp stays
    naive and a date-only one stays date-only.
    """
    if not raw:
        return None
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw  # date-only source: inventing a midnight time would fake precision
    dt = None
    try:
        dt = datetime.fromisoformat(raw[:-1] + "+00:00") if raw.endswith(("Z", "z")) else datetime.fromisoformat(raw)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(raw)
        except Exception:
            dt = None
    if dt is None:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})([T ]\d{2}:\d{2}:\d{2})?", raw)
        return raw[:19].replace(" ", "T") if m and m.group(2) else (m.group(1) if m else None)
    return dt.isoformat()


def news_claim_value(title: str | None, published: str | None) -> str | None:
    if not title:
        return None
    title = " ".join(str(title).split())
    return f"{title} ({published})" if published else title


def parse_feed(text: str) -> list[dict]:
    """Parse RSS 2.0 or Atom feed into [{title, url, published, published_datetime, published_raw}]."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    items = []
    for elem in root.iter():
        local = _local(elem.tag)
        if local == "item":
            title = _child_text(elem, "title")
            link = _child_text(elem, "link")
            pub = _child_text(elem, "pubdate", "pubDate", "date")
            items.append({"title": title, "url": link, "published": normalize_iso_date(pub), "published_datetime": normalize_datetime(pub), "published_raw": pub})
        elif local == "entry":
            title = _child_text(elem, "title")
            links = [c for c in list(elem) if _local(c.tag) == "link"]
            link = None
            for l in links:
                if l.get("rel") in (None, "alternate"):
                    link = l.get("href"); break
            if not link and links:
                link = links[0].get("href")
            pub = _child_text(elem, "published") or _child_text(elem, "updated")
            items.append({"title": title, "url": link, "published": normalize_iso_date(pub), "published_datetime": normalize_datetime(pub), "published_raw": pub})
    return items


def find_feed_urls(html: str, base_url: str | None) -> list[str]:
    """Find RSS/Atom feed URLs advertised by a homepage.

    Attributes may appear in any order (``rel`` before ``type`` or after it), so
    each ``<link>`` tag is parsed attribute by attribute instead of by one
    attribute-order-sensitive pattern.
    """
    urls = []
    for tag in re.findall(r"<link[^>]*>", html or "", re.I):
        rel_m = re.search(r"rel=[\"']?([^\"'\s>]+)", tag, re.I)
        type_m = re.search(r"type=[\"']?([^\"'\s>]+)", tag, re.I)
        href_m = re.search(r"href=[\"']?([^\"'\s>]+)", tag, re.I)
        if not (rel_m and type_m and href_m):
            continue
        if "alternate" not in rel_m.group(1).lower():
            continue
        if not ("rss" in type_m.group(1).lower() or "atom" in type_m.group(1).lower()):
            continue
        href = href_m.group(1).strip()
        resolved = urllib.parse.urljoin(base_url or "", href)
        if resolved.startswith(("http://", "https://")):
            urls.append(resolved)
    # WordPress /feed/ guess
    if base_url:
        parsed = base_url.rstrip("/")
        if parsed.startswith(("http://", "https://")):
            urls.append(f"{parsed}/feed/")
            urls.append(f"{parsed}/wp-json/wp/v2/posts?per_page=20")
    return urls


def resolve_site_url(website_value: dict, source_url: str | None = None) -> str:
    """Resolve the site root used for feed discovery.

    ``source_url`` lives on the website evidence record, not inside its
    ``value`` payload, so the value-level URLs are preferred and the evidence
    URL is only a fallback.
    """
    for candidate in (
        website_value.get("final_url"),
        website_value.get("requested_url"),
        source_url,
    ):
        text = str(candidate or "").strip()
        if text.startswith(("http://", "https://")):
            return text
    return ""


def exact_entity_for_status(status: str) -> bool:
    """Only a verified website identity may publish an exact-entity claim."""
    return str(status or "").lower() in {"exact", "verified"}


def fetch(url: str, timeout: float = 15.0) -> tuple[str | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), resp.geturl()
    except Exception:
        return None, None


def observations_for_org(org: str, website_value: dict, timeout: float = 15.0, source_url: str | None = None) -> list[dict]:
    observations = []
    site_url = resolve_site_url(website_value, source_url)
    identity = website_value.get("identity_assessment") or {}
    if not exact_entity_for_status(str(identity.get("status") or "")):
        return observations
    homepage_html = ""
    if site_url:
        body, _ = fetch(site_url, timeout)
        homepage_html = body or ""

    feed_urls = find_feed_urls(homepage_html, site_url)
    seen_urls = set()
    candidates = []
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    for feed_url in feed_urls:
        if feed_url in seen_urls:
            continue
        seen_urls.add(feed_url)
        body, final_url = fetch(feed_url, timeout)
        if not body:
            continue
        # WordPress REST API
        if "wp-json" in feed_url:
            try:
                data = json.loads(body)
            except ValueError:
                continue
            if isinstance(data, list):
                for post in data:
                    title_obj = post.get("title") or {}
                    title = title_obj.get("rendered") if isinstance(title_obj, dict) else None
                    link = post.get("link")
                    date_raw = post.get("date") or post.get("date_gmt")
                    published = normalize_iso_date(date_raw) if date_raw else None
                    if title and link and published:
                        candidates.append({"title": title, "url": link, "published": published,
                                           "published_datetime": normalize_datetime(date_raw),
                                           "published_raw": date_raw})
            continue
        # RSS/Atom
        items = parse_feed(body)
        for item in items:
            if item.get("url") and item.get("published") and item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                candidates.append(item)

    candidates.sort(key=lambda x: x.get("published") or "", reverse=True)
    for item in candidates[:MAX_ITEMS]:
        span = " — ".join(str(x) for x in (item.get("title"), item.get("published_raw")) if x)[:500]
        digest_input = f"{org}|{item.get('url')}".encode()
        obs = {
            "id": "feed-news-" + hashlib.sha256(f"{org}|{item.get('url')}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "company_site",
            "signal_type": "public_post",
            "source_url": item.get("url"),
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(f"{org}|{item.get('url')}|{item.get('published')}".encode()).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{
                "type": "linked_from_verified_site",
                "source": site_url,
                "source_class": "company_site",
                "matched_organisation_number": org,
                "explanation": "Feed discovered from the identity-gated company website.",
            }],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_site",
            "evidence_span": span,
            "effective_at": item.get("published"),
            "observed_at": item.get("published"),
            "metrics": {
                "title": item.get("title") or "",
                "source": "company website",
                "published_at": item.get("published_datetime") or item.get("published"),
                "published_date": item.get("published"),
                "claim_value": news_claim_value(item.get("title"), item.get("published_datetime") or item.get("published")),
            },
            "strategy": "rss_atom_feed_discovery",
        }
        observations.append(obs)

    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="RSS/Atom + WordPress REST feed discovery for dated news.")
    parser.add_argument("--profiles", required=True, help="Frozen batch profiles JSONL")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    observations = []
    statuses = {}

    for p in profiles:
        org = str(p["organisation_number"])
        evidence = (p.get("evidence") or {})
        website = evidence.get("website") or {}
        if website.get("status") != "available":
            statuses[org] = "no_website"
            continue
        wv = website.get("value") or {}
        obs = observations_for_org(org, wv, args.timeout, source_url=website.get("source_url"))
        observations.extend(obs)
        statuses[org] = f"ok:{len(obs)}"
        time.sleep(0.3)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations), encoding="utf-8"
    )

    accepted = sum(1 for s in statuses.values() if s.startswith("ok:"))
    report = {
        "connector": "feed_news_discovery_v1",
        "profiles": len(profiles),
        "accepted": accepted,
        "observations": len(observations),
        "status_counts": {k: list(statuses.values()).count(k) for k in set(statuses.values())},
        "claim_boundary": "RSS/Atom + WordPress REST feeds from identity-gated company websites; only dated items published.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "status_counts"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
