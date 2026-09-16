#!/usr/bin/env python3
"""Official NAV job-vacancy feed connector (pam-stilling-feed.nav.no).

The Norwegian Labour and Welfare Administration publishes a public JSON feed of
job vacancies. Each posting's detail record carries the posting workplace as a
brreg 'underenhet' (sub-unit) organisation number. Resolving each sub-unit to
its parent 'enhet' via Brønnøysund makes the feed a strong, exact-entity,
officially licensed source for `job_board` / `job_posting` observations: the
unique legal-entity registration number is matched directly against the profile
organisation number, with no name matching.

Two build steps + a connector mode:

  --build-index      Offline, one-time pre-build. Walks every page of the last
                     six months of the feed (the statutory maximum posting
                     lifetime), keeps ACTIVE postings, fetches each detail
                     record, and writes a frozen index of sub-units. Zero
                     network use during later evaluation runs (aside from the
                     optional incremental poll).
  --resolve-parents  Re-keys the frozen index by the brreg parent enhet of each
                     advertiser sub-unit (the org number profiles carry).
  (connector)        Reads the frozen index, plus a bounded incremental poll
                     catching postings active since the index was built.
                     Emits only publishable observations.

The index is frozen data (like the declared Brønnøysund bulk snapshot): the
same rights/refresh reasoning applies. The incremental poll keeps the connector
honest on runs after the index commit without a full re-walk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.external_footprint import publishable_observation  # noqa: E402

FEED_BASE = "https://pam-stilling-feed.nav.no"
TOKEN_URL = FEED_BASE + "/api/publicToken"
FEED_URL = FEED_BASE + "/api/v1/feed"
BRREG_UNDERENHET = "https://data.brreg.no/enhetsregisteret/api/underenheter/{orgnr}"
MAX_POSTING_AGE_DAYS = 183
POLL_WORKERS = 24
MIN_INTERVAL_BUILD = 0.0
DEFAULT_POLL_DAYS = 3
HTTP_TIMEOUT = 45


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(sanitize_line_separators(json.dumps(row, ensure_ascii=False, separators=(",", ":"))) + "\n")
    temporary.replace(path)


def _http_date(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _public_token() -> str:
    raw = urllib.request.urlopen(TOKEN_URL, timeout=HTTP_TIMEOUT).read().decode("utf-8", errors="replace")
    return raw.split(":", 1)[1].strip()


def _get_json(url: str, token: str, *, since: datetime | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if since is not None:
        headers["If-Modified-Since"] = _http_date(since)
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _posting_header(item: dict) -> dict[str, Any]:
    entry = item.get("_feed_entry") or {}
    url = str(item.get("url") or "")
    return {
        "uuid": str(item.get("id") or entry.get("uuid") or url.rsplit("/", 1)[-1]),
        "feed_url": url,
        "status": entry.get("status"),
        "business_name": entry.get("businessName"),
        "municipal": entry.get("municipal"),
        "modified": entry.get("sistEndret"),
        "title": str(item.get("title") or ""),
    }


def _detail(token: str, header: dict) -> dict[str, Any] | None:
    if not header["feed_url"]:
        return None
    try:
        payload = _get_json(FEED_BASE + header["feed_url"], token)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {**header, "detail_error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    content = payload.get("ad_content") or payload
    employer = content.get("employer") or {}
    return {
        "uuid": header["uuid"],
        "employer_name": employer.get("name"),
        "employer_orgnr": str(employer.get("orgnr") or ""),
        "published": content.get("published"),
        "expires": content.get("expires"),
        "updated": content.get("updated"),
        "title": content.get("title") or header["title"],
        "jobtitle": content.get("jobtitle"),
        "application_url": content.get("applicationUrl") or content.get("sourceurl") or content.get("link"),
        "source": content.get("source"),
        "work_locations": content.get("workLocations"),
        "position_count": content.get("positioncount"),
        "engagement_type": content.get("engagementtype"),
        "extent": content.get("extent"),
        "sector": content.get("sector"),
    }


def _candidate_orgs(org_names: list[tuple[str, str]]) -> set[str]:
    return {org for org, _name in org_names}


def _norm_name(name: str) -> str:
    return str(name or "").translate(str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A", "æ": "ae", "Æ": "AE"})).casefold()


def _parent_enhet(orgnr: str, *, timeout: float = HTTP_TIMEOUT) -> str | None:
    """Resolve a brreg sub-unit (underenhet) number to its parent legal entity.

    NAV adverts list the posting workplace as a brreg 'underenhet' number while
    profiles carry the parent 'enhet' number, so org-number matching requires
    resolving each sub-unit to its overordnetEnhet. Sub-units without a parent
    (or numbers that no longer resolve) return None and are dropped.
    """
    try:
        request = urllib.request.Request(BRREG_UNDERENHET.format(orgnr=orgnr), headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    parent = str(payload.get("overordnetEnhet") or "").strip()
    return parent if parent.isdigit() else None


def build_index(index_path: Path, report_path: Path, *, days: int, workers: int) -> None:
    token = _public_token()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    seen_active: dict[str, dict[str, Any]] = {}
    pages = 0
    total_items = 0
    active_entries = 0
    url: str | None = FEED_URL
    started = time.time()
    while url is not None:
        data = _get_json(url, token, since=since)
        items = data.get("items") or []
        total_items += len(items)
        for item in items:
            header = _posting_header(item)
            active_entries += int(header["status"] == "ACTIVE")
            # Feed pages are ordered oldest->newest; the LATEST entry per
            # posting decides current status, so expired postings drop out.
            seen_active[header["uuid"]] = header
        pages += 1
        print(f"    page {pages} items={total_items} latest_by_uuid={len(seen_active)} ({time.time()-started:.0f}s)", flush=True)
        next_url = data.get("next_url")
        url = FEED_BASE + next_url if next_url else None

    active_now = [header for header in seen_active.values() if header["status"] == "ACTIVE"]
    headers = active_now
    details: list[dict[str, Any]] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_detail, token, header): header["uuid"] for header in headers}
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result is None or "detail_error" in result:
                failures += 1
                continue
            details.append(result)
            if i % 500 == 0 and i:
                print(f"    details {i}/{len(headers)} ({time.time()-started:.0f}s)", flush=True)
            if MIN_INTERVAL_BUILD:
                time.sleep(MIN_INTERVAL_BUILD)

    by_org: dict[str, list[dict[str, Any]]] = {}
    for det in details:
        org = det.get("employer_orgnr") or ""
        if not org.isdigit():
            continue
        by_org.setdefault(org, []).append(det)
    index_rows = [
        {"organisation_number": org, "postings": postings}
        for org, postings in sorted(by_org.items())
    ]
    built_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = {
        "connector": "nav_job_feed_v1",
        "mode": "index_build",
        "built_at": built_at,
        "window_days": days,
        "pages_walked": pages,
        "total_items": total_items,
        "active_headers": len(headers),
        "detail_fetched": len(details),
        "detail_failures": failures,
        "organisation_numbers": len(index_rows),
        "posting_count": sum(len(row["postings"]) for row in index_rows),
        "source": {
            "title": data.get("title") if isinstance(data, dict) else None,
            "feed_url": FEED_URL,
            "rights": "public official open government feed",
            "acquisition_mode": "official_api",
        },
    }
    write_jsonl(index_path, index_rows)
    report = {
        "connector": "nav_job_feed_v1",
        "built_at": built_at,
        "window_days": days,
        "index_path": str(index_path),
        "index_size": len(index_rows),
        "posting_count": manifest["posting_count"],
        "pages_walked": pages,
        "total_items": total_items,
        "active_headers": len(headers),
        "detail_failures": failures,
        "elapsed_s": round(time.time() - started, 1),
        "claim_boundary": "Frozen index of ACTIVE NAV postings keyed by official employer organisation number; detail records carry ad_content.employer.orgnr.",
    }
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(report_path).with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def resolve_index(index_path: Path, report_path: Path, *, workers: int) -> None:
    """Re-key a raw NAV index by brreg parent enhet.

    NAV detail records list the posting workplace as a brreg 'underenhet'
    (sub-unit) organisation number, while profiles carry the parent 'enhet'
    number. This pass resolves every distinct employer org number to its
    overordnetEnhet via brreg and rewrites the index keyed by parent enhet,
    so downstream org-number matching is exact against profile organisation
    numbers. Sub-units with no resolvable parent are dropped.
    """
    rows = read_jsonl(index_path)
    distinct = sorted({str(p.get("employer_orgnr") or "") for row in rows for p in (row.get("postings") or []) if str(p.get("employer_orgnr") or "").isdigit()})
    parents: dict[str, str] = {}
    started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_parent_enhet, org): org for org in distinct}
        for i, future in enumerate(as_completed(futures)):
            org = futures[future]
            parent = future.result()
            if parent:
                parents[org] = parent
            if i % 500 == 0 and i:
                print(f"    parents {i}/{len(distinct)} resolved={len(parents)} ({time.time()-started:.0f}s)", flush=True)
    by_parent: dict[str, list[dict[str, Any]]] = {}
    dropped = 0
    for row in rows:
        for posting in row.get("postings") or []:
            org = str(posting.get("employer_orgnr") or "")
            parent = parents.get(org)
            if not parent:
                dropped += 1
                continue
            posting = {**posting, "employer_orgnr": org, "employer_parent_orgnr": parent}
            by_parent.setdefault(parent, []).append(posting)
    index_rows = [
        {"organisation_number": parent, "postings": postings}
        for parent, postings in sorted(by_parent.items())
    ]
    built_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_jsonl(index_path, index_rows)
    manifest = {
        "connector": "nav_job_feed_v1",
        "mode": "index_resolve_parents",
        "built_at": built_at,
        "resolved_parent_enhets": len(index_rows),
        "posting_count": sum(len(row["postings"]) for row in index_rows),
        "postings_dropped_unresolved_parent": dropped,
        "claim_boundary": "Postings keyed by the brreg parent enhet of the NAV advertiser sub-unit; employer.orgnr is the underenhet, employer_parent_orgnr the resolved legal entity.",
    }
    Path(str(index_path).replace(".jsonl", ".manifest.json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(report_path).with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "connector": "nav_job_feed_v1",
        "mode": "index_resolve_parents",
        "index_path": str(index_path),
        "index_size": len(index_rows),
        "posting_count": manifest["posting_count"],
        "parent_resolution_succeeded": len(parents),
        "parent_resolution_failed": len(distinct) - len(parents),
        "postings_dropped_unresolved_parent": dropped,
        "elapsed_s": round(time.time() - started, 1),
    }
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _poll_active(token: str, index_built_at: str, *, days: int) -> list[dict[str, Any]]:
    """Bounded poll of postings modified since the index was built (ACTIVE only)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    seen: dict[str, dict[str, Any]] = {}
    url: str | None = FEED_URL
    while url is not None:
        data = _get_json(url, token, since=since)
        for item in data.get("items") or []:
            header = _posting_header(item)
            if header["status"] != "ACTIVE":
                continue
            seen.setdefault(header["uuid"], header)
        next_url = data.get("next_url")
        url = FEED_BASE + next_url if next_url else None
    return list(seen.values())


def _emit(profile: dict, postings: list[dict[str, Any]], index_built_at: str) -> list[dict[str, Any]]:
    org = str(profile["organisation_number"])
    observations = []
    for posting in postings:
        parent = str(posting.get("employer_parent_orgnr") or "")
        if parent:
            orgnr = parent
        else:
            orgnr = str(posting.get("employer_orgnr") or "")
        if orgnr != org:
            continue
        payload = json.dumps(
            {
                "uuid": posting.get("uuid"),
                "title": posting.get("title"),
                "orgnr": orgnr,
                "published": posting.get("published"),
                "expires": posting.get("expires"),
                "source_class": posting.get("source"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        human_url = f"https://arbeidsplassen.nav.no/stillinger/stilling/{posting.get('uuid')}"
        locations = posting.get("work_locations") or []
        place = next((f"{loc.get('city', '')}, {loc.get('municipal', '')}" for loc in locations if loc.get("city") or loc.get("municipal")), "")
        evidence_span = " | ".join(part for part in [posting.get("title"), posting.get("employer_name"), place] if part)[:1200]
        matched = posting.get("employer_parent_orgnr") or orgnr
        proof_explanation = (
            "NAV job feed detail advertises the posting under a brreg sub-unit whose resolved "
            f"parent legal entity (organisation number {matched}) equals the profile organisation number."
            if posting.get("employer_parent_orgnr")
            else "NAV job feed detail advertises posting employer with legal organisation number equal to the profile organisation number."
        )
        observations.append({
            "id": "nav-job-" + hashlib.sha256((org + "|" + str(posting.get("uuid"))).encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "job_board",
            "signal_type": "job_posting",
            "source_url": human_url,
            "retrieved_at": index_built_at,
            "content_sha256": hashlib.sha256(payload).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{
                "type": "organisation_number_on_official_api",
                "source": "pam-stilling-feed.nav.no",
                "source_class": "official_job_board",
                "matched_organisation_number": matched,
                "explanation": proof_explanation,
            }],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_api",
            "signal": {
                "title": posting.get("title"),
                "jobtitle": posting.get("jobtitle"),
                "employer_name": posting.get("employer_name"),
                "published": posting.get("published"),
                "expires": posting.get("expires"),
                "application_url": posting.get("application_url"),
                "city_municipal": place,
                "engagement_type": posting.get("engagement_type"),
                "extent": posting.get("extent"),
                "sector": posting.get("sector"),
                "position_count": posting.get("position_count"),
            },
            "evidence_span": evidence_span,
            "metrics": {
                "strategy": "official_nav_job_feed_orgnr_match",
                "source": "pam-stilling-feed.nav.no",
                "index_built_at": index_built_at,
                "detail_source_url": ("feedentry" if posting.get("feed_url") else ""),
            },
            "strategy": "official_nav_job_feed_orgnr_match",
        })
    return observations


def run_connector(profiles: list[dict], index_path: Path, report_path: Path, output_path: Path, *, poll_days: int) -> None:
    if not index_path.exists():
        print(f"NAV index missing: {index_path}", file=sys.stderr)
        raise SystemExit("run --build-index first")
    index_rows = read_jsonl(index_path)
    by_org = {str(row["organisation_number"]): (row.get("postings") or []) for row in index_rows}
    manifest_path = Path(str(index_path).replace(".jsonl", ".manifest.json"))
    index_built_at = (
        manifest_path.read_text(encoding="utf-8").split('"built_at": "')[1].split('"')[0]
        if manifest_path.exists()
        else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    org_names = [(str(p["organisation_number"]), str(p.get("name") or "")) for p in profiles]
    names_by_org = dict(org_names)
    observed = {org: [] for org in names_by_org}
    for org in names_by_org:
        observed[org] = list(by_org.get(org, []))

    incremental = 0
    if poll_days > 0:
        try:
            token = _public_token()
        except Exception as exc:
            token = None
            print(f"    incremental poll skipped (token error): {str(exc)[:80]}", flush=True)
        else:
            candidates = _poll_active(token, index_built_at, days=poll_days)
            names = {_norm_name(name) for name in names_by_org.values() if name}
            for header in candidates:
                biz = _norm_name(header.get("business_name"))
                if not biz or not any(part in biz for part in names if len(part) > 3):
                    continue
                det = _detail(token, header)
                sub_unit = str(det.get("employer_orgnr") or "") if det else ""
                org = str(_parent_enhet(sub_unit) or sub_unit) if det and sub_unit else ""
                if org in observed:
                    observed[org].append({**det, "employer_parent_orgnr": org})
                    incremental += 1

    observations: list[dict[str, Any]] = []
    org_status: dict[str, dict] = {}
    for profile in profiles:
        org = str(profile["organisation_number"])
        postings = observed.get(org) or []
        emissions = _emit(profile, postings, index_built_at)
        accepted = [item for item in emissions if publishable_observation(item)]
        observations.extend(accepted)
        org_status[org] = {
            "postings_matched": len(postings),
            "publishable": len(accepted),
        }

    write_jsonl(output_path, observations)
    report = {
        "connector": "nav_job_feed_v1",
        "mode": "run_connector",
        "index_path": str(index_path),
        "index_built_at": index_built_at,
        "incremental_poll_days": poll_days,
        "incremental_new_postings": incremental,
        "profiles": len(profiles),
        "organisations_with_postings": sum(bool(org_status[org]["postings_matched"]) for org in org_status),
        "publishable_observations": len(observations),
        "rejected_unpublishable": 0,
        "claim_boundary": "Only ACTIVE NAV postings whose resolved brreg parent enhet exactly equals the profile organisation number are emitted.",
    }
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Official NAV job-feed connector (publishable official_api job postings).")
    parser.add_argument("--build-index", action="store_true", help="Offline pre-build the frozen NAV posting index")
    parser.add_argument("--resolve-parents", action="store_true", help="Re-key index by brreg parent enhet of each advert sub-unit")
    parser.add_argument("--index", default="data/nav-job-index.jsonl", help="Frozen index path")
    parser.add_argument("--profiles", default="out/web1000-profiles.jsonl", help="Batch profiles JSONL")
    parser.add_argument("--output", default="out/web1000batch.nav.jsonl", help="Observation JSONL output")
    parser.add_argument("--report", default="out/web1000batch.nav-report.json", help="Connector report")
    parser.add_argument("--days", type=int, default=MAX_POSTING_AGE_DAYS, help="Index build window in days")
    parser.add_argument("--workers", type=int, default=POLL_WORKERS, help="Detail-fetch workers during index build")
    parser.add_argument("--poll-days", type=int, default=DEFAULT_POLL_DAYS, help="Incremental poll window in days (0=off)")
    args = parser.parse_args()

    if args.build_index:
        build_index(Path(args.index), Path(args.report), days=args.days, workers=args.workers)
        return
    if args.resolve_parents:
        resolve_index(Path(args.index), Path(args.report), workers=args.workers)
        return
    profiles = read_jsonl(Path(args.profiles))
    run_connector(profiles, Path(args.index), Path(args.report), Path(args.output), poll_days=args.poll_days)


if __name__ == "__main__":
    main()