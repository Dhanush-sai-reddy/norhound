#!/usr/bin/env python3
"""
GLEIF LEI connector — exact-entity matching via Legal Entity Identifier.

Norwegian LEI records carry the organisation number in
`attributes.registration.validatedAs` (e.g. "932 862 581") and are validated by
Brønnøysundregistrene (`registration.validatedAt.id == "RA000472"`). That gives a
true exact-entity join: we normalise `validatedAs` to nine digits and match it
against the org number. No name matching, no fuzzy scoring.

`validatedAs` is not filterable through the GLEIF API, but the registration
authority is, so the index build pages the Brønnøysund-validated set once and
caches it. Query time is then a local dict lookup with zero network requests.

Index build (one-off, ~318 pages of 200):
    python scripts/run_gleif_connector.py --build-index --index data/gleif-index.jsonl

Query:
    python scripts/run_gleif_connector.py --profiles P.jsonl --organisations IDS.txt \
        --output out.jsonl --report report.json --index data/gleif-index.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


API_BASE = "https://api.gleif.org/api/v1/lei-records"
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"

# GLEIF code for Brønnøysundregistrene, the Norwegian register of business enterprises.
BRONNOYSUND = "RA000472"
PAGE_SIZE = 200


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalise_org(value: object) -> str:
    """Reduce any org-number rendering to nine digits, or '' if not one."""
    digits = re.sub(r"\D", "", str(value))
    return digits if len(digits) == 9 else ""


def fetch_json(url: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        request = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "application/vnd.api+json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read())
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def slim_record(record: dict) -> dict | None:
    """Reduce one GLEIF record to the fields we publish, keyed by org number."""
    attributes = record.get("attributes") or {}
    entity = attributes.get("entity") or {}
    registration = attributes.get("registration") or {}

    org = normalise_org(registration.get("validatedAs"))
    if not org:
        return None
    authority = ((registration.get("validatedAt") or {}).get("id")) or ""
    if authority != BRONNOYSUND:
        return None

    address = entity.get("legalAddress") or {}
    hq = entity.get("headquartersAddress") or {}
    return {
        "organisation_number": org,
        "lei": record.get("id"),
        "legal_name": (entity.get("legalName") or {}).get("name", ""),
        "other_names": [n.get("value") for n in (entity.get("otherNames") or []) if n.get("value")],
        "lei_status": attributes.get("leiStatus"),
        "entity_status": attributes.get("entityStatus"),
        "entity_status_date": attributes.get("entityStatusDate"),
        "legal_form": entity.get("legalForm") or {},
        "registered_as": entity.get("registeredAs") or {},
        "registered_address": {
            "address_lines": address.get("addressLines") or [],
            "city": address.get("city"),
            "country": address.get("country"),
            "postal_code": address.get("postalCode"),
        },
        "headquarters_address": {
            "address_lines": hq.get("addressLines") or [],
            "city": hq.get("city"),
            "country": hq.get("country"),
            "postal_code": hq.get("postalCode"),
        },
        "registration_status": registration.get("status"),
        "registration_authority": authority,
        "initial_registration_date": registration.get("initialRegistrationDate"),
        "last_update_date": registration.get("lastUpdateDate"),
        "next_renewal_date": registration.get("nextRenewalDate"),
        "corroboration_level": registration.get("corroborationLevel"),
    }


def build_index(index_path: Path, page_size: int = PAGE_SIZE) -> dict:
    """Page the Brønnøysund-validated LEI set once and cache it as JSONL."""
    url = (
        f"{API_BASE}?filter[registration.validatedAt]={BRONNOYSUND}"
        f"&page[size]={page_size}"
    )
    index_path.parent.mkdir(parents=True, exist_ok=True)

    seen, pages, kept = set(), 0, 0
    with index_path.open("w", encoding="utf-8") as out:
        while url:
            payload = fetch_json(url)
            if not payload:
                print(f"gleif: page {pages + 1} failed, stopping with {kept} records")
                break
            for record in payload.get("data") or []:
                seen.add(record.get("id"))
                slim = slim_record(record)
                if slim:
                    out.write(json.dumps(slim, ensure_ascii=False) + "\n")
                    kept += 1
            pages += 1
            total = ((payload.get("meta") or {}).get("pagination") or {}).get("total")
            print(f"gleif: page {pages} -> {kept} Brønnøysund records kept (total={total})")
            url = (payload.get("links") or {}).get("next")
            time.sleep(0.12)
    return {"pages": pages, "records_seen": len(seen), "records_kept": kept, "index": str(index_path)}


def load_index(index_path: Path) -> dict[str, dict]:
    if not index_path.exists():
        return {}
    index: dict[str, dict] = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        org = normalise_org(row.get("organisation_number"))
        if org and org not in index:
            index[org] = row
    return index


def load_targets(profiles: Path, organisations: Path) -> list[dict]:
    """Org list comes from the text file when given, else from the profiles."""
    targets: list[dict] = []
    if organisations and organisations.exists():
        for line in organisations.read_text(encoding="utf-8").splitlines():
            org = normalise_org(line)
            if org and not any(t["organisation_number"] == org for t in targets):
                targets.append({"organisation_number": org, "name": ""})
        return targets
    with profiles.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                org = normalise_org(row.get("organisation_number"))
                if org:
                    targets.append({"organisation_number": org, "name": row.get("name", "")})
    return targets


def observation_for(org: str, record: dict) -> dict:
    lei = record["lei"]
    retrieved_at = utc_now()
    body = json.dumps(record, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    oid = f"gleif-lei-{org}-{digest[:16]}"
    name = record.get("legal_name") or ""
    return {
        "id": oid,
        "organisation_number": org,
        "signal_type": "legal_entity_identifier",
        "platform": "gleif",
        "source_url": f"https://search.gleif.org/#/record/{lei}",
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "exact_entity": True,
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "official_api",
        "evidence_span": f"GLEIF LEI {lei} registered to organisation number {org} by Brønnøysundregistrene (RA000472)"
        + (f"; legal name {name}" if name else ""),
        "identity_proof": [
            {
                "type": "gleif_registration_validated_as_organisation_number",
                "value": org,
                "source": f"https://api.gleif.org/api/v1/lei-records/{lei}",
            },
            {"type": "gleif_registration_authority", "value": BRONNOYSUND},
        ],
        "metrics": record,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="GLEIF LEI connector (exact org-number match)")
    parser.add_argument("--build-index", action="store_true", help="Page Brønnøysund-validated LEI records into the cache and exit")
    parser.add_argument("--index", type=Path, default=Path("data/gleif-index.jsonl"))
    parser.add_argument("--profiles", type=Path, default=None)
    parser.add_argument("--organisations", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=4, help="accepted for CLI compatibility; queries are local")
    args = parser.parse_args()

    if args.build_index:
        summary = build_index(args.index)
        print(json.dumps(summary, indent=2))
        return 0

    if not args.profiles or not args.output or not args.report:
        parser.error("--profiles, --output and --report are required unless --build-index is used")

    targets = load_targets(args.profiles, args.organisations)
    index = load_index(args.index)
    if not index:
        print(f"gleif: index {args.index} missing or empty — run --build-index first; abstaining")
        args.output.write_text("", encoding="utf-8")
        args.report.write_text(
            json.dumps({"state": "abstained", "reason": "index_not_built", "index": str(args.index)}, indent=2),
            encoding="utf-8",
        )
        return 0

    observations, statuses, matched = [], {}, 0
    for target in targets:
        org = target["organisation_number"]
        record = index.get(org)
        if not record:
            statuses[org] = "no_lei_record"
            continue
        matched += 1
        observations.append(observation_for(org, record))
        statuses[org] = "matched"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(o, ensure_ascii=False) + "\n" for o in observations), encoding="utf-8"
    )
    args.report.write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "targets": len(targets),
                "index_records": len(index),
                "matched_companies": matched,
                "observations": len(observations),
                "unmatched": sum(1 for v in statuses.values() if v == "no_lei_record"),
                "statuses": statuses,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"gleif: {matched}/{len(targets)} companies matched an LEI, {len(observations)} observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())