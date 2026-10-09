#!/usr/bin/env python3
"""Publish registry-recorded workforce counts as exact-entity observations.

Brreg holds an employee count for a subset of organisations. That count is
fetched per organisation number from the official enhetsregisteret endpoint,
so the source URL resolves to exactly one legal entity and the payload digest
covers the value being published. No name matching, no new request, zero cost.

The annual-report connector covers the organisations that have no registry
count; this connector covers the ones that do.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _registration_date(registry_value: dict[str, Any]) -> str | None:
    """Brreg's own registration date for the employee-count field, newest first."""
    candidates = [
        str(registry_value.get("registreringsdatoAntallAnsatteEnhetsregisteret") or "").strip(),
        str(registry_value.get("registreringsdatoantallansatteNAVAaregisteret") or "").strip(),
    ]
    dated = sorted((item for item in candidates if item), reverse=True)
    return dated[0] if dated else None


def observations_for_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    org = str(profile.get("organisation_number") or "")
    if not org.isdigit():
        return []
    evidence = profile.get("evidence") or {}
    live = evidence.get("registry_live") or {}
    if live.get("status") != "available":
        return []
    value = live.get("value") or {}
    employees = str(value.get("employees") or "").strip()
    if not employees.isdigit():
        return []
    source_url = str(live.get("source_url") or "")
    digest = str(live.get("content_sha256") or "")
    if not source_url or len(digest) != 64:
        return []
    registry_value = ((evidence.get("registry") or {}).get("value") or {})
    observed_at = _registration_date(registry_value)
    count = int(employees)
    metrics = {"workforce_value": count, "measure": "employees", "registry_field": "employees"}
    if observed_at:
        metrics["registered_at"] = observed_at
    observation = {
        "id": "registry-workforce-" + hashlib.sha256(f"{org}|{count}|{digest}".encode()).hexdigest()[:24],
        "organisation_number": org,
        "platform": "brreg",
        "signal_type": "workforce_snapshot",
        "source_url": source_url,
        "retrieved_at": live.get("retrieved_at"),
        "content_sha256": digest,
        "exact_entity": True,
        "identity_proof": [{
            "type": "organisation_number_on_official_api",
            "source": "data.brreg.no",
            "source_class": "official_registry_live",
            "matched_organisation_number": org,
            "explanation": "Employee count is read from the official enhetsregisteret record fetched for this organisation number.",
        }],
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "official_registry_live",
        "evidence_span": f'"employees": {count}',
        "metrics": metrics,
        "strategy": "registry_workforce_exact",
    }
    if observed_at:
        observation["observed_at"] = observed_at
        observation["effective_at"] = observed_at
    return [observation]


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit registry-recorded workforce counts as observations.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [item for profile in profiles for item in observations_for_profile(profile)]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "registry_workforce_v1",
        "profiles": len(profiles),
        "observations": len(rows),
        "claim_boundary": "Registry-recorded employee count only, from the official per-organisation enhetsregisteret record.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
