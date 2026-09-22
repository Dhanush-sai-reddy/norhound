from __future__ import annotations

from typing import Any


TRACKED_FIELDS: dict[str, tuple[str, ...]] = {
    "registry.name": ("name",),
    "registry.legal_form": ("legal_form",),
    "registry.employees": ("employees",),
    "registry.municipality": ("municipality",),
    "registry.website": ("website",),
    "registry.latest_submitted_accounts": ("latest_submitted_accounts",),
    "financials.records": ("evidence", "financials", "value", "records"),
    "financial_history.years": ("evidence", "financial_history", "value", "years"),
    "roles.roles": ("evidence", "roles", "value", "roles"),
    "locations.locations": ("evidence", "locations", "value", "locations"),
    "website.title": ("evidence", "website", "value", "title"),
    "website.description": ("evidence", "website", "value", "description"),
    "website.social_links": ("evidence", "website", "value", "social_links"),
}


def _read(value: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _evidence_for(profile: dict[str, Any], field: str) -> dict[str, Any]:
    module = field.split(".", 1)[0]
    records = profile.get("evidence", {})
    if module == "registry":
        return records.get("registry_live") or records.get("registry", {})
    return records.get(module, {})


def diff_profile(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    old_org = previous.get("organisation_number")
    new_org = current.get("organisation_number")
    if not old_org or old_org != new_org:
        raise ValueError("Refresh comparison requires the same exact organisation number")
    changes = []
    for field, path in TRACKED_FIELDS.items():
        old_value = _read(previous, path)
        new_value = _read(current, path)
        if old_value == new_value:
            continue
        record = _evidence_for(current, field)
        previous_record = _evidence_for(previous, field)
        changes.append({
            "organisation_number": new_org,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "source_url": record.get("source_url"),
            "retrieved_at": record.get("retrieved_at"),
            "effective_at": record.get("effective_at") or record.get("as_of"),
            "source_class": record.get("source_class") or record.get("source_type"),
            "old_content_sha256": previous_record.get("content_sha256"),
            "new_content_sha256": record.get("content_sha256"),
            "status": record.get("status"),
        })
    return changes


def diff_datasets(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old_by_org = {row["organisation_number"]: row for row in previous}
    new_by_org = {row["organisation_number"]: row for row in current}
    if set(old_by_org) != set(new_by_org):
        raise ValueError("Refresh datasets must have identical organisation-number membership")
    return [
        change
        for org in sorted(old_by_org)
        for change in diff_profile(old_by_org[org], new_by_org[org])
    ]


def attach_refresh(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    """Attach refresh history to shipping envelopes (Soham's 4 update points).

    Each current envelope gains `changes` (typed old->new records with both
    content hashes, so earlier versions are preserved) and `refresh`
    (previous_run_id + baseline flag). Companies absent from the previous run
    are baselines, never changes. Inputs are not mutated; idempotent reruns
    yield empty changes.
    """
    import copy

    old_by_org = {row.get("organisation_number"): row for row in previous}
    previous_run_id = None
    if previous:
        previous_run_id = previous[0].get("run_id")
    out = []
    for env in current:
        row = copy.deepcopy(env)
        org = row.get("organisation_number")
        old = old_by_org.get(org)
        if old is None:
            row["changes"] = []
            row["refresh"] = {"previous_run_id": previous_run_id, "baseline": True}
        else:
            row["changes"] = diff_profile(old.get("profile") or {}, row.get("profile") or {})
            row["refresh"] = {"previous_run_id": old.get("run_id", previous_run_id), "baseline": False}
        out.append(row)
    return out
