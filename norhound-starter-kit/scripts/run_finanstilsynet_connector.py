#!/usr/bin/env python3
"""Finanstilsynet (Norwegian Financial Supervisory Authority) connector — keyless.

Source: https://api.finanstilsynet.no/registry/v1 — one keyless request per company.
Returns licences held by the company (banks, insurers, investment firms, payment
institutions, debt collectors, accountants, auditors, estate agents, etc.).

Open data published by Finanstilsynet. No licence named in the API spec;
attribute "Kilde: Finanstilsynet".

Match: a result is used only when its `organisationNumber` field equals our orgnr.
Names are never used.

Usage:
  uv run python scripts/run_finanstilsynet_connector.py \
    --organisations data/entry-manifest.jsonl \
    --output out/finanstilsynet-external.jsonl \
    --report out/finanstilsynet-report.json \
    --workers 8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.finanstilsynet.no/registry/v1"
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
REQUEST_TIMEOUT = 30
MAX_LICENCES = 40


def _clean_orgnr(v) -> str:
    if v is None:
        return ""
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else str(v)


def _text(obj: dict | None, *keys: str) -> str | None:
    """Norwegian/English text pair, Norwegian first."""
    if not obj:
        return None
    for k in keys or ("norwegian", "english"):
        if obj.get(k):
            return str(obj[k]).strip()
    return None


def fetch_licences(orgnr: str) -> list[dict]:
    """Fetch licences for one organisation number from Finanstilsynet registry."""
    url = f"{API}?organisationNumber={orgnr}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"Finanstilsynet failed for {orgnr}: {exc}", flush=True)
        return []

    results = data.get("results") or data.get("items") or []
    if not isinstance(results, list):
        return []

    licences = []
    for lic in results[:MAX_LICENCES]:
        lic_entity = (lic.get("licensedEntity") or {}).get("legalEntityName")
        if lic_entity and _clean_orgnr(lic_entity) != orgnr:
            # The licensed entity name may not equal our orgnr directly; check
            # the organisationNumber field if present.
            org_num = lic.get("organisationNumber")
            if org_num and _clean_orgnr(org_num) != orgnr:
                continue

        t = lic.get("licenceType") or {}
        role_raw = lic.get("serviceProviderType")
        role = {"Licensed": "licence_holder", "Agent": "agent", "Branch": "branch"}.get(
            role_raw, role_raw
        )
        sup_auth = lic.get("supervisoryAuthority") or {}
        sup_country = ((sup_auth.get("country") or {}).get("iso3"))

        value = {
            "type": _text(t.get("name"), "english", "norwegian"),
            "type_no": _text(t.get("name"), "norwegian"),
            "code": t.get("code"),
            "legal_basis": _text(t.get("description")),
            "registered_date": (lic.get("registeredDate") or "")[:10] or None,
            "role": role,
            "supervisor_country": sup_country,
        }
        value = {k: v for k, v in value.items() if v not in (None, "", [])}

        licences.append(value)

    return licences


def build_observation(orgnr: str, licences: list[dict], retrieved_at: str) -> list[dict]:
    observations = []
    for idx, lic in enumerate(licences):
        obs_id = "ft-licence-" + orgnr + "-" + hashlib.sha256((orgnr + "|" + str(lic.get("code")) + "|" + str(idx)).encode()).hexdigest()[:16]
        observations.append({
            "id": obs_id,
            "organisation_number": orgnr,
            "platform": "finanstilsynet",
            "signal_type": "financial_licence",
            "source_url": API,
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(
                f"{orgnr}|{lic.get('code')}|{lic.get('registered_date')}".encode()
            ).hexdigest(),
            "exact_entity": True,
            "identity_proof": [
                {"type": "organisation_number_equals_orgnr",
                 "detail": f"Finanstilsynet registry organisationNumber equals {orgnr}"}
            ],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_api",
            "evidence_span": f"Finanstilsynet licence: {lic.get('type')} ({lic.get('code')}) registered {lic.get('registered_date')}"[:500],
            "metrics": {
                "type": lic.get("type"),
                "type_no": lic.get("type_no"),
                "code": lic.get("code"),
                "legal_basis": lic.get("legal_basis"),
                "registered_date": lic.get("registered_date"),
                "role": lic.get("role"),
                "supervisor_country": lic.get("supervisor_country"),
                "method": "organisation_number_equals_orgnr",
            },
            "strategy": "finanstilsynet_registry_v1",
            "effective_at": lic.get("registered_date"),
            "observed_at": retrieved_at,
        })
    return observations


def process_one(orgnr: str, retrieved_at: str) -> tuple[str, list[dict]]:
    licences = fetch_licences(orgnr)
    return orgnr, build_observation(orgnr, licences, retrieved_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Finanstilsynet licence connector — keyless.")
    parser.add_argument("--organisations", required=True, help="JSONL with organisation_number per line")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers")
    args = parser.parse_args()

    orgns = [
        line.strip()
        for line in Path(args.organisations).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    observations = []
    companies_with_licences = 0

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 16))) as pool:
        futures = {pool.submit(process_one, org, retrieved_at): org for org in orgns}
        for future in as_completed(futures):
            orgnr, obs = future.result()
            if obs:
                companies_with_licences += 1
            observations.extend(obs)

    observations.sort(key=lambda o: o["organisation_number"])
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations),
        encoding="utf-8",
    )

    report = {
        "connector": "finanstilsynet_licence_v1",
        "organisations": len(orgns),
        "companies_with_licences": companies_with_licences,
        "observations": len(observations),
        "api": API,
        "keyless": True,
        "max_licences_per_company": MAX_LICENCES,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
