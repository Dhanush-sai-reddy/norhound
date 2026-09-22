#!/usr/bin/env python3
"""Wikidata P2333 (Norwegian organisation number) connector.

Wikidata carries the organisation number as property P2333, so entity
resolution is decisive rather than inferred: the number is the match key and
no name is ever consulted. Content is CC0; the supported MediaWiki API is
used (never the disallowed SPARQL endpoint). Batched lookup costs roughly six
requests per 100 companies.

Two modes, mirroring the NAV feed connector:
  --build-index   Prime a frozen index (org -> qid, values, handles, wikipedia).
  (connector)     Read profiles + frozen index, emit publishable observations:
                  wikidata company_profile, wikipedia company_profile(s), and
                  curated social handles as profile_handle observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import publishable_observation  # noqa: E402

API = "https://www.wikidata.org/w/api.php"
ENTITY_URL = "https://www.wikidata.org/wiki/{qid}"
ORG_NUMBER_PROPERTY = "P2333"
SEARCH_BATCH = 50
ENTITY_BATCH = 50
HTTP_TIMEOUT = 45

VALUE_PROPERTIES = {
    "P856": "wikidata.website",
    "P571": "wikidata.inception",
    "P1128": "wikidata.employees",
}
HANDLE_PROPERTIES = {
    "P2002": ("x", "https://x.com/{}"),
    "P2013": ("facebook", "https://www.facebook.com/{}"),
    "P2003": ("instagram", "https://www.instagram.com/{}"),
    "P2397": ("youtube", "https://www.youtube.com/channel/{}"),
    "P4264": ("linkedin", "https://www.linkedin.com/company/{}"),
}
WIKIPEDIA_SITES = {"nowiki": "no", "enwiki": "en"}


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


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _claim_value(entity: dict[str, Any], prop: str) -> Any:
    try:
        snak = entity["claims"][prop][0]["mainsnak"]
        if snak.get("snaktype") != "value":
            return None
        value = snak["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None
    if isinstance(value, dict):
        if "time" in value:
            return str(value["time"]).lstrip("+")[:10]
        if "amount" in value:
            return str(value["amount"]).lstrip("+")
        return None
    return value


def _http_get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "NorHound/1.0 (signalpost research)"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            break
        except TimeoutError as exc:
            last_error = exc
    raise last_error if last_error is not None else RuntimeError("wikidata fetch failed")


def prime_index(
    organisations: Iterable[str],
    fetch: Callable[[str], dict[str, Any]] = _http_get_json,
    *,
    retrieved_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    orgs = [str(o).strip() for o in organisations if str(o).strip().isdigit() and len(str(o).strip()) == 9]
    if not orgs:
        return {}
    stamped = retrieved_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    qids: list[str] = []
    for index, chunk in enumerate(_chunks(orgs, SEARCH_BATCH)):
        if index:
            time.sleep(1.0)
        query = "haswbstatement:" + "|".join(f"{ORG_NUMBER_PROPERTY}={o}" for o in chunk)
        payload = fetch(
            f"{API}?action=query&list=search&srsearch={urllib.parse.quote(query)}"
            f"&srlimit={SEARCH_BATCH}&format=json"
        )
        for hit in (payload.get("query") or {}).get("search", []) or []:
            if str(hit.get("title", "")).startswith("Q"):
                qids.append(str(hit["title"]))
    wanted = set(orgs)
    by_org: dict[str, dict[str, Any]] = {}
    for index, chunk in enumerate(_chunks(sorted(set(qids)), ENTITY_BATCH)):
        if index:
            time.sleep(1.0)
        payload = fetch(
            f"{API}?action=wbgetentities&ids={'|'.join(chunk)}"
            f"&props=claims|labels|sitelinks&languages=nb|en"
            f"&sitefilter={'|'.join(WIKIPEDIA_SITES)}&format=json"
        )
        for qid, entity in ((payload.get("entities") or {}).items()):
            if not isinstance(entity, dict):
                continue
            org = str(_claim_value(entity, ORG_NUMBER_PROPERTY) or "").strip()
            if org not in wanted or org in by_org:
                continue
            digest = hashlib.sha256(json.dumps(entity, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            by_org[org] = {
                "qid": qid,
                "label": ((entity.get("labels") or {}).get("nb") or (entity.get("labels") or {}).get("en") or {}).get("value"),
                "values": {field: _claim_value(entity, prop) for prop, field in VALUE_PROPERTIES.items()},
                "handles": [
                    {"platform": platform, "url": template.format(_claim_value(entity, prop)), "property": prop}
                    for prop, (platform, template) in HANDLE_PROPERTIES.items()
                    if _claim_value(entity, prop)
                ],
                "wikipedia": [
                    {"lang": lang, "url": f"https://{lang}.wikipedia.org/wiki/{((entity.get('sitelinks') or {}).get(site) or {}).get('title', '').replace(' ', '_')}"}
                    for site, lang in WIKIPEDIA_SITES.items()
                    if (entity.get("sitelinks") or {}).get(site)
                ],
                "retrieved_at": stamped,
                "content_sha256": digest,
            }
    return by_org


def collect(org: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    qid = entry["qid"]
    entity_url = ENTITY_URL.format(qid=qid)
    proof = {
        "type": "organisation_number_on_wikidata",
        "source": "wikidata.org",
        "source_class": "open_knowledge_base",
        "matched_organisation_number": org,
        "explanation": f"Wikidata entity {qid} carries property P2333 (Norwegian organisation number) equal to the profile organisation number; no name matching involved.",
    }
    base = {
        "organisation_number": org,
        "retrieved_at": entry["retrieved_at"],
        "content_sha256": entry["content_sha256"],
        "exact_entity": True,
        "identity_proof": [proof],
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "public_mention",
        "strategy": "wikidata_p2333_orgnr_match",
    }
    observations = [{
        **base,
        "id": f"wikidata-{org}",
        "platform": "wikidata",
        "signal_type": "company_profile",
        "source_url": entity_url,
        "evidence_span": f"{ORG_NUMBER_PROPERTY} = {org} on {qid} ({entry.get('label')})"[:1200],
        "metrics": {"qid": qid, "label": entry.get("label"), "values": entry.get("values") or {}},
    }]
    for page in entry.get("wikipedia") or []:
        observations.append({
            **base,
            "id": f"wikidata-{org}-wikipedia-{page['lang']}",
            "platform": "wikipedia",
            "signal_type": "company_profile",
            "source_url": page["url"],
            "evidence_span": f"Wikipedia article linked from Wikidata entity {qid} ({entry.get('label')})"[:1200],
            "metrics": {"language": page["lang"], "qid": qid},
        })
    for index, handle in enumerate(entry.get("handles") or []):
        observations.append({
            **base,
            "id": f"wikidata-{org}-handle-{handle['platform']}-{index}",
            "platform": handle["platform"],
            "signal_type": "profile_handle",
            "source_url": entity_url,
            "evidence_span": handle["url"][:1200],
            "metrics": {"platform": handle["platform"], "url": handle["url"], "property": handle["property"], "qid": qid},
        })
    return observations


def run_connector(profiles: list[dict], index: dict[str, dict[str, Any]], output_path: Path, report_path: Path) -> None:
    observations: list[dict[str, Any]] = []
    matched = 0
    for profile in profiles:
        org = str(profile.get("organisation_number") or "")
        entry = index.get(org)
        if not entry:
            continue
        matched += 1
        observations.extend(item for item in collect(org, entry) if publishable_observation(item))
    write_jsonl(output_path, observations)
    report = {
        "connector": "wikidata_p2333_v1",
        "mode": "run_connector",
        "profiles": len(profiles),
        "organisations_matched": matched,
        "publishable_observations": len(observations),
        "claim_boundary": "Only Wikidata entities whose P2333 equals the profile organisation number are emitted; the number is the match key, no name consulted.",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Wikidata P2333 organisation-number connector.")
    parser.add_argument("--build-index", action="store_true")
    parser.add_argument("--organisations", default="entry-web1000.jsonl")
    parser.add_argument("--profiles", default="out/web1000-profiles.jsonl")
    parser.add_argument("--index", default="data/wikidata-index.jsonl")
    parser.add_argument("--output", default="out/web1000batch.wikidata.jsonl")
    parser.add_argument("--report", default="out/web1000batch.wikidata-report.json")
    args = parser.parse_args()
    if args.build_index:
        rows = read_jsonl(Path(args.organisations))
        orgs = [str(r.get("organisation_number") or "") for r in rows]
        index = prime_index(orgs)
        stamped = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        write_jsonl(Path(args.index), [{"organisation_number": org, **entry} for org, entry in sorted(index.items())])
        Path(args.report).write_text(json.dumps({
            "connector": "wikidata_p2333_v1", "mode": "index_build", "built_at": stamped,
            "organisations": len(orgs), "entities_matched": len(index), "index_path": str(args.index),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"indexed {len(index)}/{len(orgs)} organisations -> {args.index}")
        return
    profiles = read_jsonl(Path(args.profiles))
    index_rows = read_jsonl(Path(args.index)) if Path(args.index).exists() else []
    index = {str(r["organisation_number"]): r for r in index_rows}
    run_connector(profiles, index, Path(args.output), Path(args.report))


if __name__ == "__main__":
    main()
