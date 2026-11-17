#!/usr/bin/env bash
#
# run_official_batch.sh — the command an evaluator runs.
#
# The official submission contract asks for "one documented command that accepts
# a JSONL batch of organisation numbers" and "exactly one terminal envelope per
# input":
#
#   https://builderr.ai/starter-briefs/signalpost.md          (retrieved 2026-11-17)
#   https://builderr.ai/signalpost-starter-kit.tar.gz         (retrieved 2026-11-18)
#
# Usage:
#   scripts/run_official_batch.sh --batch organisations.jsonl
#   scripts/run_official_batch.sh --batch organisations.jsonl \
#       --previous-envelopes out/submission/envelopes.jsonl
#   scripts/run_official_batch.sh --batch organisations.jsonl --rebuild-indexes
#
# Options:
#   --batch PATH              JSONL batch of organisation numbers (required).
#                             One organisation number per line, either as a bare
#                             number or as an object with "organisation_number".
#   --out-dir PATH            Where the run writes its artifacts.
#   --run-id ID               Run identifier (default: official-<UTC timestamp>).
#   --previous-envelopes PATH The prior run's envelopes. With it, every envelope
#                             carries refresh metadata and the material changes
#                             since that run, and the earlier evidence behind a
#                             recorded change is preserved.
#   --rebuild-indexes         Rebuild the NAV job-feed and Wikidata indexes from
#                             their live sources instead of using the frozen
#                             copies committed under data/.
#   --workers N               Parallel workers for the registry and website
#                             capture (default 8).
#   --min-audit N             Minimum number of audited observations (default 300).
#
# The run needs no API key, no login and no paid account. External cost: $0.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BATCH=""
OUT_DIR=""
RUN_ID=""
PREVIOUS=""
REBUILD_INDEXES=0
WORKERS="${WORKERS:-8}"
MIN_AUDIT="${MIN_AUDIT:-300}"

say() { printf '\n=== %s ===\n' "$*"; }
run() { printf '+ %s\n' "$*"; "$@"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --batch) BATCH="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --previous-envelopes) PREVIOUS="$2"; shift 2 ;;
    --rebuild-indexes) REBUILD_INDEXES=1; shift ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --min-audit) MIN_AUDIT="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$BATCH" ]] || { echo "--batch is required" >&2; exit 2; }
[[ -s "$BATCH" ]] || { echo "batch file not found or empty: $BATCH" >&2; exit 2; }
[[ -n "$RUN_ID" ]] || RUN_ID="official-$(date -u +%Y%m%dT%H%M%SZ)"
[[ -n "$OUT_DIR" ]] || OUT_DIR="out/run-$RUN_ID"
# The pipeline writes to out/run-<run-id>; --out-dir only says where the
# finished run should end up, so the directory is moved once the run is done.
PIPELINE_OUT="out/run-$RUN_ID"

say "1. read the supplied batch"
BATCH_ROWS="$(wc -l < "$BATCH" | tr -d ' ')"
echo "batch: $BATCH ($BATCH_ROWS rows)"
# The batch contract is one terminal envelope per input, so the input count is
# checked before any work starts.
BATCH_ORGS="$(uv run python - "$BATCH" <<'PY'
import sys
sys.path.insert(0, "src")
from norway_company_agent.batch import read_organisation_numbers
orgs = read_organisation_numbers(sys.argv[1])
print(len(orgs))
print(orgs[0] if orgs else "")
PY
)"
BATCH_COUNT="$(printf '%s\n' "$BATCH_ORGS" | sed -n '1p')"
BATCH_FIRST="$(printf '%s\n' "$BATCH_ORGS" | sed -n '2p')"
echo "organisations: $BATCH_COUNT (first: ${BATCH_FIRST:-none})"
[[ "$BATCH_COUNT" -gt 0 ]] || { echo "the batch holds no organisation numbers" >&2; exit 1; }

say "2. prepare the frozen source indexes"
CACHE="${CACHE:-.cache/run-$RUN_ID}"
NAV_INDEX="${NAV_INDEX:-data/nav-job-index.jsonl}"
WIKIDATA_INDEX="${WIKIDATA_INDEX:-data/wikidata-index.jsonl}"
if [[ "$REBUILD_INDEXES" == "1" ]]; then
  mkdir -p "$CACHE"
  run uv run python scripts/run_nav_job_feed_connector.py \
    --build-index --index "$CACHE/nav-job-index.jsonl" --days 183 --workers 24
  NAV_INDEX="$CACHE/nav-job-index.jsonl"
  run uv run python scripts/run_wikidata_connector.py \
    --build-index --organisations "$BATCH" --index "$CACHE/wikidata-index.jsonl"
  WIKIDATA_INDEX="$CACHE/wikidata-index.jsonl"
else
  echo "using the committed frozen indexes (rebuild with --rebuild-indexes)"
fi

say "3. run the pipeline over the supplied batch"
# The request counter is installed by the interpreter itself (sitecustomize.py),
# so every subprocess of the run is counted. It records the host, the method
# and the status only, and it is inert unless NORHOUND_REQUEST_LOG is set.
mkdir -p "$PIPELINE_OUT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export NORHOUND_REQUEST_LOG="$PIPELINE_OUT/requests.jsonl"
run env \
  RUN_ID="$RUN_ID" \
  ENTRY_MANIFEST="$BATCH" \
  CACHE="$CACHE" \
  NAV_INDEX="$NAV_INDEX" \
  WIKIDATA_INDEX="$WIKIDATA_INDEX" \
  WORKERS="$WORKERS" \
  MIN_AUDIT="$MIN_AUDIT" \
  bash scripts/run_full_batch.sh

if [[ "$OUT_DIR" != "$PIPELINE_OUT" ]]; then
  mkdir -p "$(dirname "$OUT_DIR")"
  rm -rf "$OUT_DIR"
  mv "$PIPELINE_OUT" "$OUT_DIR"
  echo "moved the run to $OUT_DIR"
fi

say "4. attach the refresh history"
if [[ -n "$PREVIOUS" ]]; then
  [[ -s "$PREVIOUS" ]] || { echo "previous envelopes not found: $PREVIOUS" >&2; exit 1; }
  run uv run python scripts/attach_refresh_changes.py \
    --envelopes "$OUT_DIR/envelopes-final.jsonl" \
    --previous "$PREVIOUS" \
    --output "$OUT_DIR/envelopes-final.jsonl" \
    --report "$OUT_DIR/refresh-report.json"
else
  run uv run python scripts/attach_refresh_changes.py \
    --envelopes "$OUT_DIR/envelopes-final.jsonl" \
    --output "$OUT_DIR/envelopes-final.jsonl" \
    --report "$OUT_DIR/refresh-report.json"
fi

say "5. write the machine-readable run report"
run uv run python scripts/build_official_run_report.py \
  --run-dir "$OUT_DIR" \
  --output "$OUT_DIR/official-run-report.json"

say "result"
python3 - "$OUT_DIR" "$BATCH_COUNT" <<'PY'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
expected = int(sys.argv[2])
report = json.loads((out / "official-run-report.json").read_text())
print("input organisations:", expected)
print("terminal envelopes:  ", report["outputs"]["envelopes"])
print("runtime:             ", f'{report["runtime_ms"] / 1000 / 60:.1f} min')
print("requests:            ", json.dumps(report["requests"]))
print("third-party cost:    ", report["third_party_cost_usd"], "USD")
print("entity precision:    ", report["identity_precision"])
print("wrong-company:       ", report["wrong_company_publications"])
PY

say "done"
printf 'envelopes: %s\n' "$OUT_DIR/envelopes-final.jsonl"
printf 'run report: %s\n' "$OUT_DIR/official-run-report.json"
