# Minimal output contract

Emit one JSON object per input organisation number.

```json
{
  "organisation_number": "123456789",
  "run": {
    "run_id": "2026-08-24-a",
    "started_at": "2026-08-24T06:00:00Z",
    "completed_at": "2026-08-24T06:00:08Z",
    "terminal_status": "completed"
  },
  "claims": [
    {
      "field": "official_website",
      "value": "https://example.no/",
      "availability": "available",
      "confidence": 0.99,
      "evidence_ids": ["ev-1"]
    }
  ],
  "evidence": [
    {
      "id": "ev-1",
      "source_url": "https://example.no/",
      "source_class": "company_owned",
      "retrieved_at": "2026-08-24T06:00:04Z",
      "content_sha256": "...",
      "claim_span": "Example AS, organisation number 123 456 789"
    }
  ],
  "changes": [
    {
      "organisation_number": "123456789",
      "field": "registry.employees",
      "change_type": "profile_field",
      "old_value": 10,
      "new_value": 12,
      "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/123456789",
      "retrieved_at": "2026-08-25T06:00:04Z",
      "effective_at": "2026-08-24T00:00:00Z",
      "source_class": "official_api",
      "old_content_sha256": "...",
      "new_content_sha256": "...",
      "status": "changed",
      "detected_at": "2026-08-25T06:00:04Z",
      "previous_run_id": "2026-08-24-a",
      "change_id": "b1946ac92492d2347c6235b4d2611184"
    }
  ],
  "refresh": {
    "previous_run_id": "2026-08-24-a",
    "baseline": false,
    "compared_at": "2026-08-25T06:00:04Z",
    "changes_detected": 1,
    "changes_already_recorded": 0,
    "historical_changes": 0,
    "previous_envelopes": "out/run-2026-08-24-a/envelopes-final.jsonl"
  },
  "errors": [],
  "operations": {
    "requests": 4,
    "runtime_ms": 8120,
    "third_party_cost_usd": 0
  }
}
```

Allowed availability states are `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous` and `failed`. A checked source that has zero jobs or zero locations is different from a source that was not checked.

## Refresh metadata

The current brief requires "refresh metadata and material changes since the
previous run" and "idempotent refresh with prior snapshots preserved"
(https://builderr.ai/starter-briefs/signalpost.md, retrieved 2026-11-17).

- `changes` holds typed old -> new records. Each record names the field, the
  old and the new value, the source URL, the retrieval time, the effective
  date, the content hash of both values and the run that detected it.
- `refresh` names the previous run, whether this company is a baseline (it was
  not in the previous run, so there is nothing to compare), and how many
  changes were detected versus already recorded.
- A change is keyed by a content hash of (organisation, field, old value, new
  value, new content hash), so repeating the comparison records nothing twice
  and the earlier evidence behind a recorded change is kept.

`scripts/attach_refresh_changes.py` writes these two sections; the official
command calls it with `--previous-envelopes <prior envelopes.jsonl>`.
