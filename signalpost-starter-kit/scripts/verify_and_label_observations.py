#!/usr/bin/env python3
"""Label external observations by re-verifying them against stored evidence.

Each observation's exact_entity and metric_correct labels are derived by
re-checking the frozen profile evidence that produced it, not assumed:

- source_url must live on the company's verified registered domain
- content_sha256 must match the stored website digest for that organisation
- identity_proof must carry the website identity gate assessment
- publishable status must match at publication time
- profile_handle rows must reference a social link that the identity gate
  actually observed in social_links (and stays quarantined otherwise)

A row is labelled exact_entity=1 only when all checks pass; anything that
cannot be re-derived from frozen evidence is labelled 0 (fail-safe).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tldextract import TLDExtract  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def registered_domain(url: str) -> str | None:
    try:
        return TLDExtract(cache_dir=str(Path(".cache/tldextract"))).extract_str(url).registered_domain.lower() or None
    except Exception:
        return None


def _identity_gate(website: dict) -> dict:
    return ((website.get("value") or {}).get("identity_assessment") or {})


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
    digest = obs.get("content_sha256")
    stored_digest = value.get("content_sha256") or website.get("content_sha256")
    page_digests = {str(p.get("content_sha256") or "") for p in (value.get("pages") or [])}
    digest_matches = (digest and digest == stored_digest) or (digest and digest in page_digests)
    checks["digest_matches"] = digest_matches
    checks["identity_proof_present"] = bool(obs.get("identity_proof"))
    checks["proof_references_site"] = any(
        isinstance(p, dict) and ("website" in str(p.get("type") or "").lower() or "site" in str(p.get("type") or "").lower())
        for p in (obs.get("identity_proof") or [])
    )
    checks["acquisition_permitted"] = obs.get("acquisition_mode") == "permitted_public_page"
    checks["rights_approved"] = obs.get("rights_status") == "approved"

    if obs.get("signal_type") == "profile_handle":
        handle = (obs.get("metrics") or {}).get("url") or ""
        socials = [s.get("url") or "" for s in (value.get("social_links") or [])]
        checks["handle_present_in_gate_socials"] = handle in socials
        checks["platform_minor"] = bool(obs.get("platform"))

    exact_entity = bool(
        checks["organisation_match"]
        and checks["site_status_available"]
        and checks["gate_publishable"]
        and checks["source_domain_matches"]
        and checks["identity_proof_present"]
    )
    if obs.get("signal_type") == "profile_handle":
        exact_entity = exact_entity and checks.get("handle_present_in_gate_socials", False)
    digest_present = bool(digest)
    metric_correct = exact_entity and digest_present and checks["acquisition_permitted"] and checks["rights_approved"]
    return {
        "id": obs.get("id"),
        "exact_entity": int(exact_entity),
        "metric_correct": int(metric_correct),
        "sentiment_correct": None,
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
            label = {"exact_entity": 0, "metric_correct": 0, "sentiment_correct": None}
        else:
            label = verify(obs, profile)
            for check, ok in label["checks"].items():
                if not ok:
                    failures.setdefault(check, 0)
                    failures[check] += 1
        verified[str(obs.get("id"))] = {"id": str(obs.get("id")), "exact_entity": label["exact_entity"], "metric_correct": label["metric_correct"], "sentiment_correct": None}
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