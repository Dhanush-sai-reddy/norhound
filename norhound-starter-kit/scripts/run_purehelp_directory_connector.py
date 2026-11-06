#!/usr/bin/env python3
"""Keyless Purehelp directory connector (organisation-number keyed pages).

Purehelp publishes one public profile page per Norwegian organisation number
(``https://purehelp.no/company/NO/<orgnr>``). The page mirrors the public
registers (Enhetsregisteret, Foretaksregisteret, Regnskapsregisteret) and is
reachable without an API key, a login or a paid account.

Publication rules (same shape as the Fagfolkguiden directory path):

* the page payload states the requested 9-digit organisation number exactly,
  and
* the legal name on the page equals the BRREG legal name after legal-form
  normalisation (or differs only by a registry word such as ``SAMEIET``).

Every emitted row carries the source URL, the retrieval time, the SHA-256 of
the page body, the extraction method and the identity proof. Financial values
are deliberately **not** published from this directory: they come from the
official Brønnøysund accounts API instead, so no value is ever mirrored twice
or attributed to the wrong source class.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
BASE = "https://purehelp.no"
PAGE_URL_TEMPLATE = f"{BASE}/company/NO/{{org}}"
ROBOTS_NOTE = (
    "robots.txt allows /company/NO/; /api/, /admin, /account, /monitor, /alerts "
    "and /ai are disallowed and are never requested"
)
MAX_BYTES = 4_000_000
ORGANISATION_NUMBER_RE = re.compile(r"^\d{9}$")

# Legal forms that may sit as one trailing token of a registered name.
LEGAL_FORM_SUFFIXES = (
    "a/s", "ab", "ans", "aps", "asa", "as", "ba", "co", "corp", "da", "enk",
    "gmbh", "ag", "bv", "i/s", "inc", "k/s", "kf", "limited", "ltd", "llc",
    "llp", "lp", "nv", "oy", "oyj", "p/s", "plc", "reg", "sa", "sarl", "sp",
    "spa", "srl", "ug",
)
TRANSLITERATION = str.maketrans(
    {"ø": "o", "å": "a", "æ": "ae", "Ø": "O", "Å": "A", "Æ": "AE"}
)
# Registry words that a register may add in front of the trade name.
REGISTRY_NAME_PREFIXES = {"sameiet", "sameiete", "sameietet"}

NUXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S | re.I
)
NUXT_TAGS = {"ShallowReactive", "Reactive", "PlainReactive", "Ref", "ShallowRef", "Set", "Map", "Date", "NaN"}


# --------------------------------------------------------------------------- #
# Payload parsing
# --------------------------------------------------------------------------- #
def parse_nuxt_payload(html: str) -> dict | None:
    """Resolve a Nuxt SSR ``__NUXT_DATA__`` payload into plain Python objects.

    The payload is a flat devalue array: every value lives in one array and
    objects and lists reference their members by index.
    """
    match = NUXT_DATA_RE.search(str(html or ""))
    if not match:
        return None
    try:
        flat = json.loads(match.group(1))
    except (TypeError, ValueError):
        return None
    if not isinstance(flat, list) or not flat:
        return None

    def resolve(index: int, depth: int = 0) -> object:
        if depth > 32:
            return None
        if not isinstance(index, int) or index < 0 or index >= len(flat):
            return None
        value = flat[index]
        if isinstance(value, dict):
            return {key: resolve(item, depth + 1) for key, item in value.items()}
        if isinstance(value, list):
            if not value:
                return []
            head = value[0]
            if isinstance(head, str) and head in NUXT_TAGS and len(value) > 1:
                return resolve(value[1], depth + 1)
            return [resolve(item, depth + 1) for item in value]
        return value

    root = resolve(0)
    return root if isinstance(root, dict) else None


def company_payload(html: str, organisation_number: str) -> dict | None:
    """The company record of the requested organisation, or None."""
    root = parse_nuxt_payload(html)
    if not root:
        return None
    data = root.get("data")
    if not isinstance(data, dict):
        return None
    record = data.get(f"company-NO-{organisation_number}")
    return record if isinstance(record, dict) else None


# --------------------------------------------------------------------------- #
# Name handling
# --------------------------------------------------------------------------- #
def normalize_legal_name(value: object) -> str:
    """Transliterate, lowercase and drop one trailing legal-form token."""
    text = str(value or "").casefold().translate(TRANSLITERATION)
    text = re.sub(r"\s+", " ", text).strip()
    for form in LEGAL_FORM_SUFFIXES:
        if text == form:
            candidate = ""
        elif text.endswith(" " + form):
            candidate = text[: -len(form)].strip()
        else:
            continue
        if candidate:
            text = candidate
        break
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def legal_name_matches(profile_name: object, page_name: object) -> bool:
    """True when both names describe the same registered entity.

    The exact match is the normal case. A register may prefix a trade name
    with ``SAMEIET`` (housing associations), so a name pair also matches when
    one token set is the other plus a registry word.
    """
    expected = normalize_legal_name(profile_name)
    actual = normalize_legal_name(page_name)
    if not expected or not actual:
        return False
    if expected == actual:
        return True
    expected_tokens = expected.split()
    actual_tokens = actual.split()
    if set(expected_tokens) <= set(actual_tokens):
        difference = set(actual_tokens) - set(expected_tokens)
        return bool(difference) and difference <= REGISTRY_NAME_PREFIXES
    if set(actual_tokens) <= set(expected_tokens):
        difference = set(expected_tokens) - set(actual_tokens)
        return bool(difference) and difference <= REGISTRY_NAME_PREFIXES
    return False


# --------------------------------------------------------------------------- #
# Observations
# --------------------------------------------------------------------------- #
def _date_part(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split("T", 1)[0].strip()


def _evidence_span(payload: dict, organisation_number: str) -> str:
    """A compact, checkable description of where the fact was read."""
    return (
        f"nuxt:company-NO-{organisation_number}.orgNumber={payload.get('orgNumber')}"
        f";name={payload.get('name')}"
    )


def build_observations(
    organisation_number: str,
    profile_name: str,
    payload: dict,
    source_url: str,
    raw: bytes,
    retrieved_at: str,
) -> list[dict]:
    """The directory rows for one identity-proved Purehelp page."""
    content_digest = hashlib.sha256(raw).hexdigest()
    url_digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]
    proof = [
        {"type": "exact_organisation_number_on_directory_page", "value": organisation_number},
        {
            "type": "exact_legal_name_on_directory_page",
            "value": str(payload.get("name") or ""),
            "matched_organisation_number": organisation_number,
        },
    ]
    common = {
        "organisation_number": organisation_number,
        "platform": "company_directory",
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "content_sha256": content_digest,
        "exact_entity": True,
        "identity_proof": proof,
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_directory",
        "extraction_method": "nuxt_ssr_payload_company_record",
        "evidence_span": _evidence_span(payload, organisation_number),
    }

    rows: list[dict] = [
        {
            **common,
            "id": f"purehelp-profile-{organisation_number}-{url_digest}",
            "signal_type": "profile_metrics",
            "strategy": "purehelp_directory_profile",
            "metrics": {
                "legal_form": payload.get("legalForm"),
                "legal_form_description": payload.get("legalFormDescription"),
                "nace_code": payload.get("naceCode"),
                "nace_description": payload.get("naceDescriptionEng"),
                "town": payload.get("town"),
                "zipcode": payload.get("zipcode"),
                "municipality": payload.get("municipality"),
                "municipality_number": payload.get("municipalityNumber"),
                "county": payload.get("county"),
                "registration_date": _date_part(payload.get("registrationDate")),
                "registry_status": payload.get("registryStatus"),
                "registry_status_date": _date_part(payload.get("registryStatusDate")),
                "deregistration_date": _date_part(payload.get("deregistrationDate")),
                "is_active": payload.get("isActive"),
                "is_bankrupt": payload.get("isBankrupt"),
                "bankruptcy_date": _date_part(payload.get("bankruptcyDate")),
                "website_domain": payload.get("website"),
            },
        },
    ]

    employees = payload.get("employees")
    if isinstance(employees, int) and not isinstance(employees, bool) and employees >= 0:
        rows.append(
            {
                **common,
                "id": f"purehelp-workforce-{organisation_number}-{url_digest}",
                "signal_type": "workforce_snapshot",
                "strategy": "purehelp_directory_workforce",
                "metrics": {
                    "employees": employees,
                    "as_of": _date_part(payload.get("employeesAsOf")),
                    "employees_source": payload.get("employeesSource"),
                    "interpretation": "Employee count published by the directory; no value is inferred.",
                },
            }
        )

    email = str(payload.get("email") or "").strip()
    if email:
        rows.append(
            {
                **common,
                "id": f"purehelp-email-{organisation_number}-{url_digest}",
                "signal_type": "contact_email",
                "strategy": "purehelp_directory_contact",
                "metrics": {
                    "email": email,
                    "contact_as_of": _date_part(payload.get("contactAsOf")),
                },
            }
        )

    phone = str(payload.get("phone") or "").strip()
    if phone:
        rows.append(
            {
                **common,
                "id": f"purehelp-phone-{organisation_number}-{url_digest}",
                "signal_type": "contact_phone",
                "strategy": "purehelp_directory_contact",
                "metrics": {
                    "phone": phone,
                    "contact_as_of": _date_part(payload.get("contactAsOf")),
                },
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Fetching and running
# --------------------------------------------------------------------------- #
def http_fetch(url: str, timeout: int = 30) -> tuple[bytes, str]:
    """Fetch a public page; returns the body and the URL actually retrieved."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES)
        final_url = response.geturl() if hasattr(response, "geturl") else url
    return body, final_url


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_from_mtime(path: Path) -> str:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return stamp.isoformat().replace("+00:00", "Z")


def process_organisation(
    organisation_number: str,
    profile: dict,
    cache_dir: Path,
    *,
    offline: bool,
    fetcher,
) -> tuple[list[dict], dict]:
    """Read (or fetch) one company page and publish its rows."""
    cache_path = Path(cache_dir) / f"{organisation_number}.html"
    page_url = PAGE_URL_TEMPLATE.format(org=organisation_number)
    status: dict = {"organisation_number": organisation_number, "accepted": False}
    if offline:
        if not cache_path.exists():
            status["reason"] = "page_cache_miss"
            status["requested_url"] = page_url
            return [], status
        raw = cache_path.read_bytes()
        retrieved_at = _iso_from_mtime(cache_path)
        status["cache_hit"] = True
    else:
        try:
            raw, final_url = fetcher(page_url)
        except urllib.error.HTTPError as exc:
            status["reason"] = "no_listing" if exc.code in (404, 410) else "page_fetch_error"
            status["error"] = f"HTTP {exc.code}"
            status["requested_url"] = page_url
            return [], status
        except Exception as exc:  # pragma: no cover - network failure path
            status["reason"] = "page_fetch_error"
            status["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            status["requested_url"] = page_url
            return [], status
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw)
        except OSError as exc:  # pragma: no cover - disk failure path
            status["cache_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        retrieved_at = _now_iso()
        status["cache_hit"] = False
        status["final_url"] = final_url

    html = raw.decode("utf-8", errors="replace")
    payload = company_payload(html, organisation_number)
    if payload is None:
        status["reason"] = "no_company_payload"
        status["requested_url"] = page_url
        return [], status

    page_org = str(payload.get("orgNumber") or "").strip()
    status["page_organisation_number"] = page_org
    status["page_name"] = str(payload.get("name") or "")
    if page_org != organisation_number:
        status["reason"] = "org_number_mismatch"
        return [], status

    expected_name = str((profile or {}).get("name") or "").strip()
    if not expected_name:
        status["reason"] = "profile_name_missing"
        return [], status
    if not legal_name_matches(expected_name, payload.get("name")):
        status["reason"] = "legal_name_mismatch"
        status["profile_name"] = expected_name
        return [], status

    rows = build_observations(
        organisation_number, expected_name, payload, page_url, raw, retrieved_at
    )
    status["accepted"] = True
    status["page_url"] = page_url
    status["signals"] = sorted({row["signal_type"] for row in rows})
    return rows, status


def run_connector(
    *,
    profiles: dict[str, dict],
    wanted: list[str],
    cache_dir: Path,
    offline: bool = False,
    workers: int = 4,
    fetcher=None,
    timeout: int = 30,
    min_interval: float = 0.0,
) -> tuple[list[dict], dict]:
    """Run the connector over the requested organisations."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetcher or (lambda url: http_fetch(url, timeout))

    organisations: list[str] = []
    for org in wanted:
        org = str(org).strip()
        if org and org not in organisations:
            organisations.append(org)

    def work(org: str) -> tuple[list[dict], dict]:
        if min_interval > 0 and not offline:
            time.sleep(min_interval)
        return process_organisation(
            org,
            (profiles or {}).get(org, {}),
            cache_dir,
            offline=offline,
            fetcher=fetch,
        )

    rows: list[dict] = []
    statuses: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers or 1), 8))) as pool:
        for org_rows, org_status in pool.map(work, organisations):
            rows.extend(org_rows)
            statuses.append(org_status)

    order = {org: index for index, org in enumerate(organisations)}
    rows.sort(key=lambda row: (order.get(row["organisation_number"], 0), row["signal_type"]))
    statuses.sort(key=lambda row: order.get(row["organisation_number"], 0))

    rejected_by_reason: dict[str, int] = {}
    for status in statuses:
        if status.get("accepted"):
            continue
        reason = str(status.get("reason") or "unknown")
        rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
    signal_counts: dict[str, int] = {}
    for row in rows:
        signal = str(row.get("signal_type") or "")
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
    accepted = sum(1 for status in statuses if status.get("accepted"))
    report = {
        "connector": "purehelp_directory_orgnr_v1",
        "offline": bool(offline),
        "orgs_requested": len(organisations),
        "orgs_accepted": accepted,
        "orgs_rejected": len(organisations) - accepted,
        "rejected_by_reason": rejected_by_reason,
        "observations": len(rows),
        "observations_by_signal_type": signal_counts,
        "robots_note": ROBOTS_NOTE,
        "rights_note": (
            "Public directory profile pages; robots.txt permits /company/NO/. "
            "Values are directory-sourced, never presented as official register output."
        ),
        "financials_note": "No financial value is published from this source.",
        "company_results": statuses,
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exact-entity Purehelp directory rows from organisation-number pages."
    )
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--organisations", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--offline", action="store_true", help="Use cached pages only; never touch the network")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--min-interval", type=float, default=0.2, help="Seconds between page requests")
    args = parser.parse_args()

    wanted = [
        line.strip()
        for line in Path(args.organisations).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    profiles = {
        str(row["organisation_number"]): row
        for row in (
            json.loads(line)
            for line in Path(args.profiles).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if str(row.get("organisation_number") or "").strip()
    }
    rows, report = run_connector(
        profiles=profiles,
        wanted=wanted,
        cache_dir=Path(args.cache),
        offline=args.offline,
        workers=args.workers,
        timeout=args.timeout,
        min_interval=args.min_interval,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "connector", "orgs_requested", "orgs_accepted", "orgs_rejected",
        "observations", "observations_by_signal_type", "rejected_by_reason",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
