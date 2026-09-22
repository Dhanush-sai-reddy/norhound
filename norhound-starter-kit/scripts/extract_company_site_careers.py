#!/usr/bin/env python3
"""Extract a hiring signal from an exact-site bounded careers page.

Same tier as extract_company_site_news.py: a careers/jobs page reachable from
the company's own identity-gated website is a company-owned source. This only
records that such a page exists (signal_type careers_page) — it never claims
individual open positions the way a jobs-board posting does.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse


CAREERS_PATH = re.compile(r"(?:^|[-/])(?:careers?|jobs?|karriere|ledige-stillinger|stillinger)(?:[-/]|$)", re.I)


def observation(profile: dict) -> dict | None:
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    if website.get("status") != "available" or not identity.get("publishable"):
        return None
    pages = [
        page for page in (value.get("pages") or [])
        if CAREERS_PATH.search(urlparse(str(page.get("url") or "")).path)
    ]
    if not pages:
        return None
    pages.sort(key=lambda page: str(page.get("url") or ""))
    page = pages[0]
    url = str(page.get("url") or "")
    digest = str(page.get("content_sha256") or "")
    if not url.startswith(("http://", "https://")) or len(digest) != 64:
        return None
    org = str(profile["organisation_number"])
    title = str(page.get("title") or "Careers page").strip()
    return {
        "id": "company-site-careers-" + hashlib.sha256(f"{org}|{url}".encode()).hexdigest()[:24],
        "organisation_number": org,
        "platform": "company_site",
        "signal_type": "careers_page",
        "source_url": url,
        "retrieved_at": website.get("retrieved_at"),
        "content_sha256": digest,
        "exact_entity": True,
        "identity_proof": [{"type": "website_identity_gate", "score": identity.get("score"), "method": identity.get("method")}],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_site",
        "evidence_span": f"Careers page on the exact company site: {title}"[:1200],
        "metrics": {"captured_careers_pages": len(pages), "interpretation": "Hiring signal (page exists); not counted as individual open positions."},
        "strategy": "company_site_activity",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract company-owned hiring signal from exact-site bounded careers pages.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [item for profile in profiles if (item := observation(profile))]
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "exact_company_site_careers_v1",
        "profiles": len(profiles),
        "companies_with_careers": len(rows),
        "observations": len(rows),
        "claim_boundary": "Page-exists hiring signal only; never individual open positions.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
