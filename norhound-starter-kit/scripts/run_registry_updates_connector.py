#!/usr/bin/env python3
"""Brønnøysund registry-update feed connector (dated official activity).

The oppdateringer endpoint lists dated registry events per organisation
number — official, exact-orgnr-keyed, no key, no matching. One request per
company; newest events kept (MAX_EVENTS). Emitted as registry_update
observations filling the dated-activity family.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import publishable_observation  # noqa: E402

UPDATES_API = "https://data.brreg.no/enhetsregisteret/api/oppdateringer/enheter"
PAGE_SIZE = 200
MAX_EVENTS = 20
HTTP_TIMEOUT = 45


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(sanitize_line_separators(json.dumps(row, ensure_ascii=False, separators=(",", ":"))) + "\n")
    temporary.replace(path)


def events_url(org: str) -> str:
    return f"{UPDATES_API}?organisasjonsnummer={org}&size={PAGE_SIZE}"


def _fetch_events(org: str) -> dict[str, Any]:
    request = urllib.request.Request(events_url(org), headers={"Accept": "application/json", "User-Agent": "NorHound/1.0 (signalpost research)"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def collect(org: str, payload: dict[str, Any], *, retrieved_at: str) -> list[dict[str, Any]]:
    events = ((payload.get("_embedded") or {}).get("oppdaterteEnheter") or [])
    events = [e for e in events if isinstance(e, dict) and str(e.get("organisasjonsnummer") or "") == org]
    events.sort(key=lambda e: str(e.get("dato") or ""), reverse=True)
    observations = []
    for event in events[:MAX_EVENTS]:
        dato = event.get("dato")
        date = dato[:10] if isinstance(dato, str) and len(dato) >= 10 else None
        if not date:
            continue
        change_type = str(event.get("endringstype") or "Endring")
        links = event.get("_links") or {}
        enhet = (links.get("enhet") or {}).get("href") or f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}"
        payload_bytes = json.dumps({"org": org, "id": event.get("oppdateringsid"), "date": date, "type": change_type}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        observations.append({
            "id": "registry-update-" + hashlib.sha256(payload_bytes).hexdigest()[:24],
            "organisation_number": org,
            "platform": "brreg",
            "signal_type": "registry_update",
            "source_url": enhet,
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "observed_at": date,
            "exact_entity": True,
            "identity_proof": [{
                "type": "organisation_number_on_official_api",
                "source": "data.brreg.no",
                "source_class": "official_registry_updates",
                "matched_organisation_number": org,
                "explanation": "Update event is keyed by this organisation number in the official feed.",
            }],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_registry_bulk",
            "evidence_span": f"Registry update {date}: {change_type}"[:1200],
            "metrics": {"date": date, "change_type": change_type, "interpretation": "Dated official registry event."},
            "strategy": "registry_updates_feed",
        })
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Brønnøysund registry-update feed connector.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    profiles = read_jsonl(Path(args.profiles))
    if args.limit:
        profiles = profiles[: args.limit]
    stamped = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    observations: list[dict[str, Any]] = []
    matched = 0
    for profile in profiles:
        org = str(profile.get("organisation_number") or "")
        if not org.isdigit():
            continue
        try:
            payload = _fetch_events(org)
        except Exception:
            continue
        items = [item for item in collect(org, payload, retrieved_at=stamped) if publishable_observation(item)]
        if items:
            matched += 1
        observations.extend(items)
    write_jsonl(Path(args.output), observations)
    report = {
        "connector": "registry_updates_v1",
        "profiles": len(profiles),
        "organisations_with_updates": matched,
        "publishable_observations": len(observations),
        "claim_boundary": "Dated official registry events keyed by organisation number; newest kept.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
