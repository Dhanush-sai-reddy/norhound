#!/usr/bin/env python3
"""Extract dated news + social handles from related_or_uncertain company sites.

For sites the website gate rated 'related_or_uncertain' (group/brand pages),
publish a fact only when the specific page carries a page-scoped strong proof
(org number in body, or exact legal name + address). Emitted rows are
exact_entity=False, source_class="related_or_uncertain". This widens
dated-news/social coverage without a wrong-company risk.
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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.website import USER_AGENT, _robots_allowed, assert_public_url, _social_links  # noqa: E402
from norway_company_agent.identity import assess_social_identity  # noqa: E402

PAGES = ("/nyheter", "/aktuelt", "/news", "/om-oss", "/kontakt", "/about")
COMPARE_RE = re.compile(r"(?<!\d)(\d{3}\s?\d{3}\s?\d{3})(?!\d)")


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
        assert_public_url(url)
    except ValueError:
        return None
    if not _robots_allowed(url, timeout):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read(max_bytes).decode("utf-8", "replace")
    except Exception:
        return None


def orgnr_on_page(html: str, org: str) -> bool:
    c = html or ""
    if org in c:
        return True
    comp = c.replace("-", "").replace(" ", "").replace("\u00a0", "").replace("\u200b", "")
    return org in comp


def exact_name_on_page(html: str, name: str, address: str | None) -> bool:
    c = re.sub(r"<[^>]+>", " ", html or "")
    c = re.sub(r"\s+", " ", c)
    name_l = " ".join(re.findall(r"[a-z0-9æøå]+", name.casefold()))
    if not name_l or name_l not in c.casefold():
        return False
    if address:
        return any(t in c.casefold() for t in re.findall(r"[a-z0-9æøå]+", address.casefold()) if len(t) >= 4)
    return False


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


def process(profile: dict, address: str | None) -> list[dict]:
    ev = (profile.get("evidence") or {}).get("website") or {}
    if ev.get("status") != "available":
        return []
    val = ev.get("value") or {}
    ident = val.get("identity_assessment") or {}
    status = str(ident.get("status") or "").lower()
    if status != "related_or_uncertain":
        return []
    site = ev.get("source_url") or val.get("final_url") or ""
    if not site:
        return []
    org = str(profile["organisation_number"])
    name = str(profile.get("name") or "")
    out = []

    pages = [site] + [urllib.parse.urljoin(site, p) for p in PAGES]
    page_html: dict[str, str] = {}
    for p in pages:
        h = fetch(p)
        if h:
            page_html[p] = h

    # Handles: link on any proven page
    for page, html in page_html.items():
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        strong = orgnr_on_page(html, org) or exact_name_on_page(html, name, address)
        base = page.rsplit("/", 1)[0] + "/"
        for link in _social_links(page, soup):
            if not isinstance(link, dict):
                continue
            plat = link.get("platform") or ""
            url = str(link.get("url") or "")
            if not url or not plat:
                continue
            a = assess_social_identity({"organisation_number": org, "name": name}, {"platform": plat, "url": url}) if strong else {"publishable": False}
            if not ((a.get("publishable") and strong)):
                continue
            digest = hashlib.sha256(f"{org}|{plat}|{url}".encode()).hexdigest()[:16]
            out.append({
                "organisation_number": org,
                "platform": plat,
                "source_url": page,
                "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "content_sha256": hashlib.sha256(f"{plat}|{url}|{org}".encode()).hexdigest(),
                "exact_entity": False,
                "identity_proof": [{"type": "related_site_page_proof", "site": site, "orgnr_on_page": strong}],
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "related_or_uncertain",
                "strategy": "related_site_social",
                "id": f"related-social-{org}-{plat}-{digest}",
                "signal_type": "profile_handle",
                "evidence_span": f"Social handle on related site page with page-level proof ({site}).",
                "metrics": {"platform": plat, "url": url},
            })

    # Dated news: first dated item per page
    from email.utils import parsedate_to_datetime as _p
    date_re = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
    for page, html in page_html.items():
        strong = orgnr_on_page(html, org) or exact_name_on_page(html, name, address)
        if not strong:
            continue
        dates = date_re.findall(html)
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else page
        if dates and title:
            d = parse_date(dates[0])
            if d:
                digest = hashlib.sha256(f"{org}|{page}|{d}".encode()).hexdigest()[:16]
                out.append({
                    "organisation_number": org,
                    "platform": "company_site",
                    "source_url": page,
                    "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "content_sha256": hashlib.sha256((title+d).encode()).hexdigest(),
                    "exact_entity": False,
                    "identity_proof": [{"type": "related_site_page_proof", "site": site, "orgnr_on_page": strong}],
                    "acquisition_mode": "permitted_public_page",
                    "rights_status": "approved",
                    "source_class": "related_or_uncertain",
                    "strategy": "related_site_news",
                    "id": f"related-news-{org}-{digest}",
                    "signal_type": "public_post",
                    "evidence_span": title[:1200],
                    "metrics": {"published_at": d, "date_source": "page_html", "body_excerpt": (re.sub(r"<[^>]+>", " ", html)[:2000] if strong else None)},
                })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    profiles = read_jsonl(Path(args.profiles))
    if args.limit:
        profiles = profiles[: args.limit]
    addresses = {str(p["organisation_number"]): str((((p.get("evidence") or {}).get("registry") or {}).get("value") or {}).get("postal_address") or ((((p.get("evidence") or {}).get("registry") or {}).get("value") or {}).get("address") or "")) for p in profiles}
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process, p, addresses.get(str(p["organisation_number"]))): p for p in profiles}
        for fut in as_completed(futures):
            out.extend(fut.result() or [])
    write_jsonl(Path(args.output), out)
    rep = {"profiles": len(profiles), "rows": len(out), "orgs": len({o["organisation_number"] for o in out}), "output": args.output}
    Path(args.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
