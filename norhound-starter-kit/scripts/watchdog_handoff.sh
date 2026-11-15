#!/usr/bin/env bash
# One-shot watchdog: wait for the running batch to finish stage 4, then stop it
# before the unbounded Fagfolkguiden/PDF stages and hand over to the fast path.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG="${LOG:?set LOG to the running batch log}"
PID="${PID:?set PID to the running batch pid}"
RUN_ID="${RUN_ID:?set RUN_ID}"

while kill -0 "$PID" 2>/dev/null; do
  if grep -q "=== 5. external footprint" "$LOG"; then
    echo "$(date -u +%H:%M:%S) stage 5 reached — stopping the slow path"
    pkill -f "run_full_batch.sh" 2>/dev/null
    pkill -f "run_external_pipeline.py" 2>/dev/null
    pkill -f "run_fagfolkguiden_reviews_connector.py" 2>/dev/null
    sleep 3
    echo "$(date -u +%H:%M:%S) starting the fast path for $RUN_ID"
    RUN_ID="$RUN_ID" CACHE=".cache/run-$RUN_ID" \
      NAV_INDEX=".cache/run-$RUN_ID/nav-job-index.jsonl" \
      WIKIDATA_INDEX=".cache/run-$RUN_ID/wikidata-index.jsonl" \
      bash scripts/run_stages_5_13.sh
    exit $?
  fi
  sleep 5
done

echo "$(date -u +%H:%M:%S) batch exited before stage 5 — nothing handed over"
exit 1
