#!/usr/bin/env python3
"""Sitemap URL+lastmod as dated official-site content observations.

A gated company website's sitemap lists the site's own pages with their last
modification dates. Each entry fetched from the verified company domain is
exact-entity by construction; the lastmod gives a dated signal of company
online activity. Only dated pages are emitted, newest first, capped to keep
the claim per-page and bounded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import publishable_observation  # noqa: E402

SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")
HTTP_TIMEOUT = 8
MAX_TEXT = 3000
MAX_SITEMAP_BYTES = 500000
MAX_CHILD_SITEMAPS = 5


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(sanitize_line_separators(json.dumps(row, ensure_ascii=False, separators=(",", ":"))) + "\n")
    temporary.replace(path)


def _fetch_and_parse_sitemaps(body: str) -> dict[str, dict[str, str | None]]:
    """Walk one sitemap body; follow up to MAX_CHILD_SITEMAPS sitemap-index entries."""
    pages: dict[str, dict[str, str | None]] = {}
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return pages
    if root.tag.endswith("sitemapindex"):
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        count = 0
        for sitemap in root.findall("s:sitemap", ns):
            if count >= MAX_CHILD_SITEMAPS:
                break
            loc = sitemap.findtext("s:loc", namespaces=ns)
            if not loc:
                continue
            count += 1
            try:
                request = urllib.request.Request(loc, headers={"User-Agent": "NorHound/1.0 (signalpost research)", "Accept": "application/xml"})
                with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                    child = response.read(MAX_SITEMAP_BYTES).decode("utf-8", "replace")
            except Exception:
                continue
            child_pages = parse_sitemap(child)
            pages.update(child_pages)
        return pages
    return parse_sitemap(body)


def parse_sitemap(xml_text: str) -> dict[str, dict[str, str | None]]:
    """Return {page_url: {"lastmod": "YYYY-MM-DD" or None}} from a sitemap body."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return {}
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    pages: dict[str, dict[str, str | None]] = {}
    for url in root.findall(".//s:url", ns):
        loc = url.findtext("s:loc", default=None, namespaces=ns)
        if not loc:
            continue
        lastmod = url.findtext("s:lastmod", default=None, namespaces=ns)
        date = (lastmod or "")[:10] if lastmod else None
        if isinstance(date, str) and len(date) == 10 and date.count("-") == 2:
            pages[loc.strip()] = {"lastmod": date}
        else:
            pages[loc.strip()] = {"lastmod": None}
    return pages


def select_pages(pages: dict[str, dict[str, str | None]], *, limit: int) -> list[tuple[str, dict[str, str | None]]]:
    dated = [(loc, meta) for loc, meta in pages.items() if meta.get("lastmod")]
    dated.sort(key=lambda item: item[1]["lastmod"] or "", reverse=True)
    return dated[:limit]


def host_variants(final_url: str) -> list[str]:
    """Root URLs to probe for a sitemap, prefer actual host then the www/non-www variant."""
    base = final_url.rstrip("/")
    roots = [base]
    if base.startswith("https://www."):
        roots.append("https://" + base[len("https://www."):])
    elif base.startswith("http://"):
        roots.append(base.replace("http://", "http://www.", 1))
    elif base.startswith("https://"):
        roots.append(base.replace("https://", "https://www.", 1))
    seen, ordered = set(), []
    for root in roots:
        if root not in seen:
            seen.add(root)
            ordered.append(root)
    return ordered


def _fetch_sitemap(root: str) -> str | None:
    for path in SITEMAP_PATHS:
        url = root + path
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NorHound/1.0 (signalpost research)", "Accept": "application/xml"})
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                body = response.read(500000).decode("utf-8", "replace")
            if "<url" in body or "<loc>" in body:
                return body
        except Exception:
            continue
    return None


def observations_for_profile(profile: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    org = str(profile.get("organisation_number") or "")
    if not org.isdigit():
        return []
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    if website.get("status") != "available" or not identity.get("publishable"):
        return []
    final_url = str(value.get("final_url") or value.get("source_url") or "").strip()
    if not final_url.startswith(("http://", "https://")):
        return []
    body = None
    variants = host_variants(final_url)
    for root in variants[:1]:
        body = _fetch_sitemap(root)
    if body is None and len(variants) > 1:
        body = _fetch_sitemap(variants[1])
    if body is None:
        return []
    pages = _fetch_and_parse_sitemaps(body)
    selected = select_pages(pages, limit=limit)
    observations = []
    for loc, meta in selected:
        observations.append({
            "id": "sitemap-page-" + hashlib.sha256(f"{org}|{loc}|{meta['lastmod']}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "company_site",
            "signal_type": "sitemap_page",
            "source_url": final_url,
            "retrieved_at": website.get("retrieved_at"),
            "content_sha256": value.get("content_sha256") or website.get("content_sha256") or "",
            "observed_at": meta["lastmod"],
            "exact_entity": True,
            "identity_proof": [{"type": "website_identity_gate", "score": identity.get("score"), "method": identity.get("method")}],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_site",
            "evidence_span": f"Sitemap page {loc} last modified {meta['lastmod']}"[:MAX_TEXT],
            "metrics": {"page_url": loc, "lastmod": meta["lastmod"], "interpretation": "Dated official-site page from the site's own sitemap."},
            "strategy": "sitemap_lastmod",
        })
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Sitemap URL+lastmod connector.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--per-org-limit", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    profiles = read_jsonl(Path(args.profiles))
    if args.limit:
        profiles = profiles[: args.limit]
    observations: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(observations_for_profile, profile, limit=args.per_org_limit): profile["organisation_number"] for profile in profiles}
        for index, future in enumerate(as_completed(futures), 1):
            observations.extend(future.result())
    publishable = [o for o in observations if publishable_observation(o)]
    write_jsonl(Path(args.output), publishable)
    report = {
        "connector": "sitemap_lastmod_v1",
        "profiles": len(profiles),
        "publishable_observations": len(publishable),
        "claim_boundary": "Only dated pages from the verified company site's own sitemap; newest first, capped per org.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()