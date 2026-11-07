#!/usr/bin/env python3
"""Publish website observations for companies whose domain BRREG declares.

BRREG — the official Norwegian company registry — states each company's website
domain. When the crawled site lives on exactly that domain *and* the stored page
text corroborates the company (its organisation number, or a legal-name token),
the identity is official-grade: the registry resolves the domain to the legal
entity and the page confirms it.

The observation carries that proof explicitly:

    {"type": "registry_declared_website_domain_match",
     "value": "<domain>",
     "matched_organisation_number": "<org>",
     "source": "brreg",
     "source_url": "<registry record URL>",
     "retrieved_at": "<registry retrieval time>"}

The verifier (`scripts/verify_and_label_observations.py`) re-derives both
conditions from the frozen profile — the registry field and the stored page
text — and never trusts what the observation says about itself.

Usage:
    uv run python scripts/extract_registry_proved_site_observations.py \
        --profiles out/frozen/web1000-profiles.jsonl \
        --output out/registry-site.external.jsonl \
        --report out/registry-site.report.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

PROOF_TYPE = "registry_declared_website_domain_match"

# Legal-form tokens are dropped before name-token comparison: "AS", "ASA",
# "ENK", ... carry no identity signal on a web page.
LEGAL_FORM_TOKENS = {
    "as", "asa", "a/s", "ans", "ba", "da", "enk", "kf", "sa", "aps", "ab", "oy", "oyj",
    "gmbh", "ag", "bv", "nv", "sarl", "spa", "srl", "co", "corp", "plc", "lp", "llp",
    "k/s", "i/s", "sp", "ug", "reg", "limited", "ltd", "inc", "llc", "p/s",
}

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def normalise_host(value: str) -> str:
    """Host of a URL or bare domain, lowercased and without a leading www."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        host = (urlparse(text).hostname or "").strip()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _fold(text: str) -> str:
    """Lowercase and transliterate the Norwegian letters OCR/pages may mangle."""
    return (text or "").lower().replace("ø", "o").replace("å", "a").replace("æ", "ae")


def legal_name_tokens(name: str) -> list[str]:
    """Distinctive tokens of the legal name (legal forms and short tokens dropped)."""
    tokens = [token for token in re.split(r"[^0-9a-z]+", _fold(name)) if token]
    return [token for token in tokens if token not in LEGAL_FORM_TOKENS and len(token) >= 4]


def site_text(value: dict) -> str:
    """All stored text of the crawled page, folded for comparison."""
    parts = [
        str(value.get("title") or ""),
        str(value.get("description") or ""),
        str(value.get("main_text_excerpt") or ""),
        json.dumps(value.get("structured_organisations") or [], ensure_ascii=False),
    ]
    return _fold(" ".join(parts))


def corroborates_identity(profile: dict, value: dict) -> bool:
    """True when the stored page text names the organisation number or a name token."""
    org = str(profile.get("organisation_number") or "")
    text = site_text(value)
    if org and org in re.sub(r"\D", "", text):
        return True
    return any(token in text for token in legal_name_tokens(str(profile.get("name") or "")))


def _website_evidence(profile: dict) -> dict:
    return ((profile.get("evidence") or {}).get("website") or {})


def _digest(website: dict, value: dict) -> str:
    for candidate in (
        value.get("content_sha256"),
        website.get("content_sha256"),
        *[(page or {}).get("content_sha256") for page in (value.get("pages") or [])],
    ):
        text = str(candidate or "")
        if HEX64_RE.match(text.lower()):
            return text.lower()
    return ""


def extract_observation(profile: dict) -> tuple[dict | None, dict]:
    """Build one website observation from frozen evidence, or explain why not."""
    org = str(profile.get("organisation_number") or "")
    status = {"organisation_number": org, "status": "skipped"}

    registry_host = normalise_host(profile.get("website") or "")
    if not registry_host:
        return None, {**status, "reason": "no_registry_website"}

    website = _website_evidence(profile)
    if website.get("status") != "available":
        return None, {**status, "reason": "website_not_available"}
    value = website.get("value") or {}

    site_host = normalise_host(
        value.get("registered_domain") or value.get("final_url") or website.get("source_url") or ""
    )
    if not site_host or site_host != registry_host:
        return None, {**status, "reason": "registry_domain_mismatch", "registry_host": registry_host, "site_host": site_host}

    digest = _digest(website, value)
    if not digest:
        return None, {**status, "reason": "no_digest"}

    if not corroborates_identity(profile, value):
        return None, {**status, "reason": "identity_not_corroborated"}

    title = str(value.get("title") or "").strip()
    description = str(value.get("description") or "").strip()
    if not title and not description:
        # Some server-rendered pages carry no <title> and no meta description.
        # The page's own extracted main text is the company's own words, and it
        # comes from the bytes already captured and hashed for this page.
        description = str(value.get("main_text_excerpt") or "").strip()
    if not title and not description:
        return None, {**status, "reason": "no_extractable_text"}

    source_url = str(value.get("final_url") or website.get("source_url") or "")
    retrieved_at = str(website.get("retrieved_at") or "")
    registry = (profile.get("evidence") or {}).get("registry") or {}
    proof = {
        "type": PROOF_TYPE,
        "value": registry_host,
        "matched_organisation_number": org,
        "source": "brreg",
        "source_url": str(registry.get("source_url") or ""),
        "retrieved_at": str(registry.get("retrieved_at") or ""),
        "explanation": (
            f"BRREG declares {registry_host} as the website of organisation {org}; the crawled page "
            "on that host corroborates the organisation number or the legal name."
        ),
    }
    observation = {
        "id": f"registry-site-{org}-{digest[:16]}",
        "organisation_number": org,
        "platform": "company_site",
        "signal_type": "website_description",
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "exact_entity": True,
        "identity_proof": [proof],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_site",
        "evidence_span": " — ".join(part for part in (title, description) if part)[:400],
        "metrics": {"title": title, "description": description, "registry_domain": registry_host},
        "strategy": "registry_declared_website_description",
    }
    return observation, {**status, "status": "accepted", "registry_host": registry_host}


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit website observations proved by the BRREG-declared domain.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    profiles = [
        json.loads(line)
        for line in Path(args.profiles).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    observations: list[dict] = []
    statuses: list[dict] = []
    for profile in profiles:
        observation, status = extract_observation(profile)
        if observation is not None:
            observations.append(observation)
        statuses.append(status)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations), encoding="utf-8"
    )
    reasons: dict[str, int] = {}
    for status in statuses:
        if status.get("status") != "accepted":
            reasons[status.get("reason", "unknown")] = reasons.get(status.get("reason", "unknown"), 0) + 1
    report = {
        "connector": "registry_declared_website_observations_v1",
        "companies": len(profiles),
        "observations": len(observations),
        "accepted": sum(1 for status in statuses if status.get("status") == "accepted"),
        "skipped_reasons": reasons,
        "claim_boundary": (
            "BRREG-declared website domain plus stored page corroboration; the observation states the "
            "registry proof and the verifier re-derives it from the frozen profile."
        ),
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
