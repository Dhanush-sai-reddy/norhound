#!/usr/bin/env python3
"""Publish company-owned site identity as exact-entity observations.

A gated company website's own <title>/<meta description> and its JSON-LD
Organization name are the company's own words about itself. Emitted as
website_description and public_brand observations. Person names and street
addresses are deliberately NOT parsed from free text: without structured
records they carry namesake risk, so site_leader/site_location stay
unpublished until a structured source exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _base(profile: dict[str, Any], org: str, website: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    identity = value.get("identity_assessment") or {}
    return {
        "organisation_number": org,
        "platform": "company_site",
        "source_url": website.get("source_url") or value.get("final_url") or "",
        "retrieved_at": website.get("retrieved_at"),
        "content_sha256": value.get("content_sha256") or website.get("content_sha256") or "",
        "exact_entity": True,
        "identity_proof": [{"type": "website_identity_gate", "score": identity.get("score"), "method": identity.get("method")}],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_site",
        "strategy": "company_site_identity",
    }


def observations_for_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    org = str(profile.get("organisation_number") or "")
    if not org.isdigit():
        return []
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    if website.get("status") != "available" or not identity.get("publishable"):
        return []
    base = _base(profile, org, website, value)
    if not base["source_url"].startswith(("http://", "https://")) or len(str(base["content_sha256"])) != 64:
        return []
    observations = []
    title = str(value.get("title") or "").strip()
    description = str(value.get("description") or "").strip()
    text = " — ".join(part for part in (title, description) if part)
    if text:
        observations.append({
            **base,
            "id": "site-description-" + hashlib.sha256(f"{org}|{text}".encode()).hexdigest()[:24],
            "signal_type": "website_description",
            "evidence_span": text[:1200],
            "metrics": {"interpretation": "Company-owned description; the company's own words."},
        })
    for entry in value.get("structured_organisations") or []:
        if not isinstance(entry, dict):
            continue
        brand = str(entry.get("name") or "").strip()
        if not brand:
            continue
        observations.append({
            **base,
            "id": "site-brand-" + hashlib.sha256(f"{org}|{brand}".encode()).hexdigest()[:24],
            "signal_type": "public_brand",
            "evidence_span": brand[:300],
            "metrics": {"declared_url": entry.get("url"), "interpretation": "Brand name from the site's own JSON-LD."},
        })
        break
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit company-owned site description/brand as observations.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [item for profile in profiles for item in observations_for_profile(profile)]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "site_description_v1",
        "profiles": len(profiles),
        "observations": len(rows),
        "claim_boundary": "Company-owned title/description/JSON-LD brand only; no free-text person or address parsing.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
