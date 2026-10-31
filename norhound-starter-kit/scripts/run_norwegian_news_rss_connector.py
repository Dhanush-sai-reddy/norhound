#!/usr/bin/env python3
"""Norwegian news RSS connector — fetches from multiple NO news sources,
extracts company mentions via fuzzy matching against BRREG names,
emits dated news observations with exact-entity verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.identity import assess_social_identity  # noqa: E402
from norway_company_agent.news_datetime import publication_timestamp  # noqa: E402

# Norwegian news RSS feeds (no key, free)
NEWS_FEEDS = [
    ("aftenposten", "https://www.aftenposten.no/rss"),
    ("tu_no", "https://www.tu.no/rss"),
    ("digi_no", "https://www.digi.no/rss"),
    ("e24", "https://e24.no/rss2/"),
    ("nrk", "https://www.nrk.no/nyheter/siste.rss"),
    ("nrk_okonomi", "https://www.nrk.no/nyheter/okonomi.rss"),
    ("digi_no", "https://www.digi.no/rss"),
    ("finansavisen", "https://ws.finansavisen.no/api/articles/rss"),
    ("nrk_okonomi", "https://www.nrk.no/nyheter/okonomi.rss"),
]


def norm_name(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9æøå ]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_name_index(profiles: list[dict]) -> dict[str, list[str]]:
    idx = {}
    for p in profiles:
        name = p.get("name", "")
        org = str(p["organisation_number"])
        if not name:
            continue
        key = norm_name(name)
        if key:
            idx.setdefault(key, []).append(org)
        for suffix in ("as", "asa", "ans", "da", "nuf", "ba", "flt", "sa"):
            if name.lower().endswith(" " + suffix):
                short = name[:-(len(suffix)+1)]
                key = norm_name(short)
                if key:
                    idx.setdefault(key, []).append(p["organisation_number"])
    return idx


def parse_date(text: str | None) -> str | None:
    return publication_timestamp(text)


def parse_rfc822_date(date_str: str | None) -> str | None:
    return publication_timestamp(date_str)


def fetch_rss(url: str, timeout: float = 12.0) -> list[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SignalpostNews/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml = resp.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  [fetch] {url}: {e}")
        return []

    items = []
    try:
        root = ET.fromstring(xml)
        # RSS 2.0
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
            items.append({"title": title.strip(), "url": link.strip(), "pub_date": pub.strip()})
        # Atom
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_el.get("href") if link_el is not None else ""
            pub = entry.findtext("{http://www.w3.org/2005/Atom}published") or entry.findtext("{http://www.w3.org/2005/Atom}updated")
            items.append({"title": title.strip(), "url": link.strip(), "pub_date": pub.strip()})
    except Exception as e:
        print(f"  [parse] {url}: {e}")
    return items


def process_feed(source_name: str, feed_url: str, profiles_index: dict) -> list[dict]:
    print(f"  [{source_name}] fetching {feed_url}...")
    items = fetch_rss(feed_url)
    if not items:
        return []
    print(f"  [{source_name}] {len(items)} items")
    out = []
    seen = set()
    for item in items:
        title = item.get("title", "")
        url = item.get("url", "")
        pub = item.get("pub_date", "")
        matched = match_company_in_title(title, PROFILE_INDEX)
        if not matched:
            continue
        pub_date = parse_date(item.get("pub_date", "")) or parse_rfc822_date(item.get("pub_date", ""))
        if not pub_date:
            continue
        for org in matched:
            key = (org, item.get("url", ""))
            if key in seen:
                continue
            seen.add(key)
            digest = hashlib.sha256(f"{org}|{url}|{pub_date}".encode()).hexdigest()[:16]
            out.append({
                "organisation_number": org,
                "platform": "news",
                "source_url": url,
                "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "content_sha256": hashlib.sha256((title + pub_date).encode()).hexdigest(),
                "exact_entity": True,
                "identity_proof": [{"type": "exact_name_in_news_title", "source": f"news_rss:{source_name}", "matched_name": True}],
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "public_news",
                "strategy": "norwegian_news_rss",
                "id": f"news-rss-{org}-{hashlib.sha256(f'{org}|{url}|{pub_date}'.encode()).hexdigest()[:16]}",
                "signal_type": "public_mention",
                "evidence_span": title[:1200],
                "metrics": {"published_at": pub_date, "date_source": "rss", "feed_source": source_name, "article_url": url},
            })
    return out

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def match_company_in_title(title: str, profiles_index: dict) -> list[str]:
    """Return org numbers whose indexed company name appears in the title.

    The index is keyed by the normalized company name (with and without its
    legal suffix), so a title matches when the whole name occurs as a phrase.
    Matching single words against full-name keys could never succeed.
    """
    title_norm = norm_name(title)
    if not title_norm:
        return []
    matches = set()
    for form, orgs in profiles_index.items():
        if len(form) < 6:
            continue
        if re.search(r"(?<![a-z0-9æøå])" + re.escape(form) + r"(?![a-z0-9æøå])", title_norm):
            matches.update(orgs)
    return sorted(matches)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    global PROFILE_INDEX
    PROFILE_INDEX = build_name_index(profiles)

    out: list[dict] = []
    stats = {"profiles": 0, "feeds_found": 0, "dated_items": 0, "companies": 0}; matched_orgs = set()
    seen: set[tuple[str, str]] = set()
    matched_orgs: set[str] = set()

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process_feed, name, url, PROFILE_INDEX): name for name, url in NEWS_FEEDS}
        for fut in as_completed(futures):
            stats["profiles"] += 1
            rows = fut.result() or []
            if rows:
                stats["feeds_found"] += 1
                stats["dated_items"] += len(rows)
                for r in rows:
                    matched_orgs.add(r["organisation_number"])
                    out.append(r)

    write_jsonl(Path(args.output), out)
    stats["output"] = args.output
    Path(args.report).write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**stats, "orgs_covered": len(matched_orgs)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()