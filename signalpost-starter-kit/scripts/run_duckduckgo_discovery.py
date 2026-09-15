#!/usr/bin/env python3
"""Free, API-key-free company-site discovery via DuckDuckGo HTML search.

Replaces Firecrawl Search for candidate discovery. Search output is transient
and never persisted as evidence; only an independently crawled, identity-gated
exact-entity page may be promoted into canonical website evidence. Blocks the
same directory/aggregator/social hosts as the Firecrawl connector and applies
the identical deterministic candidate gate (`choose_search_candidate`).

Resumable: rows already present in the output file are skipped, so a failed or
rate-limited run can be re-invoked with the same output path to continue.
"""

from __future__ import annotations

import argparse
import hashlib
import html as pyhtml
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.discovery import build_company_search_query, choose_search_candidate  # noqa: E402
from norway_company_agent.identity import apply_website_identity_gate  # noqa: E402
from norway_company_agent.website import fetch_website  # noqa: E402

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (compatible; builderr-signalpost-poc/0.1; +https://builderr.ai)"
BLOCKED_FRAGMENTS = ("/l/?uddg=", "duckduckgo.com", "htmlduckduckgo")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evidence(field: str, status: str, note: str, source_url: str, *, value: dict | None = None) -> dict:
    now = utc_now()
    return {
        "field": field,
        "status": status,
        "note": note,
        "source_class": "web_discovery",
        "source_type": "transient_duckduckgo_html_search",
        "source_url": source_url,
        "source_row_key": f"{field}:{status}:{now}",
        "content_sha256": None,
        "effective_at": now,
        "as_of": now,
        "retrieved_at": now,
        "value": value or {},
    }


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def duckduckgo_search(
    profile: dict,
    *,
    timeout: float,
    count: int,
    max_retries: int = 3,
) -> tuple[list[dict], dict]:
    query = build_company_search_query(profile)
    params = urllib.parse.urlencode({"q": query, "kp": "-2", "kl": "no-no"})
    url = f"{DDG_ENDPOINT}?{params}"
    query_sha = hashlib.sha256(url.encode("utf-8")).hexdigest()
    last_error: dict = {}
    for attempt in range(max_retries):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "nb-NO,no;q=0.9,nn;q=0.8,en;q=0.7",
            },
            method="GET",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            html = raw.decode("utf-8", errors="replace")
            results = parse_duckduckgo_html(html, query=query, limit=count)
            return results, {
                "status": response.status,
                "latency_ms": elapsed_ms,
                "bytes": len(raw),
                "query_sha256": query_sha,
                "attempt": attempt + 1,
            }
        except urllib.error.HTTPError as exc:
            status = getattr(exc, "code", 0)
            raw_exc = getattr(exc, "read", lambda: b"")()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            last_error = {
                "status": status,
                "latency_ms": elapsed_ms,
                "bytes": len(raw_exc),
                "query_sha256": query_sha,
                "error": f"HTTPError:{status}",
                "attempt": attempt + 1,
            }
            retry_after = min(60.0, 2 ** attempt * 2.0)
            time.sleep(retry_after)
        except Exception as exc:  # URLError, timeout, socket
            elapsed_ms = int((time.monotonic() - started) * 1000)
            last_error = {
                "status": 0,
                "latency_ms": elapsed_ms,
                "bytes": 0,
                "query_sha256": query_sha,
                "error": f"{type(exc).__name__}: {exc}",
                "attempt": attempt + 1,
            }
            time.sleep(2 ** attempt)
    results: list[dict] = []
    return results, {**last_error, "error": last_error.get("error", "ProviderError"), "result": "retries_exhausted"}


def _unblock(url: str) -> str:
    match = re.search(r"[?&]uddg=([^&]+)", url)
    if match:
        return urllib.parse.unquote(match.group(1))
    return url


def parse_duckduckgo_html(html: str, *, query: str, limit: int = 8) -> list[dict]:
    results: list[dict] = []
    for rank, match in enumerate(re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S), start=1):
        raw_href, title_html = match.group(1), match.group(2)
        target = _unblock(pyhtml.unescape(raw_href))
        if not target.startswith("http") or any(fragment in target for fragment in BLOCKED_FRAGMENTS):
            continue
        title = re.sub(r"<[^>]+>", "", title_html)
        title = pyhtml.unescape(re.sub(r"\s+", " ", title)).strip()
        if len(results) >= limit:
            break
        snippet_match = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html[html.find(title_html):], re.S)
        snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)) if snippet_match else ""
        snippet = pyhtml.unescape(re.sub(r"\s+", " ", snippet)).strip()
        results.append({
            "url": target,
            "title": title,
            "snippet": snippet,
            "rank": rank,
            "provider": "duckduckgo_html_search",
            "query": query,
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Free DuckDuckGo company-site discovery with independent identity-gated crawl.")
    parser.add_argument("--input", required=True, help="Profiles JSONL (must include name + organisation_number)")
    parser.add_argument("--output", required=True, help="Resumable discovery results JSONL")
    parser.add_argument("--report", required=True)
    parser.add_argument("--limit", type=int, default=0, help="Optional row cap (default: all)")
    parser.add_argument("--count", type=int, default=8, help="Search results per query")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--min-interval", type=float, default=3.0, help="Politeness delay between queries")
    parser.add_argument("--promote-verified", action="store_true", help="Copy exact-entity discovered sites into canonical website evidence")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows = read_jsonl(input_path)
    if args.limit:
        all_rows = all_rows[: args.limit]
    existing = set()
    if output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing.add(str(json.loads(line)["organisation_number"]))

    counts = {
        "provider_requests": 0,
        "provider_errors": 0,
        "abstained_before_crawl": 0,
        "independent_crawls": 0,
        "verified_sites": 0,
        "promoted_sites": 0,
        "resumed_skipped": 0,
        "quarantined_sites": 0,
    }
    provider_latencies: list[int] = []

    for index, row in enumerate(all_rows, start=1):
        org = str(row["organisation_number"])
        if org in existing:
            counts["resumed_skipped"] += 1
            continue
        results, operation = duckduckgo_search(row, timeout=args.timeout, count=args.count)
        counts["provider_requests"] += 1
        provider_latencies.append(operation.get("latency_ms", 0))
        if operation.get("error"):
            counts["provider_errors"] += 1
        decision = choose_search_candidate(row, results)
        selected = decision.get("selected")
        discovery_summary = {
            "provider": "duckduckgo_html_search",
            "query": build_company_search_query(row),
            "query_sha256": operation["query_sha256"],
            "candidate_count": len(results),
            "selected_for_independent_crawl": bool(selected),
            "provider_status": operation["status"],
            "retention_policy": "Search titles, snippets, ranks and query text are not persisted; only independent crawl evidence may publish.",
        }
        if not selected:
            counts["abstained_before_crawl"] += 1
            row.setdefault("evidence", {})["website_discovery"] = evidence(
                "website_discovery",
                "not_found",
                "No result passed the deterministic crawl-candidate gate; search output was discarded.",
                DDG_ENDPOINT,
                value=discovery_summary,
            )
            _append_jsonl(output_path, row)
            existing.add(org)
            time.sleep(args.min_interval)
            continue

        website, web_ops = fetch_website(selected["url"], timeout=args.timeout)
        gated = apply_website_identity_gate(row, website)
        website = gated["website"]
        assessment = gated["assessment"] or {}
        publishable = bool(assessment.get("publishable"))
        value = website.get("value") or {}
        website["source_type"] = "search_discovered_company_website"
        website["value"] = value
        row.setdefault("evidence", {})["website_discovery"] = evidence(
            "website_discovery",
            "available" if publishable else "not_found",
            "Search output was transient. Publication depends only on independently fetched exact-entity page evidence.",
            DDG_ENDPOINT,
            value={**discovery_summary, "independent_page_url": website.get("source_url") if publishable else None},
        )
        row["evidence"]["website_discovered"] = website
        counts["independent_crawls"] += 1
        if publishable and website.get("status") == "available":
            counts["verified_sites"] += 1
            if args.promote_verified:
                row["evidence"]["website"] = website
                counts["promoted_sites"] += 1
        else:
            counts["quarantined_sites"] += 1
        _append_jsonl(output_path, row)
        existing.add(org)
        time.sleep(args.min_interval)

    report = {
        "generated_at": utc_now(),
        "provider": "DuckDuckGo HTML search (free, no API key)",
        "provider_endpoint": DDG_ENDPOINT,
        "input_profiles": len(all_rows),
        "counts": counts,
        "provider_latency_ms": {
            "p50": round(sorted(provider_latencies)[len(provider_latencies) // 2]) if provider_latencies else None,
            "p95": round(sorted(provider_latencies)[int(len(provider_latencies) * 0.95) - 1]) if provider_latencies else None,
        },
        "qualification": "candidates gated deterministically; publication requires exact-entity identity on an independently crawled page",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "notes": ""}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()