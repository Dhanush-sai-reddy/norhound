#!/usr/bin/env python3
"""Mattilsynet smilefjes food-hygiene inspection ratings.

Downloads https://smilefjes.mattilsynet.no/search/index/nb.json once per run,
matches places by company postcode + name token, fetches the place page, and
publishes only when the page's Orgnr. matches the company's organisation number.

Adapted from noneedofit/provenance activity/smilefjes.py (competitor repo).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
import urllib.error
from html import unescape
from pathlib import Path
from datetime import datetime, timezone


BASE_URL = "https://smilefjes.mattilsynet.no"
INDEX_URL = BASE_URL + "/search/index/nb.json"
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
MAX_PAGES = 3

_STOP = {"as", "asa", "da", "ans", "sa", "enk", "nuf", "avd", "og", "the", "i", "pa", "cafe", "kafe", "restaurant",
         "pizza", "sushi", "bar", "kro", "grill", "bakeri", "kafeteria", "kantine"}


def _tokens(name: str) -> set[str]:
    folded = (name or "").lower()
    return {t for t in re.findall(r"[a-z0-9]+", folded) if len(t) >= 3 and t not in _STOP}


def _fetch_index(timeout: float = 30.0) -> list[list] | None:
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except Exception:
        return None
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    lookup = data.get("lookup") or [] if isinstance(data, dict) else []
    return [row for row in lookup if isinstance(row, list) and len(row) >= 7 and row[4]]


def _visible_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", html)
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))).strip()


_ORGNR_RE = re.compile(r"Orgnr\.?\s*(\d{3}\s?\d{3}\s?\d{3})")
_LATEST_RE = re.compile(r"Siste tilsynsresultat:\s*</h2>\s*<div[^>]*title=[\"']([^\"']+)[\"']", re.S)
_LATEST_DATE_RE = re.compile(r"Siste tilsynsresultat:\s*(\d{2}\.\d{2}\.\d{4})")
_SMILEY_WORDS = (
    ("blidt smilefjes", "smiling face (no breaches found)"),
    ("strekmunn", "straight mouth (breaches that require follow-up)"),
    ("sur munn", "sad mouth (serious breaches)"),
)


def observations_for_org(org: str, name: str, postcode: str | None,
                         subunits: list[dict], index: list[list], timeout: float = 15.0) -> list[dict]:
    observations = []
    wanted = _tokens(name) | _tokens(postcode or "")
    candidates = {}
    for row in index:
        row_postcode = str(row[4]) if row[4] else ""
        if row_postcode != str(postcode or ""):
            continue
        row_name_tokens = _tokens(row[1]) if row[1] else set()
        if wanted and not (row_name_tokens & wanted):
            continue
        candidates.setdefault(row[0], row)

    our_orgs = {org}
    for s in subunits or []:
        if s.get("organisation_number"):
            our_orgs.add(str(s["organisation_number"]))

    count = 0
    for path, row in sorted(candidates.items()):
        if count >= MAX_PAGES:
            break
        url = BASE_URL + str(path)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                page = resp.read().decode("utf-8", errors="replace")
                final_url = resp.geturl()
                status = resp.status
        except Exception:
            continue

        text = _visible_text(page)
        m = _ORGNR_RE.search(text)
        if not m:
            continue
        page_org = re.sub(r"\D", "", m.group(1))
        if page_org not in our_orgs:
            continue

        latest_title_m = _LATEST_RE.search(page)
        latest_date_m = _LATEST_DATE_RE.search(text)
        if not latest_title_m or not latest_date_m:
            continue

        smiley_text = unescape(latest_title_m.group(1))
        smiley = next((label for word, label in _SMILEY_WORDS if word in smiley_text.casefold()), None)
        if smiley is None:
            continue

        day, month, year = latest_date_m.group(1).split(".")
        inspected = f"{year}-{month}-{day}"

        history = row[6] if isinstance(row[6], list) else []
        index_grade = str(history[0][0]) if history and history[0] else None
        index_date = str(history[0][1]) if history and len(history[0]) > 1 else None
        grade_code = int(index_grade) if index_grade and index_date == inspected else None
        grade_map = {"0": "smiling face (no breaches found)", "1": "smiling face (minor breaches, no follow-up needed)",
                     "2": "straight mouth (breaches that require follow-up)", "3": "sad mouth (serious breaches)"}
        grade = grade_map.get(index_grade, smiley) if grade_code is not None else smiley

        quote_parts = [f"{row[1]} Orgnr. {page_org}", f"Siste tilsynsresultat: {latest_date_m.group(1)}", smiley_text]
        span = " — ".join(quote_parts)[:500]
        digest_input = f"{org}|{final_url}|{inspected}".encode()
        digest = hashlib.sha256(digest_input).hexdigest()
        retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        obs = {
            "id": "smilefjes-" + hashlib.sha256(f"{org}|{row[0]}|{inspected}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "mattilsynet",
            "signal_type": "inspection_rating",
            "source_url": final_url or url,
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": [{
                "type": "organisation_number_on_source",
                "source": "smilefjes.mattilsynet.no",
                "source_class": "official_inspection",
                "matched_organisation_number": page_org,
                "explanation": "Mattilsynet smilefjes page carries the exact organisation number.",
            }],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "official_inspection",
            "evidence_span": span,
            "effective_at": inspected,
            "metrics": {
                "rater": "Mattilsynet (Norwegian Food Safety Authority)",
                "scheme": "smilefjes food-hygiene inspection",
                "place": row[1] or "",
                "place_org_number": page_org,
                "grade_code": grade_code,
                "grade": grade,
                "inspected_on": inspected,
            },
            "strategy": "smilefjes_ratings",
        }
        observations.append(obs)
        count += 1
        time.sleep(0.3)

    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Mattilsynet smilefjes ratings connector.")
    parser.add_argument("--profiles", required=True, help="Frozen batch profiles JSONL")
    parser.add_argument("--output", required=True, help="Observations JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    index = _fetch_index(args.timeout)
    index_count = len(index) if index else 0

    observations = []
    statuses = {}

    for p in profiles:
        org = str(p["organisation_number"])
        name = p.get("name") or ""
        registry = (p.get("evidence") or {}).get("registry") or {}
        reg_value = registry.get("value") or {}
        postcode = str(reg_value.get("postnummer") or reg_value.get("postal_code") or "")
        subunits = reg_value.get("subunits") or []

        if not index:
            statuses[org] = "index_fetch_failed"
            continue

        obs = observations_for_org(org, name, postcode, subunits, index, args.timeout)
        observations.extend(obs)
        statuses[org] = f"ok:{len(obs)}"
        time.sleep(0.2)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations), encoding="utf-8"
    )

    accepted = sum(1 for s in statuses.values() if s.startswith("ok:"))
    report = {
        "connector": "smilefjes_ratings_v1",
        "profiles": len(profiles),
        "accepted": accepted,
        "observations": len(observations),
        "index_entries": index_count,
        "status_counts": {k: list(statuses.values()).count(k) for k in set(statuses.values())},
        "claim_boundary": "Mattilsynet smilefjes food-hygiene inspection ratings, exact org-number match on source page.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "status_counts"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
