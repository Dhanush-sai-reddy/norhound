#!/usr/bin/env python3
"""Publish registry-recorded contacts as exact-entity observations.

The Brønnøysund bulk record already carries epostadresse/telefon/mobil for
many companies. The record itself is keyed by organisation number, so these
facts are exact by construction — no name matching, no separate fetch, zero
new requests. They fill the contact family (contact_email/contact_phone).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


FIELDS = (
    ("epostadresse", "contact_email"),
    ("telefon", "contact_phone"),
    ("mobil", "contact_phone"),
)


def observations_for_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    org = str(profile.get("organisation_number") or "")
    if not org.isdigit():
        return []
    registry = (profile.get("evidence") or {}).get("registry") or {}
    if registry.get("status") != "available":
        return []
    value = registry.get("value") or {}
    source_url = registry.get("source_url") or ""
    digest = registry.get("content_sha256") or ""
    if not source_url or len(str(digest)) != 64:
        return []
    observations = []
    for field, signal in FIELDS:
        contact = str(value.get(field) or "").strip()
        if not contact:
            continue
        observations.append({
            "id": "registry-contact-" + hashlib.sha256(f"{org}|{signal}|{contact}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "brreg",
            "signal_type": signal,
            "source_url": source_url,
            "retrieved_at": registry.get("retrieved_at"),
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": [{
                "type": "organisation_number_on_official_api",
                "source": "data.brreg.no",
                "source_class": "official_registry_bulk",
                "matched_organisation_number": org,
                "explanation": "Contact is read from the Brønnøysund registry record keyed by this organisation number.",
            }],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_registry_bulk",
            "evidence_span": contact[:300],
            "metrics": {"registry_field": field, "interpretation": "Registry-recorded contact; exact by record key."},
            "strategy": "registry_contact_exact",
        })
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit registry-recorded contacts as observations.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [item for profile in profiles for item in observations_for_profile(profile)]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "registry_contacts_v1",
        "profiles": len(profiles),
        "observations": len(rows),
        "claim_boundary": "Registry-recorded contacts only; record key is the organisation number.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
