#!/usr/bin/env python3
"""Attach material changes to a refresh run.

The official brief requires every terminal envelope to carry "refresh metadata
and material changes since the previous run", and the official-run integrity
check requires "idempotent refresh with prior snapshots preserved":

  https://builderr.ai/starter-briefs/signalpost.md  (retrieved 2026-11-17)

This stage is the last step of the official-batch command. It compares the
current envelopes against the previous run's envelopes and writes:

  * `changes`     — typed old -> new records for every material difference,
                    with the source URL, retrieval time, effective date and
                    the content hash of both the old and the new value;
  * `refresh`     — the previous run id, whether the company is a baseline,
                    and how many changes were detected versus preserved;
  * preserved evidence — the evidence record behind a historical change is
                    kept even when the current run no longer carries it, so
                    earlier evidence is not silently dropped.

It is idempotent. Re-running it over the same current envelopes and the same
previous envelopes produces byte-identical output, and re-running it over its
own output produces the same result again: change records are keyed by a
content hash of (field, old value, new value, new content hash), so a change
that is already recorded is not recorded twice.

The comparison never mutates the input files unless --output is the input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.refresh import diff_profile  # noqa: E402

# Values that are lists of objects are compared as sets of stable strings, so
# a reordered list is not a material change.
MAX_VALUES_IN_RECORD = 50


def read_jsonl(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(
                json.loads(line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
            )
    return rows


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def stable_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def claim_map(envelope: dict) -> dict[str, dict[str, dict]]:
    """Group the claims of an envelope by field, then by stable value.

    A field can carry many claims (every role holder, every dated news item),
    so a field is compared as the set of values it holds rather than as one
    value. A set that gained or lost a member, or a member whose availability
    changed, is a material change.
    """
    grouped: dict[str, dict[str, dict]] = {}
    for claim in envelope.get("claims") or []:
        field = str(claim.get("field") or "")
        if not field:
            continue
        key = stable_value(claim.get("value"))
        bucket = grouped.setdefault(field, {})
        if key in bucket:
            # Keep the first record for a value; it is the one whose evidence
            # is quoted. A later duplicate of the same value adds nothing.
            continue
        bucket[key] = {
            "value": claim.get("value"),
            "availability": claim.get("availability"),
            "evidence_id": (claim.get("evidence_ids") or [None])[0],
        }
    return grouped


def evidence_index(envelope: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for record in envelope.get("evidence") or []:
        key = str(record.get("id") or "")
        if key:
            index[key] = record
    return index


def _quote(values: list[Any]) -> Any:
    if len(values) == 1:
        return values[0]
    return values[:MAX_VALUES_IN_RECORD]


def _evidence_facts(
    envelope: dict, evidence_id: str | None
) -> dict[str, Any]:
    if not evidence_id:
        return {}
    record = evidence_index(envelope).get(str(evidence_id))
    if not record:
        return {}
    return {
        "source_url": record.get("source_url"),
        "retrieved_at": record.get("retrieved_at"),
        "effective_at": record.get("effective_at") or record.get("as_of"),
        "source_class": record.get("source_class"),
        "content_sha256": record.get("content_sha256"),
    }


def _change_id(record: dict) -> str:
    payload = "|".join(
        [
            str(record.get("organisation_number") or ""),
            str(record.get("field") or ""),
            str(record.get("change_type") or ""),
            stable_value(record.get("old_value")),
            stable_value(record.get("new_value")),
            str(record.get("new_content_sha256") or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def diff_claims(
    previous: dict, current: dict, detected_at: str, previous_run_id: str | None
) -> list[dict]:
    """Material claim changes between two envelopes for one company."""
    old_claims = claim_map(previous)
    new_claims = claim_map(current)
    changes: list[dict] = []
    for field in sorted(set(old_claims) | set(new_claims)):
        old_values = old_claims.get(field, {})
        new_values = new_claims.get(field, {})
        added_keys = sorted(set(new_values) - set(old_values))
        removed_keys = sorted(set(old_values) - set(new_values))
        availability_changed = [
            key
            for key in set(old_values) & set(new_values)
            if old_values[key].get("availability") != new_values[key].get("availability")
        ]
        if not added_keys and not removed_keys and not availability_changed:
            continue
        added = [new_values[key]["value"] for key in added_keys]
        removed = [old_values[key]["value"] for key in removed_keys]
        # The new anchor is the value the current run published; the old anchor
        # is the value the previous run published for the same field. When the
        # value was replaced, the old value is no longer in the current set,
        # so it is anchored on the removed values instead. A field that only
        # exists in one of the two runs has no anchor on the other side.
        new_candidates = added_keys or availability_changed or sorted(new_values)
        old_candidates = removed_keys or availability_changed or sorted(old_values)
        new_anchor = (
            new_values.get(new_candidates[0]) if new_candidates else {}
        )
        old_anchor = (
            old_values.get(old_candidates[0]) if old_candidates else {}
        )
        new_facts = _evidence_facts(current, new_anchor.get("evidence_id"))
        old_facts = _evidence_facts(previous, old_anchor.get("evidence_id"))
        record = {
            "organisation_number": current.get("organisation_number"),
            "field": field,
            "change_type": "claim_value_set",
            "old_value": _quote([old_values[key]["value"] for key in sorted(old_values)]),
            "new_value": _quote([new_values[key]["value"] for key in sorted(new_values)]),
            "added": _quote(added),
            "removed": _quote(removed),
            "availability_changed": bool(availability_changed),
            "source_url": new_facts.get("source_url"),
            "retrieved_at": new_facts.get("retrieved_at"),
            "effective_at": new_facts.get("effective_at"),
            "source_class": new_facts.get("source_class"),
            "evidence_id": new_anchor.get("evidence_id"),
            "old_content_sha256": old_facts.get("content_sha256"),
            "new_content_sha256": new_facts.get("content_sha256"),
            "status": "changed",
            "detected_at": detected_at,
            "previous_run_id": previous_run_id,
        }
        record["change_id"] = _change_id(record)
        changes.append(record)
    return changes


def profile_changes(
    previous: dict, current: dict, detected_at: str, previous_run_id: str | None
) -> list[dict]:
    """Registry-level changes tracked by the reference starter's refresh module."""
    try:
        records = diff_profile(
            previous.get("profile") or {}, current.get("profile") or {}
        )
    except ValueError:
        return []
    out = []
    for record in records:
        record = dict(record)
        record.setdefault("change_type", "profile_field")
        record["detected_at"] = detected_at
        record["previous_run_id"] = previous_run_id
        record["change_id"] = _change_id(record)
        out.append(record)
    return out


def _preserved_evidence_needed(
    historical: list[dict], current: dict, previous: dict
) -> list[dict]:
    """Evidence records behind a preserved change that the current run dropped."""
    have = evidence_index(current)
    old = evidence_index(previous)
    needed: list[dict] = []
    for change in historical:
        evidence_id = change.get("evidence_id")
        if not evidence_id or str(evidence_id) in have:
            continue
        record = old.get(str(evidence_id))
        if not record:
            continue
        preserved = dict(record)
        preserved["preserved_from_run"] = (
            previous.get("run_id") or change.get("previous_run_id")
        )
        needed.append(preserved)
    return needed


def attach(
    current_rows: list[dict],
    previous_rows: list[dict],
    previous_path: str | None = None,
) -> tuple[list[dict], dict]:
    previous_by_org = {
        str(row.get("organisation_number")): row for row in previous_rows
    }
    out: list[dict] = []
    baselines = compared = 0
    detected_total = preserved_total = repeated_total = 0
    companies_with_changes = 0
    preserved_evidence = 0

    for row in current_rows:
        envelope = dict(row)
        org = str(envelope.get("organisation_number"))
        prior = previous_by_org.get(org)
        run_started = str((envelope.get("run") or {}).get("started_at") or "")
        if prior is None:
            envelope["changes"] = list(envelope.get("changes") or [])
            envelope["refresh"] = {
                "previous_run_id": None,
                "baseline": True,
                "compared_at": run_started,
                "changes_detected": 0,
                "changes_already_recorded": 0,
                "historical_changes": len(envelope["changes"]),
                "previous_envelopes": previous_path,
            }
            baselines += 1
            out.append(envelope)
            continue

        previous_run_id = prior.get("run_id") or (prior.get("run") or {}).get("run_id")
        # The history is everything already recorded: the previous run's
        # changes and the changes this envelope already carries. A change that
        # is already in the history is not reported a second time.
        historical: list[dict] = []
        historical_ids: set[str] = set()
        for record in list(prior.get("changes") or []) + list(envelope.get("changes") or []):
            key = str(record.get("change_id") or _change_id(record))
            if key in historical_ids:
                continue
            historical_ids.add(key)
            historical.append(record)

        detected = profile_changes(prior, envelope, run_started, previous_run_id)
        detected += diff_claims(prior, envelope, run_started, previous_run_id)
        new_records = []
        repeated = 0
        for record in detected:
            if str(record["change_id"]) in historical_ids:
                repeated += 1
                continue
            historical_ids.add(str(record["change_id"]))
            new_records.append(record)

        needed = _preserved_evidence_needed(historical, envelope, prior)
        if needed:
            evidence = list(envelope.get("evidence") or [])
            evidence.extend(needed)
            envelope["evidence"] = evidence
            preserved_evidence += len(needed)

        envelope["changes"] = historical + new_records
        envelope["refresh"] = {
            "previous_run_id": previous_run_id,
            "baseline": False,
            "compared_at": run_started,
            "changes_detected": len(new_records),
            "changes_already_recorded": repeated,
            "historical_changes": len(historical),
            "previous_envelopes": previous_path,
        }
        compared += 1
        detected_total += len(new_records)
        repeated_total += repeated
        preserved_total += len(historical)
        if envelope["changes"]:
            companies_with_changes += 1
        out.append(envelope)

    report = {
        "envelopes": len(out),
        "compared": compared,
        "baselines": baselines,
        "changes_detected": detected_total,
        "changes_already_recorded": repeated_total,
        "changes_preserved": preserved_total,
        "companies_with_changes": companies_with_changes,
        "preserved_evidence_records": preserved_evidence,
        "previous_envelopes": previous_path,
    }
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelopes", required=True, help="Current run envelopes JSONL")
    parser.add_argument(
        "--previous",
        default=None,
        help="Previous run envelopes JSONL (the prior snapshot). Omit for a baseline run.",
    )
    parser.add_argument("--output", required=True, help="Output envelopes JSONL")
    parser.add_argument("--report", default=None, help="Write a JSON report here")
    args = parser.parse_args()

    current_rows = read_jsonl(args.envelopes)
    previous_rows = read_jsonl(args.previous) if args.previous else []
    rows, report = attach(current_rows, previous_rows, args.previous)
    write_jsonl(args.output, rows)
    report["output"] = args.output
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
