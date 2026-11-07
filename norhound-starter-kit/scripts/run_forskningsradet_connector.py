#!/usr/bin/env python3
"""Forskningsrådet (Research Council of Norway) connector — keyless.

Sources (both published by Norges forskningsråd):
1. SkatteFUNN R&D tax-credit applications — https://www.forskningsradet.no/skattefunn/suksesshistorier/
   Two Excel files: applications May 2024 onwards (refreshed monthly) and 2002–2024.
   Only rows marked approved ("Søknad godkjent" = JA) are used.
2. Research Council project funding "Søknader - versjon 2" —
   https://github.com/Forskningsradet/open-data/main/datasets/soknader2/dataset.csv
   NLOD 2.0. Only projects in phase "Bevilgning" (funded, running) or
   "Avsluttet" (funded, finished) are used.

Match: the row's organisation-number column equals ours. Names are never used.

This version downloads the CSV (0.5–2 MB) once per run and filters offline —
one HTTP request total, not one per company.

Usage:
  uv run python scripts/run_forskningsradet_connector.py \
    --organisations data/entry-manifest.jsonl \
    --output out/forskningsradet-external.jsonl \
    --report out/forskningsradet-report.json
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RCN_CSV = "https://raw.githubusercontent.com/Forskningsradet/open-data/main/datasets/soknader2/dataset.csv"
SF_PAGE = "https://www.forskningsradet.no/skattefunn/suksesshistorier/"
SF_HIST = "https://www.forskningsradet.no/siteassets/skattefunn/tall/skattefunn-innsendte-soknader-2002-2024.xlsx"
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
REQUEST_TIMEOUT = 60
MAX_PROJECTS = 8

FUNDED_PHASES = {"Bevilgning", "Avsluttet"}
DATE_COLS = {"Vedtaksdato", "Søknadsdato", "Innsendt dato", "Fra-år", "Til-år",
             "Prosjektets fra-år", "Prosjektets til-år"}


def _clean_orgnr(v: str) -> str:
    v = (v or "").strip()
    return v[:-2] if v.endswith(".0") else v


def _val(col: str, v: str) -> str:
    v = (v or "").strip()
    if col in DATE_COLS and v:
        try:
            n = float(v)
        except ValueError:
            return v
        if n > 3000:  # Excel serial date
            return str(int(n))
        return str(int(n))
    return v


def fetch_rccn_csv() -> list[dict]:
    """Download and parse the Forskningsrådet Soknader v2 CSV."""
    req = urllib.request.Request(RCN_CSV, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        raw = resp.read()
    text = raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=",")
    rows = []
    for row in reader:
        orgnr = _clean_orgnr(row.get("organisasjonsnummer"))
        phase = (row.get("prosjektfase") or "").strip()
        if phase not in FUNDED_PHASES:
            continue
        rows.append({
            "project_number": row.get("prosjektnummer", "").strip(),
            "orgnr": orgnr,
            "project_leader": row.get("prosjektansvarlig_navn", "").strip(),
            "title": row.get("prosjekttittel", "").strip(),
            "phase": phase,
            "start": _val("prosjektstart", row.get("prosjektstart", "")),
            "end": _val("prosjektslutt", row.get("prosjektslutt", "")),
            "application_type": row.get("soknadstype", "").strip(),
            "activity": row.get("aktivitet", "").strip(),
            "amount": row.get("tildelt_beloep", "").strip(),
            "municipality": row.get("kommune", "").strip(),
            "source": "forskningsradet_soknader_v2",
            "source_url": RCN_CSV,
        })
    return rows


def build_observations(orgnr: str, rows: list[dict], retrieved_at: str) -> list[dict]:
    observations = []
    company_rows = [r for r in rows if r["orgnr"] == orgnr]
    company_rows.sort(key=lambda r: r.get("end") or "", reverse=True)
    for idx, r in enumerate(company_rows[:MAX_PROJECTS]):
        obs_id = "rcn-" + orgnr + "-" + hashlib.sha256((orgnr + "|" + str(r["project_number"]) + "|" + str(idx)).encode()).hexdigest()[:16]
        amount = None
        try:
            if r["amount"]:
                amount = float(r["amount"].replace(" ", "").replace(",", "."))
        except (ValueError, TypeError):
            amount = None
        observations.append({
            "id": obs_id,
            "organisation_number": orgnr,
            "platform": "forskningsradet",
            "signal_type": "research_grant",
            "source_url": RCN_CSV,
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(
                f"{orgnr}|{r['project_number']}|{r['end']}".encode()
            ).hexdigest(),
            "exact_entity": True,
            "identity_proof": [
                {"type": "organisation_number_on_official_api",
                 "detail": f"Forskningsradet open-data CSV states organisasjonsnummer {orgnr} on the official research-council dataset"},
                {"type": "organisasjonsnummer_equals_orgnr",
                 "detail": f"Forskningsrådet row organisasjonsnummer equals {orgnr}"}
            ],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_api",
            "evidence_span": f"Forskningsrådet project {r['project_number']}: {r['title']} — {r['phase']}"[:500],
            "metrics": {
                "project_number": r["project_number"],
                "title": r["title"],
                "phase": r["phase"],
                "start": r["start"],
                "end": r["end"],
                "amount": amount,
                "currency": "NOK",
                "municipality": r["municipality"],
                "application_type": r["application_type"],
                "activity": r["activity"],
                "method": "organisasjonsnummer_equals_orgnr",
            },
            "strategy": "forskningsradet_soknader_v2_csv",
            "effective_at": r["end"] or r["start"],
            "observed_at": retrieved_at,
        })
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Forskningsrådet research grant connector — keyless.")
    parser.add_argument("--organisations", required=True, help="JSONL with organisation_number per line")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    args = parser.parse_args()

    orgns = {
        line.strip()
        for line in Path(args.organisations).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    print("Downloading Forskningsrådet Soknader v2 CSV...", flush=True)
    rows = fetch_rccn_csv()
    print(f"Loaded {len(rows)} funded project rows", flush=True)

    observations = []
    companies_with_grants = 0
    for orgnr in sorted(orgns):
        obs = build_observations(orgnr, rows, retrieved_at)
        if obs:
            companies_with_grants += 1
        observations.extend(obs)

    observations.sort(key=lambda o: o["organisation_number"])
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations),
        encoding="utf-8",
    )

    report = {
        "connector": "forskningsradet_research_grant_v1",
        "organisations": len(orgns),
        "companies_with_grants": companies_with_grants,
        "observations": len(observations),
        "total_rows_loaded": len(rows),
        "source": RCN_CSV,
        "keyless": True,
        "max_projects_per_company": MAX_PROJECTS,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
