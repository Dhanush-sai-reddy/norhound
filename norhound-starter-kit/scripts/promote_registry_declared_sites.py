#!/usr/bin/env python3
"""Promote website identity for sites whose domain the entity itself declared.

The name-token identity gate compares the legal name in the register with the
words on the homepage.  It fails on every brand site (`hlfbriskeby.no` for
"Briskeby videregående skole", a group domain, a shortened trading name) and
those sites then lose *all* website-derived facts — dated news, careers pages,
social handles, descriptions — even though the pages are already captured and
hashed in the frozen profile.

The register offers a stronger, independent basis: `hjemmeside` is submitted by
the entity in its own official filing.  When the crawled page sits on exactly
that domain *and* the register shows no other organisation number claiming it,
the site belongs to this organisation number as a matter of official record.

This is a pure profile pre-pass: it only widens `identity_assessment`, keeps the
previous assessment for audit, and touches no captured bytes or digests.
Organisations that do not satisfy every condition are passed through unchanged.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_registry_domain_index import register_domain  # noqa: E402


def load_index(path: Path) -> dict[str, str]:
    """domain -> sole declaring organisation number."""
    if not path.exists():
        return {}
    opener = gzip.open if path.suffix == ".gz" else open
    index: dict[str, str] = {}
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            domain = str(row.get("domain") or "")
            number = str(row.get("organisation_number") or "")
            if domain and len(number) == 9:
                index[domain] = number
    return index


def site_domain(website: dict) -> str:
    value = website.get("value") or {}
    for candidate in (value.get("final_url"), website.get("source_url"), value.get("requested_url")):
        domain = register_domain(str(candidate or ""))
        if domain:
            return domain
    return ""


def corroborated_by_page(value: dict, assessment: dict, organisation_number: str) -> bool:
    """Require the page itself to mention the company before a register filing promotes it.

    A declared domain cannot distinguish the company's own site from a hosting
    placeholder, an agency's page, or a domain that expired into other hands;
    several batch companies still file such URLs as hjemmeside.
    """
    if assessment.get("matched_tokens"):
        return True
    grouped = f"{organisation_number[:3]} {organisation_number[3:6]} {organisation_number[6:]}"
    text = " ".join(str(value.get(key) or "") for key in
                    ("title", "description", "main_text_excerpt", "structured_organisations"))
    return organisation_number in text or grouped in text


def promote(profile: dict, index: dict[str, str], as_of: str) -> str:
    """Apply the registry-domain proof in place; returns the outcome for the report."""
    evidence = profile.get("evidence") or {}
    website = evidence.get("website") or {}
    if website.get("status") != "available":
        return ""
    registry = ((evidence.get("registry") or {}).get("value") or {})
    declared = register_domain(str(registry.get("hjemmeside") or ""))
    if not declared:
        return ""
    crawled = site_domain(website)
    if not crawled or crawled != declared:
        return ""
    if index.get(declared) != str(profile.get("organisation_number")):
        return ""
    value = website.get("value") or {}
    assessment = dict(value.get("identity_assessment") or {})
    if assessment.get("registry_declared_domain") and assessment.get("publishable"):
        return "already_promoted"
    if not corroborated_by_page(value, assessment, str(profile.get("organisation_number"))):
        return "uncorroborated"
    prior = dict(assessment)
    assessment.update({
        "status": "exact",
        "label": assessment.get("label") or "exact",
        "score": max(float(assessment.get("score") or 0.0), 0.95),
        "publishable": True,
        "registry_declared_domain": True,
        "promotion_proof": {
            "type": "registry_declared_domain_unique",
            "domain": declared,
            "register_field": "hjemmeside",
            "sole_declarer_in_register": True,
            "index_as_of": as_of,
            "basis": "the organisation number filed this exact domain in the official register, "
                     "no other organisation number declares it, and the page mentions the company",
        },
        "prior_assessment": {key: prior.get(key) for key in ("status", "score", "publishable", "label")},
    })
    value["identity_assessment"] = assessment
    website["value"] = value
    evidence["website"] = website
    profile["evidence"] = evidence
    return "promoted"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profiles", required=True, help="Frozen batch profiles JSONL")
    parser.add_argument("--output", required=True, help="Promoted profiles JSONL")
    parser.add_argument("--report", required=True, help="Summary JSON")
    parser.add_argument("--index", default="data/registry-domain-unique.jsonl.gz",
                        help="Sole-declarer domain index (build_registry_domain_index.py)")
    args = parser.parse_args()

    source = Path(args.profiles)
    profiles = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    index = load_index(Path(args.index))
    if not index:
        print(f"warning: domain index empty or missing at {args.index}; no profiles promoted", file=sys.stderr)

    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = collections.Counter(profiles=len(profiles), promoted=0, already_promoted=0, uncorroborated=0,
                                index_domains=len(index))
    for profile in profiles:
        stats[promote(profile, index, as_of) or "not_matched"] += 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                                 for row in profiles), encoding="utf-8")
    temporary.replace(output)

    summary = {**stats, "output": str(output)}
    Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
