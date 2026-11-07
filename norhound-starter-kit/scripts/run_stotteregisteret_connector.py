#!/usr/bin/env python3
"""Støtteregisteret (Brønnøysund state aid register) connector — keyless.

Source: https://stottetiltak-registerinfo-api.app.brreg.no/api/v1/soek/stoettetildeling
POST with body: [{"field":"STOETTEMOTTAKER_ORGNR","value":"<orgnr>","matchType":"EXACT_MATCH"}]
No API key required. NLOD 2.0 licence (Brønnøysundregistrene).

One request per company. Publishes up to 10 most recent state-aid awards
whose recipient role carries exactly this organisation number.

Usage:
  uv run python scripts/run_stotteregisteret_connector.py \
    --organisations data/entry-manifest.jsonl \
    --output out/stotteregisteret-external.jsonl \
    --report out/stotteregisteret-report.json \
    --workers 2
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
from decimal import Decimal
from pathlib import Path

API = "https://stottetiltak-registerinfo-api.app.brreg.no/api/v1/soek/stoettetildeling"
GRANT_PAGE = "https://stotte.brreg.no/nb/oppslag/stoettetildeling/{nr}"
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
REQUEST_TIMEOUT = 30
MAX_GRANTS = 10

INSTRUMENT = {
    "skatteEllerAvgiftsFritak": "tax or duty exemption",
    "tilskudd": "grant",
    "laan": "loan",
    "garanti": "guarantee",
    "rentesubsidier": "interest subsidy",
    "egenkapital": "equity",
    "skattefradrag": "tax deduction",
    "redusertSkatt": "reduced tax",
    "annet": "other aid",
}


def _clean_orgnr(v) -> str:
    if v is None:
        return ""
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else str(v)


def _text(v) -> str:
    if isinstance(v, dict):
        for lang in ("NOR", "nor", "nob", "ENG", "eng"):
            if v.get(lang):
                x = v[lang]
                return x[0] if isinstance(x, list) else str(x)
        x = next(iter(v.values()), "")
        return x[0] if isinstance(x, list) else str(x or "")
    if isinstance(v, list):
        return str(v[0]) if v else ""
    return str(v or "")


def fetch_awards(orgnr: str) -> list[dict]:
    """Fetch state-aid awards for one organisation number."""
    body = json.dumps([
        {"field": "STOETTEMOTTAKER_ORGNR", "value": orgnr, "matchType": "EXACT_MATCH"}
    ], separators=(",", ":")).encode("utf-8")

    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"Støtteregisteret failed for {orgnr}: {exc}", flush=True)
        return []

    rows = data.get("stoettetildeling") or []
    awards = []
    for r in rows:
        # Verify the recipient role carries exactly this orgnr
        recipients = [
            x for x in (r.get("rolle") or [])
            if x.get("type") == "rolletype.stoettemottaker"
        ]
        if not any(
            _clean_orgnr((x.get("rolleinnehaverVirksomhet") or {}).get("organisasjonsnummer")) == orgnr
            for x in recipients
        ):
            continue

        giver = next(
            ((x.get("rolleinnehaverVirksomhet") or {}).get("navn")
             for x in (r.get("rolle") or [])
             if x.get("type") == "rolletype.stoettegiver"),
            None,
        )
        inst = (r.get("stoetteinstrument") or "").split(".")[-1]
        amt = r.get("tildeltBeloep") or {}

        value = {
            "title": f"State aid: {INSTRUMENT.get(inst, inst)} from {giver or 'a public body'}",
            "amount": float(amt.get("beloep")) if amt.get("beloep") is not None else None,
            "amount_range_from": amt.get("beloepIntervallFra"),
            "amount_range_to": amt.get("beloepIntervallTil"),
            "currency": amt.get("valuta") or "NOK",
            "giver": _text(giver),
            "instrument": INSTRUMENT.get(inst, inst),
            "reference": r.get("stoettetiltaksnummer"),
            "scheme": r.get("tilknyttetStoetteordning"),
            "page_url": GRANT_PAGE.format(nr=r.get("stoettetiltaksnummer")),
            "date": r.get("tildelingsdato"),
        }
        awards.append(value)

    awards.sort(key=lambda a: a.get("date") or "", reverse=True)
    return awards[:MAX_GRANTS]


def build_observation(orgnr: str, awards: list[dict], retrieved_at: str) -> list[dict]:
    observations = []
    for idx, award in enumerate(awards):
        obs_id = "stotte-" + orgnr + "-" + hashlib.sha256((orgnr + "|" + str(award.get("reference")) + "|" + str(idx)).encode()).hexdigest()[:16]
        observations.append({
            "id": obs_id,
            "organisation_number": orgnr,
            "platform": "stotteregisteret",
            "signal_type": "state_aid_award",
            "source_url": award["page_url"] or API,
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(
                f"{orgnr}|{award.get('reference')}|{award.get('date')}".encode()
            ).hexdigest(),
            "exact_entity": True,
            "identity_proof": [
                {"type": "organisation_number_on_official_api",
                 "detail": f"Støtteregisteret (official Brønnøysund state-aid register) states the recipient organisation number {orgnr}"},
                {"type": "organisasjonsnummer_stottemottaker_equals_orgnr",
                 "detail": f"Støtteregisteret recipient orgnr equals {orgnr}"}
            ],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_api",
            "evidence_span": f"stoettetiltak {award.get('reference')}: {award.get('instrument')} {award.get('amount')} {award.get('currency')} from {award.get('giver')}, tildelingsdato {award.get('date')}"[:500],
            "metrics": {
                "reference": award.get("reference"),
                "date": award.get("date"),
                "amount": award.get("amount"),
                "currency": award.get("currency"),
                "giver": award.get("giver"),
                "instrument": award.get("instrument"),
                "scheme": award.get("scheme"),
                "purpose": award.get("purpose"),
                "category": award.get("category"),
                "url": award["page_url"],
                "method": "organisasjonsnummer_stottemottaker_equals_orgnr",
            },
            "strategy": "stotteregisteret_api_v1",
            "effective_at": award.get("date"),
            "observed_at": retrieved_at,
        })
    return observations


def process_one(orgnr: str, retrieved_at: str) -> tuple[str, list[dict]]:
    awards = fetch_awards(orgnr)
    return orgnr, build_observation(orgnr, awards, retrieved_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Støtteregisteret state aid connector — keyless.")
    parser.add_argument("--organisations", required=True, help="JSONL with organisation_number per line")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--workers", type=int, default=2, help="Parallel workers")
    args = parser.parse_args()

    orgns = [
        line.strip()
        for line in Path(args.organisations).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    observations = []
    companies_with_awards = 0

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        futures = {pool.submit(process_one, org, retrieved_at): org for org in orgns}
        for future in as_completed(futures):
            orgnr, obs = future.result()
            if obs:
                companies_with_awards += 1
            observations.extend(obs)

    observations.sort(key=lambda o: o["organisation_number"])
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations),
        encoding="utf-8",
    )

    report = {
        "connector": "stotteregisteret_state_aid_v1",
        "organisations": len(orgns),
        "companies_with_awards": companies_with_awards,
        "observations": len(observations),
        "api": API,
        "keyless": True,
        "max_grants_per_company": MAX_GRANTS,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
