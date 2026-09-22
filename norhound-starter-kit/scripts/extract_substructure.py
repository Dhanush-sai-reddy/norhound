#!/usr/bin/env python3
"""Publish Brønnøysund sub-unit and group-structure facts as observations.

The batch already fetches underenheter (locations module) and konsernstruktur
(group module) into every envelope. These stores are official-api and keyed by
organisation number, so turning them into observations adds exact-entity facts
for organizational structure at zero additional request cost. Only records the
envelope itself proves: subunits belonging to this parent, and the parent's own
children. No inference about affiliation beyond the declared link.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _base(profile: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any] | None:
    org = str(profile.get("organisation_number") or "")
    module = (profile.get("evidence") or {}).get(evidence["module"]) or {}
    value = module.get("value") or {}
    source_url = module.get("source_url") or ""
    digest = module.get("content_sha256") or ""
    retrieved_at = module.get("retrieved_at") or ""
    if module.get("status") != "available" or not source_url or len(str(digest)) != 64:
        return None
    return {
        "organisation_number": org,
        "platform": "brreg",
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "exact_entity": True,
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "official_registry_bulk",
    }


def observations_for_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    org = str(profile.get("organisation_number") or "")
    if not org.isdigit():
        return []
    observations = []
    locations = (profile.get("evidence") or {}).get("locations") or {}
    if locations.get("status") == "available":
        base = _base(profile, {"module": "locations"})
        for subunit in (locations.get("value") or {}).get("locations") or []:
            if not isinstance(subunit, dict):
                continue
            name = str(subunit.get("name") or "").strip()
            if not name:
                continue
            span = name[:300]
            base_out = dict(base or {})
            base_out["id"] = "subunit-" + hashlib.sha256(f"{org}|{name}".encode()).hexdigest()[:24]
            base_out["signal_type"] = "subunit"
            base_out["evidence_span"] = span
            base_out["identity_proof"] = [{
                "type": "organisation_number_on_official_api",
                "source": "data.brreg.no",
                "source_class": "official_subunits",
                "matched_organisation_number": org,
                "explanation": "Sub-unit is declared under this parent organisation number by Brønnøysund.",
            }]
            base_out["metrics"] = {
                "subunit_organisation_number": subunit.get("organisation_number"),
                "municipality": (subunit.get("address") or {}).get("kommune") if isinstance(subunit.get("address"), dict) else None,
                "interpretation": "Officially registered sub-unit of this organisation.",
            }
            observations.append(base_out)
    group = (profile.get("evidence") or {}).get("group") or {}
    if group.get("status") == "available":
        base = _base(profile, {"module": "group"})
        value = group.get("value") or {}
        for child in value.get("children") or []:
            if not isinstance(child, dict):
                continue
            name = str(child.get("navn") or "").strip()
            if not name:
                continue
            base_out = dict(base or {})
            base_out["id"] = "group-child-" + hashlib.sha256(f"{org}|{name}".encode()).hexdigest()[:24]
            base_out["signal_type"] = "group_child"
            base_out["evidence_span"] = name[:300]
            base_out["identity_proof"] = [{
                "type": "organisation_number_on_official_api",
                "source": "data.brreg.no",
                "source_class": "official_group_structure",
                "matched_organisation_number": org,
                "explanation": "Structure record names this entity as parent of the declared child.",
            }]
            base_out["metrics"] = {
                "child_organisation_number": child.get("organisasjonsnummer"),
                "ownership": child.get("grunnlag"),
                "relation": (child.get("knytningsform") or {}).get("beskrivelse") if isinstance(child.get("knytningsform"), dict) else None,
                "interpretation": "Group-structure relation declared by Brønnøysund.",
            }
            observations.append(base_out)
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Brønnøysund sub-unit and group facts as observations.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [item for profile in profiles for item in observations_for_profile(profile)]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report = {
        "connector": "substructure_v1",
        "profiles": len(profiles),
        "observations": len(rows),
        "subunits": sum(1 for r in rows if r["signal_type"] == "subunit"),
        "group_children": sum(1 for r in rows if r["signal_type"] == "group_child"),
        "claim_boundary": "Only links Brønnøysund declares in the already-fetched envelope stores.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()