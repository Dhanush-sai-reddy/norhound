#!/usr/bin/env python3
"""TED (Tenders Electronic Daily) EU procurement connector — keyless.

Source: EU Publications Office Search API v3
  POST https://api.ted.europa.eu/v3/notices/search
No API key required (https://docs.ted.europa.eu/api/latest/index.html).
TED legal notice: notices freely reusable for commercial or non-commercial purposes.

Match: eForms notices carry each organisation's national identifier.
A notice is a contract award for us only when winner-identifier holds our
exact organisation number and winner-country includes NOR.
A notice is a buyer notice only when organisation-identifier-buyer holds it
and buyer-country includes NOR.
Names are never used — only organisation numbers.

One POST per 100 organisation numbers (batch query via winner-identifier IN (...)).
~1 request per 100 companies.

Usage:
  uv run python scripts/run_ted_connector.py \
    --organisations data/entry-manifest.jsonl \
    --output out/ted-external.jsonl \
    --report out/ted-report.json \
    --batch-size 100
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.ted.europa.eu/v3/notices/search"
FIELDS = [
    "publication-number", "notice-title", "publication-date",
    "winner-identifier", "winner-name", "notice-type", "buyer-name",
    "organisation-identifier-buyer", "buyer-country", "winner-country",
    "result-value-notice", "result-value-cur-notice",
    "organisation-name-tenderer", "organisation-country-tenderer",
    "form-type", "procedure-identifier",
]
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_BATCHES = 1.5  # TED rate-limits bursts


def _clean_orgnr(v) -> str:
    """Extract 9-digit orgnr from TED identifier field."""
    if v is None:
        return ""
    s = str(v)
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else s


def _text(v) -> str:
    if isinstance(v, dict):
        for lang in ("nor", "nob", "eng", "NOR", "ENG"):
            if v.get(lang):
                x = v[lang]
                return x[0] if isinstance(x, list) else str(x)
        x = next(iter(v.values()), "")
        return x[0] if isinstance(x, list) else str(x or "")
    if isinstance(v, list):
        return str(v[0]) if v else ""
    return str(v or "")


def fetch_ted_for_batch(orgns: list[str]) -> dict[str, list[dict]]:
    """Query TED for notices matching any orgnr in the batch.

    Returns dict mapping orgnr -> list of notice records.
    """
    results: dict[str, list[dict]] = {o: [] for o in orgns}
    if not orgns:
        return results

    body = json.dumps({
        "query": f"winner-identifier IN ({' '.join(orgns)})",
        "fields": FIELDS,
        "limit": 250,
        "page": 1,
    }).encode()

    page = 1
    while page <= 5:
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
            print(f"TED batch page {page} failed: {exc}", flush=True)
            break

        notices = data.get("notices") or []
        for n in notices:
            winners = n.get("winner-identifier") or []
            buyers = n.get("organisation-identifier-buyer") or []
            winner_countries = n.get("winner-country") or []
            buyer_countries = n.get("buyer-country") or []

            pub = n.get("publication-number")
            notice = {
                "publication_number": pub,
                "notice_title": _text(n.get("notice-title")),
                "publication_date": (n.get("publication-date") or "")[:10] or None,
                "notice_type": n.get("notice-type"),
                "winner_name": _text(n.get("winner-name")),
                "buyer_name": _text(n.get("buyer-name")),
                "result_value": n.get("result-value-notice"),
                "result_currency": n.get("result-value-cur-notice"),
                "form_type": n.get("form-type"),
                "procedure_identifier": n.get("procedure-identifier"),
                "page_url": f"https://ted.europa.eu/en/notice/-/detail/{pub}" if pub else None,
            }

            for w in winners:
                w_clean = _clean_orgnr(w)
                if w_clean in results and "NOR" in winner_countries:
                    results[w_clean].append({**notice, "role": "winner"})

            for b in buyers:
                b_clean = _clean_orgnr(b)
                if b_clean in results and "NOR" in buyer_countries:
                    results[b_clean].append({**notice, "role": "buyer"})

        if len(notices) < 250:
            break
        page += 1
        body = json.dumps({
            "query": f"winner-identifier IN ({' '.join(orgns)})",
            "fields": FIELDS,
            "limit": 250,
            "page": page,
        }).encode()
        time.sleep(SLEEP_BETWEEN_BATCHES)

    return results


def build_observation(orgnr: str, notices: list[dict], retrieved_at: str) -> list[dict]:
    """Convert TED notices into observation dicts."""
    observations = []
    won = [n for n in notices if n.get("role") == "winner"]
    bought = [n for n in notices if n.get("role") == "buyer"]

    for idx, n in enumerate(won[:25]):
        obs_id = "ted-award-" + orgnr + "-" + hashlib.sha256((orgnr + "|" + n["publication_number"] + "|" + str(idx)).encode()).hexdigest()[:16]
        observations.append({
            "id": obs_id,
            "organisation_number": orgnr,
            "platform": "ted_europa",
            "signal_type": "public_contract_award",
            "source_url": n["page_url"] or API,
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(
                f"{orgnr}|{n['publication_number']}|{n['notice_type']}".encode()
            ).hexdigest(),
            "exact_entity": True,
            "identity_proof": [
                {"type": "organisation_number_on_official_api",
                 "detail": f"TED eForms notice states the organisation number {orgnr} on the official EU procurement API"},
                {"type": "winner_identifier_equals_orgnr",
                 "detail": f"TED eForms winner-identifier equals {orgnr} (winner-country NOR)"}
            ],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_api",
            "evidence_span": f"TED notice {n['publication_number']} — winner-identifier {orgnr}: {n['notice_title']}"[:500],
            "metrics": {
                "notice": n["publication_number"],
                "date": n["publication_date"],
                "notice_type": n["notice_type"],
                "title": n["notice_title"],
                "buyer": n["buyer_name"],
                "notice_total_value": n["result_value"],
                "currency": n["result_currency"],
                "url": n["page_url"],
                "method": "winner_identifier_equals_orgnr",
            },
            "strategy": "ted_search_v3_eforms",
            "effective_at": n["publication_date"],
            "observed_at": retrieved_at,
        })

    for idx, n in enumerate(bought[:5]):
        obs_id = "ted-procurement-" + orgnr + "-" + hashlib.sha256((orgnr + "|" + n["publication_number"] + "|" + str(idx)).encode()).hexdigest()[:16]
        observations.append({
            "id": obs_id,
            "organisation_number": orgnr,
            "platform": "ted_europa",
            "signal_type": "procurement_notice",
            "source_url": n["page_url"] or API,
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(
                f"{orgnr}|{n['publication_number']}|buyer".encode()
            ).hexdigest(),
            "exact_entity": True,
            "identity_proof": [
                {"type": "organisation_number_on_official_api",
                 "detail": f"TED eForms notice states the organisation number {orgnr} on the official EU procurement API"},
                {"type": "organisation_identifier_buyer_equals_orgnr",
                 "detail": f"TED eForms buyer-identifier equals {orgnr} (buyer-country NOR)"}
            ],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_api",
            "evidence_span": f"TED notice {n['publication_number']} — buyer-identifier {orgnr}: {n['notice_title']}"[:500],
            "metrics": {
                "notice": n["publication_number"],
                "date": n["publication_date"],
                "notice_type": n["notice_type"],
                "title": n["notice_title"],
                "role": "buyer",
                "url": n["page_url"],
                "method": "organisation_identifier_buyer_equals_orgnr",
            },
            "strategy": "ted_search_v3_eforms",
            "effective_at": n["publication_date"],
            "observed_at": retrieved_at,
        })

    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="TED EU procurement connector — keyless.")
    parser.add_argument("--organisations", required=True, help="JSONL with organisation_number per line")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--batch-size", type=int, default=100, help="Org numbers per TED query")
    args = parser.parse_args()

    orgns = [
        line.strip()
        for line in Path(args.organisations).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    observations = []
    total_queries = 0

    for i in range(0, len(orgns), args.batch_size):
        batch = orgns[i:i + args.batch_size]
        print(f"TED batch {i // args.batch_size + 1}: {len(batch)} org numbers", flush=True)
        results = fetch_ted_for_batch(batch)
        total_queries += 1
        for orgnr in batch:
            notices = results.get(orgnr, [])
            if notices:
                observations.extend(build_observation(orgnr, notices, retrieved_at))
        time.sleep(SLEEP_BETWEEN_BATCHES)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations),
        encoding="utf-8",
    )

    companies_with_awards = len({o["organisation_number"] for o in observations})
    report = {
        "connector": "ted_eu_procurement_v1",
        "organisations": len(orgns),
        "batches": total_queries,
        "companies_with_awards": companies_with_awards,
        "observations": len(observations),
        "api": API,
        "keyless": True,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
