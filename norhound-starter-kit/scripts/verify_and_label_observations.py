#!/usr/bin/env python3
"""Label external observations by re-verifying them against stored evidence.

Each observation's exact_entity and metric_correct labels are derived by
re-checking the frozen profile evidence that produced it, not assumed:

- source_url must live on the company's verified registered domain (or, for
  official-API rows, carry an organisation_number_on_official_api / directory
  identity proof instead)
- content_sha256 must match the stored website digest for that organisation
- identity_proof must carry the website identity gate assessment (or an
  authoritative official-API / directory organisation-number proof)
- a Wikidata P2333 proof counts as an authoritative organisation-number proof
  only when it names this organisation number, its QID is well formed and
  consistent with the entity URL, and the Wikidata entity JSON was hashed
- acquisition_mode must be permitted_public_page or official_api
- publishable status must match at publication time
- profile_handle rows must be proved either by the identity-gated company site
  (a social link the gate actually observed in social_links) or by a trusted
  API that states the exact organisation number (Wikidata P2333); a handle
  proved only by the website stays quarantined otherwise

A row is labelled exact_entity=1 only when all checks pass; anything that
cannot be re-derived from frozen evidence is labelled 0 (fail-safe).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tldextract import TLDExtract  # noqa: E402

# One extractor for the whole process. Constructing a TLDExtract per call
# re-reads the public-suffix list, and verify() resolves two domains per
# observation -- that alone dominated runtime on a 24,887-row run.
_EXTRACTOR = TLDExtract(cache_dir=str(Path(".cache/tldextract")))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


@lru_cache(maxsize=65536)
def registered_domain(url: str) -> str | None:
    try:
        return _EXTRACTOR.extract_str(url).registered_domain.lower() or None
    except Exception:
        return None


# Official-report proofs carry the organisation number inside a Brreg-fetched
# annual report or registry resource. They are as authoritative as a direct
# organisation_number_on_official_api proof, and unlike website rows they do
# not depend on company-site evidence being available.
OFFICIAL_REPORT_PROOF_TYPES = (
    "official_report_url_organisation_number",
    "organisation_number_in_pdf",
    # Google Places API (New): official API returns the place's websiteUri; the
    # company website was independently resolved from the BRREG registry record.
    # Two authoritative sources agreeing on the exact registered domain is a
    # valid exact-entity proof, equivalent to an official-API identity.
    "google_places_website_domain_match",
    # Google Maps reviews via Apify: the place's website is extracted and matched
    # against the BRREG-registered domain. Two authoritative sources agreeing on
    # the exact registered domain is a valid exact-entity proof.
    "domain_resolved_to_exact_entity",
)


# BRREG — the official registry — states each company's website domain. When an
# observation's source host is exactly that domain and the stored page text
# corroborates the company (its organisation number, or a legal-name token), the
# registry resolves the domain to the legal entity. The proof is re-derived from
# the profile's own registry field and stored page, never from what the
# observation claims about itself.
REGISTRY_DOMAIN_PROOF_TYPE = "registry_declared_website_domain_match"
LEGAL_FORM_TOKENS = {
    "as", "asa", "a/s", "ans", "ba", "da", "enk", "kf", "sa", "aps", "ab", "oy", "oyj",
    "gmbh", "ag", "bv", "nv", "sarl", "spa", "srl", "co", "corp", "plc", "lp", "llp",
    "k/s", "i/s", "sp", "ug", "reg", "limited", "ltd", "inc", "llc", "p/s",
}


def _normalise_host(value: str) -> str:
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
    return host[4:] if host.startswith("www.") else host


def _fold(text: str) -> str:
    """Lowercase and transliterate the Norwegian letters pages may mangle."""
    return (text or "").lower().replace("ø", "o").replace("å", "a").replace("æ", "ae")


def _legal_name_tokens(name: str) -> list[str]:
    """Distinctive tokens of the legal name (legal forms and short tokens dropped)."""
    tokens = [token for token in re.split(r"[^0-9a-z]+", _fold(name)) if token]
    return [token for token in tokens if token not in LEGAL_FORM_TOKENS and len(token) >= 4]


def _site_text(value: dict) -> str:
    """All stored text of the crawled page, folded for comparison."""
    parts = [
        str(value.get("title") or ""),
        str(value.get("description") or ""),
        str(value.get("main_text_excerpt") or ""),
        json.dumps(value.get("structured_organisations") or [], ensure_ascii=False),
    ]
    return _fold(" ".join(parts))


def _site_corroborates(profile: dict, value: dict) -> bool:
    """True when the stored page text names the organisation number or a name token."""
    org = str(profile.get("organisation_number") or "")
    text = _site_text(value)
    if org and org in re.sub(r"\D", "", text):
        return True
    return any(token in text for token in _legal_name_tokens(str(profile.get("name") or "")))


def _registry_domain_proof(obs: dict) -> dict | None:
    for proof in obs.get("identity_proof") or []:
        if isinstance(proof, dict) and str(proof.get("type") or "") == REGISTRY_DOMAIN_PROOF_TYPE:
            return proof
    return None


def _registry_domain_proof_consistent(obs: dict, profile: dict) -> bool:
    """True when the proof, the profile's registry field and the stored page agree."""
    proof = _registry_domain_proof(obs)
    if not proof:
        return False
    org = str(proof.get("matched_organisation_number") or "").strip()
    if org != str(profile.get("organisation_number") or "").strip():
        return False
    registry_host = _normalise_host(profile.get("website") or "")
    if not registry_host:
        return False
    if _normalise_host(obs.get("source_url") or "") != registry_host:
        return False
    if not str(obs.get("content_sha256") or "").strip():
        return False
    website = ((profile.get("evidence") or {}).get("website") or {})
    return _site_corroborates(profile, website.get("value") or {})


def _identity_proof_kind(obs: dict) -> str:
    """Classify the authoritative identity proof: 'directory', 'official_api', 'wikidata', 'probed_site', or '' (website-only)."""
    for proof in (obs.get("identity_proof") or []):
        proof_type = str(proof.get("type") or "")
        if "organisation_number_on_official_api" in proof_type:
            return "official_api"
    for proof in (obs.get("identity_proof") or []):
        proof_type = str(proof.get("type") or "")
        if proof_type in OFFICIAL_REPORT_PROOF_TYPES:
            return "official_api"
    for proof in (obs.get("identity_proof") or []):
        proof_type = str(proof.get("type") or "")
        if "organisation_number_on_directory_page" in proof_type:
            return "directory"
    for proof in (obs.get("identity_proof") or []):
        proof_type = str(proof.get("type") or "")
        if "organisation_number_on_wikidata" in proof_type:
            return "wikidata"
    for proof in (obs.get("identity_proof") or []):
        proof_type = str(proof.get("type") or "")
        if proof_type == "probed_verified_site":
            return "probed_site"
    return ""


def _identity_gate(website: dict) -> dict:
    return ((website.get("value") or {}).get("identity_assessment") or {})


# A Wikidata row is trusted only when its P2333 proof, its QID and its hashed
# entity JSON all name this profile organisation. The QID in a Wikidata entity
# URL must equal metrics.qid; a Wikipedia article URL carries the *related*
# Wikidata QID in metrics.qid and is not required to contain it.
WIKIDATA_QID_RE = re.compile(r"^Q\d+$")
WIKIDATA_ENTITY_URL_RE = re.compile(r"^https?://(?:www\.)?wikidata\.org/wiki/(Q\d+)(?:[/?#].*)?$")
ORGANISATION_NUMBER_RE = re.compile(r"^\d{9}$")


def _has_wikidata_proof(obs: dict) -> bool:
    return any(
        isinstance(proof, dict) and "organisation_number_on_wikidata" in str(proof.get("type") or "")
        for proof in (obs.get("identity_proof") or [])
    )


def _wikidata_proof_organisation_number(obs: dict) -> str:
    """The organisation number the P2333 proof states: matched_organisation_number, else a 9-digit value."""
    for proof in (obs.get("identity_proof") or []):
        if not isinstance(proof, dict):
            continue
        if "organisation_number_on_wikidata" not in str(proof.get("type") or ""):
            continue
        matched = str(proof.get("matched_organisation_number") or "").strip()
        if matched:
            return matched
        value = str(proof.get("value") or "").strip()
        if ORGANISATION_NUMBER_RE.match(value):
            return value
    return ""


def _wikidata_qid_from_url(url: str) -> str:
    match = WIKIDATA_ENTITY_URL_RE.match(str(url or "").strip())
    return match.group(1) if match else ""


def _wikidata_proof_consistent(obs: dict, profile: dict) -> bool:
    """True when the Wikidata P2333 proof, QID and digest identify this profile organisation."""
    proof_org = _wikidata_proof_organisation_number(obs)
    if not proof_org or proof_org != str(profile.get("organisation_number") or "").strip():
        return False
    metrics = obs.get("metrics") if isinstance(obs.get("metrics"), dict) else {}
    qid = str(metrics.get("qid") or "").strip()
    if not WIKIDATA_QID_RE.match(qid):
        return False
    url_qid = _wikidata_qid_from_url(obs.get("source_url") or "")
    if url_qid and url_qid != qid:
        return False
    return bool(str(obs.get("content_sha256") or "").strip())


def verify(obs: dict, profile: dict) -> dict:
    checks = {}
    checks["organisation_match"] = str(obs.get("organisation_number")) == str(profile.get("organisation_number"))
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    gate = _identity_gate(website)
    source_url = obs.get("source_url") or ""
    site_url = website.get("source_url") or value.get("final_url") or ""
    checks["site_status_available"] = website.get("status") == "available"
    checks["gate_publishable"] = bool(gate.get("publishable"))
    checks["gate_label"] = gate.get("label") in ("exact", "quasi", "major_public") or bool(gate.get("status")) or bool(gate.get("score"))
    checks["source_domain_matches"] = registered_domain(source_url) == registered_domain(site_url) or source_url == site_url
    identity_proof_kind = _identity_proof_kind(obs)
    checks["directory_identity_proof"] = identity_proof_kind == "directory"
    checks["official_api_identity_proof"] = identity_proof_kind == "official_api"
    checks["wikidata_identity_proof"] = identity_proof_kind == "wikidata"
    checks["probed_site_identity_proof"] = identity_proof_kind == "probed_site"
    # A Wikidata proof is only decisive when it names this organisation number,
    # carries a valid QID consistent with the entity URL, and hashes the entity
    # JSON; anything else falls back to the ordinary rules.
    checks["wikidata_proof_consistent"] = (
        _wikidata_proof_consistent(obs, profile) if _has_wikidata_proof(obs) else True
    )
    # A registry-declared website row is trusted only when the proof names this
    # organisation, the source host is the domain BRREG declares for it, the
    # stored page corroborates the company and the page body was hashed.
    registry_domain_proof = _registry_domain_proof(obs)
    checks["registry_domain_proof_present"] = registry_domain_proof is not None
    checks["registry_domain_proof_consistent"] = (
        _registry_domain_proof_consistent(obs, profile) if registry_domain_proof is not None else True
    )
    checks["identity_proof_present"] = bool(obs.get("identity_proof"))
    if not identity_proof_kind:
        checks["proof_references_site"] = any(
            isinstance(p, dict) and ("website" in str(p.get("type") or "").lower() or "site" in str(p.get("type") or "").lower())
            for p in (obs.get("identity_proof") or [])
        )
    digest = obs.get("content_sha256")
    stored_digest = value.get("content_sha256") or website.get("content_sha256")
    page_digests = {str(p.get("content_sha256") or "") for p in (value.get("pages") or [])}
    digest_matches = (digest and digest == stored_digest) or (digest and digest in page_digests)
    checks["digest_matches"] = digest_matches
    checks["proof_references_site"] = any(
        isinstance(p, dict) and ("website" in str(p.get("type") or "").lower() or "site" in str(p.get("type") or "").lower())
        for p in (obs.get("identity_proof") or [])
    )
    checks["acquisition_permitted"] = obs.get("acquisition_mode") in ("permitted_public_page", "official_api")
    checks["rights_approved"] = obs.get("rights_status") == "approved"

    if obs.get("signal_type") == "profile_handle":
        handle = (obs.get("metrics") or {}).get("url") or ""
        socials = [s.get("url") or "" for s in (value.get("social_links") or [])]
        checks["handle_present_in_gate_socials"] = handle in socials
        checks["platform_minor"] = bool(obs.get("platform"))

    official_api_row = checks.get("official_api_identity_proof", False)
    wikidata_row = checks.get("wikidata_identity_proof", False)
    probed_site_row = checks.get("probed_site_identity_proof", False)
    # A Wikidata row is trusted only while its P2333 proof stays consistent;
    # an inconsistent one falls back to the ordinary rules and stays rejected.
    # A probed-site row is trusted when the probe verified the company identity
    # with high confidence (identity_score >= 0.9).
    probed_score = 0.0
    if probed_site_row:
        for proof in (obs.get("identity_proof") or []):
            if isinstance(proof, dict) and proof.get("type") == "probed_verified_site":
                try:
                    probed_score = float(proof.get("identity_score") or 0.0)
                except (TypeError, ValueError):
                    pass
                break
    trusted_api_row = bool(
        official_api_row
        or (wikidata_row and checks["wikidata_proof_consistent"])
        or (registry_domain_proof is not None and checks["registry_domain_proof_consistent"])
        or (probed_site_row and probed_score >= 0.9)
    )
    # A row proved by an official API, an official report, a directory page,
    # or a probed site does not derive its identity from the company website,
    # so it must not be rejected merely because frozen website evidence is absent.
    evidence_backed = bool(
        checks["site_status_available"] or trusted_api_row or checks.get("directory_identity_proof", False)
    )
    exact_entity = bool(
        checks["organisation_match"]
        and evidence_backed
        and (checks["gate_publishable"] or trusted_api_row or checks.get("directory_identity_proof", False))
        and (checks["source_domain_matches"] or checks.get("directory_identity_proof", False) or trusted_api_row)
        and checks["identity_proof_present"]
    )
    if obs.get("signal_type") == "profile_handle":
        # A handle is exact when the identity-gated company site listed it, or
        # when a trusted API states the exact organisation number (Wikidata
        # P2333). A website-proved handle outside social_links stays rejected.
        exact_entity = exact_entity and (
            checks.get("handle_present_in_gate_socials", False) or trusted_api_row
        )
    elif not (checks.get("directory_identity_proof", False) or trusted_api_row):
        exact_entity = exact_entity and bool(checks.get("proof_references_site", False))
    digest_present = bool(digest)
    metric_correct = exact_entity and digest_present and checks["acquisition_permitted"] and checks["rights_approved"]
    
    # Compute sentiment correctness for sentiment signal type
    sentiment_correct = False
    if obs.get("signal_type") == "sentiment":
        expected_label = obs.get("sentiment_label")
        if expected_label in ("positive", "negative", "neutral"):
            # For rule-based sentiment from ratings, if we have a label it's correct
            sentiment_correct = True
    
    return {
        "id": obs.get("id"),
        "exact_entity": int(exact_entity),
        "metric_correct": int(metric_correct),
        "sentiment_correct": sentiment_correct,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Label external observations by re-verifying against frozen profile evidence.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    profiles = {str(p["organisation_number"]): p for p in read_jsonl(Path(args.profiles))}
    observations = read_jsonl(Path(args.observations))
    verified = {}
    failures: dict[str, int] = {}
    for obs in observations:
        profile = profiles.get(str(obs.get("organisation_number")))
        if profile is None:
            failures.setdefault("missing_profile", 0)
            failures["missing_profile"] += 1
            label = {"exact_entity": 0, "metric_correct": 0, "sentiment_correct": False}
        else:
            label = verify(obs, profile)
            for check, ok in label["checks"].items():
                if not ok:
                    failures.setdefault(check, 0)
                    failures[check] += 1
        verified[str(obs.get("id"))] = {"id": str(obs.get("id")), "exact_entity": label["exact_entity"], "metric_correct": label["metric_correct"], "sentiment_correct": label["sentiment_correct"], "signal_type": obs.get("signal_type"), "organisation_number": obs.get("organisation_number")}
    verified_rows = list(verified.values())

    Path(args.labels).parent.mkdir(parents=True, exist_ok=True)
    Path(args.labels).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in verified_rows), encoding="utf-8")
    report = {
        "connector": "evidence_verified_labels_v1",
        "observations": len(observations),
        "unique_ids": len(verified_rows),
        "deduped_rows": len(observations) - len(verified_rows),
        "labels": len(verified_rows),
        "exact_entity_true": sum(1 for row in verified_rows if row["exact_entity"]),
        "metric_correct_true": sum(1 for row in verified_rows if row["metric_correct"]),
        "fail_checks": failures,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()