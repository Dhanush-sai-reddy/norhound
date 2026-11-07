#!/usr/bin/env python3
"""Brave Search discovery for missing-website companies.

https://api.search.brave.com/res/v1/web/search

Keyless-ish: needs BRAVE_SEARCH_API_KEY env var. Searches for the company
name + Norway, then independently crawls candidate URLs and applies the
identity gate. Only exact-entity sites are published.

Adapted from DG10911's run_brave_discovery.py (competitor repo).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.evidence import utc_now  # noqa: E402
from norway_company_agent.identity import apply_website_identity_gate  # noqa: E402
from norway_company_agent.website import fetch_website  # noqa: E402

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def build_query(name: str, orgnr: str) -> str:
    q = f'"{name}" {orgnr} Norway company website'
    return q


def brave_search(query: str, api_key: str, *, timeout: float, count: int) -> tuple[list[dict], dict]:
    url = BRAVE_ENDPOINT + "?" + urllib.parse.urlencode({
        "q": query,
        "count": count,
        "country": "no",
        "search_lang": "nb",
        "safesearch": "moderate",
        "spellcheck": "0",
    })
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "User-Agent": "NorHound/1.0",
        "X-Subscription-Token": api_key,
    })
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        payload = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return [], {"status": getattr(exc, "code", 0), "latency_ms": int((time.monotonic() - started) * 1000), "bytes": 0, "error": type(exc).__name__}

    results = []
    web_results = payload.get("web", {}) if isinstance(payload, dict) else {}
    for item in web_results.get("results", []) if isinstance(web_results, dict) else []:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link")
        title = item.get("title") or ""
        desc = item.get("description") or item.get("snippet") or ""
        if url:
            results.append({"url": url, "title": title, "description": desc})
    return results, {"status": 200, "latency_ms": elapsed_ms, "bytes": len(raw), "candidate_count": len(results)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Brave Search discovery for missing-website companies.")
    parser.add_argument("--profiles", required=True, help="Frozen batch profiles JSONL")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--limit", type=int, default=50, help="Max missing-website profiles to query")
    parser.add_argument("--count", type=int, default=10, help="Search results per query")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--api-key-env", default="BRAVE_SEARCH_API_KEY")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        print(f"Missing {args.api_key_env} — Brave discovery abstains.", file=sys.stderr)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text("", encoding="utf-8")
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps({"connector": "brave_discovery_v1", "abstained": True, "reason": "missing API key"}, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    missing = [p for p in profiles if not p.get("website")]
    if not missing:
        Path(args.output).write_text("", encoding="utf-8")
        Path(args.report).write_text(json.dumps({"connector": "brave_discovery_v1", "missing_website_profiles": 0}, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    observations = []
    queried = 0
    verified = 0
    abstained = 0

    for p in missing:
        if queried >= args.limit:
            break
        org = str(p["organisation_number"])
        name = p.get("name") or org
        query = build_query(name, org)
        results, op = brave_search(query, api_key, timeout=args.timeout, count=args.count)
        queried += 1

        if op.get("error"):
            abstained += 1
            time.sleep(0.5)
            continue

        selected = None
        for r in results:
            url = r.get("url", "")
            if any(d in url for d in ("facebook.com", "linkedin.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "proff.no", "gulesider.no", "kart.sit.no", "1881.no")):
                continue
            selected = r
            break

        if not selected:
            abstained += 1
            time.sleep(0.5)
            continue

        website, web_ops = fetch_website(selected["url"], timeout=args.timeout)
        gated = apply_website_identity_gate(p, website)
        website = gated["website"]
        assessment = gated["assessment"]
        value = website.get("value") or {}

        if assessment.get("publishable") and website.get("status") == "available":
            digest = website.get("content_sha256") or ""
            pages = value.get("pages") or []
            span = ""
            if pages:
                span = pages[0].get("main_text_excerpt") or pages[0].get("title") or ""
                span = str(span)[:500]
            obs = {
                "id": "brave-discovery-" + hashlib.sha256(f"{org}|{selected['url']}".encode()).hexdigest()[:24],
                "organisation_number": org,
                "platform": "brave_search",
                "signal_type": "profile_handle",
                "source_url": selected["url"],
                "retrieved_at": website.get("retrieved_at") or utc_now(),
                "content_sha256": digest,
                "exact_entity": True,
                "identity_proof": [{
                    "type": "website_identity_gate_exact",
                    "source": "brave_search_api",
                    "source_class": "search_discovered_company_website",
                    "matched_organisation_number": org,
                    "explanation": "Brave Search candidate crawled independently and passed exact-entity identity gate.",
                }],
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "search_discovered_company_website",
                "evidence_span": span,
                "metrics": {"discovered_url": selected["url"], "candidate_count": op.get("candidate_count", 0)},
                "strategy": "brave_discovery",
            }
            observations.append(obs)
            verified += 1
        else:
            abstained += 1
        time.sleep(0.5)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations), encoding="utf-8"
    )
    report = {
        "connector": "brave_discovery_v1",
        "missing_website_profiles": len(missing),
        "queried": queried,
        "verified_sites": verified,
        "abstained": abstained,
        "observations": len(observations),
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
