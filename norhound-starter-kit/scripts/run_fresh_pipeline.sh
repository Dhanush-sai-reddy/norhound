#!/usr/bin/env bash
#
# run_fresh_pipeline.sh — a full 1,000-company run where NOTHING is reused.
#
# run_full_batch.sh deliberately reuses frozen inputs (universe, BRREG bulk,
# NAV job index, Wikidata index) so a rerun is cheap and reproducible. This
# wrapper does the opposite: it downloads every official input again, rebuilds
# both frozen indexes from the live sources, and only then hands the fresh
# inputs to run_full_batch.sh.
#
# Everything stays keyless. No API key, no login, no paid account.
#
# Usage:
#   scripts/run_fresh_pipeline.sh                # fresh 1,000-company run
#   COUNT=200 scripts/run_fresh_pipeline.sh      # smaller fresh batch
#   NAV_DAYS=30 scripts/run_fresh_pipeline.sh    # shorter NAV index window
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COUNT="${COUNT:-1000}"
SEED="${SEED:-20260823}"
NAV_DAYS="${NAV_DAYS:-183}"
NAV_WORKERS="${NAV_WORKERS:-24}"
RUN_ID="${RUN_ID:-fresh-$(date -u +%Y%m%dT%H%M%SZ)}"
export RUN_ID

OUT="out/run-$RUN_ID"
CACHE=".cache/run-$RUN_ID"
export CACHE
mkdir -p "$OUT" "$CACHE" "$OUT/logs"

UNIVERSE="$CACHE/norhound-universe.jsonl.gz"
BRREG_JSON="$CACHE/enheter_alle.json.gz"
DOMAIN_INDEX="$CACHE/registry-domain-unique.jsonl.gz"
NAV_INDEX="$CACHE/nav-job-index.jsonl"
WIKIDATA_INDEX="$CACHE/wikidata-index.jsonl"

say() { printf '\n=== %s ===\n' "$*"; }
run() { printf '+ %s\n' "$*"; "$@"; }

say "fresh run $RUN_ID (count=$COUNT seed=$SEED nav_days=$NAV_DAYS)"

# ---------------------------------------------------------------- NAV index
# The whole-country feed walk is independent of the entry batch, so it starts
# first and runs while the other official inputs download.
say "A. rebuild the NAV job index from the live feed (background)"
(
  uv run python scripts/run_nav_job_feed_connector.py \
    --build-index \
    --index "$NAV_INDEX" \
    --report "$OUT/nav-index-build-report.json" \
    --days "$NAV_DAYS" \
    --workers "$NAV_WORKERS" \
  && uv run python scripts/run_nav_job_feed_connector.py \
    --resolve-parents \
    --index "$NAV_INDEX" \
    --report "$OUT/nav-index-resolve-report.json" \
    --workers "$NAV_WORKERS"
) > "$OUT/logs/nav-index.log" 2>&1 &
NAV_PID=$!
echo "NAV index build PID $NAV_PID (log $OUT/logs/nav-index.log)"

# ------------------------------------------------------------ official inputs
say "B. download the official inputs again (universe + BRREG bulk)"
run curl -sSL --retry 3 -o "$UNIVERSE" \
  'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz'
run curl -sSL --retry 3 -o "$BRREG_JSON" \
  'https://data.brreg.no/enhetsregisteret/api/enheter/lastned'
ls -la "$UNIVERSE" "$BRREG_JSON"

say "C. rebuild the sole-declarer domain index"
run uv run python scripts/build_registry_domain_index.py \
  --register "$BRREG_JSON" \
  --output "$DOMAIN_INDEX" \
  --report "$OUT/domain-index-report.json"

say "D. select the entry batch (seed $SEED)"
SMOKE_FLAG=""
if [[ "$COUNT" -lt 1000 ]]; then
  SMOKE_FLAG="--allow-smoke"
fi
run uv run python select_entry_batch.py \
  --universe "$UNIVERSE" \
  --count "$COUNT" \
  --seed "$SEED" \
  --website-only \
  $SMOKE_FLAG \
  --output "$OUT/entry.jsonl"

say "E. rebuild the Wikidata index from the fresh entry batch"
run uv run python scripts/run_wikidata_connector.py \
  --build-index \
  --organisations "$OUT/entry.jsonl" \
  --index "$WIKIDATA_INDEX" \
  --report "$OUT/wikidata-index-report.json"

say "F. wait for the NAV index build"
wait "$NAV_PID"
[[ -s "$NAV_INDEX" ]] || { echo "NAV index is empty: $NAV_INDEX"; exit 1; }
echo "NAV index rows: $(wc -l < "$NAV_INDEX" | tr -d ' ')"

# --------------------------------------------------------------- full batch
# run_full_batch.sh sees the fresh universe/BRREG in $CACHE and reuses those
# (they were downloaded in this run), and takes the two rebuilt indexes and the
# already-selected entry batch from the environment.
say "G. run the 14-stage pipeline on the fresh inputs"
ENTRY_MANIFEST="$OUT/entry.jsonl" \
NAV_INDEX="$NAV_INDEX" \
WIKIDATA_INDEX="$WIKIDATA_INDEX" \
bash scripts/run_full_batch.sh

say "fresh run complete"
printf 'artifacts: %s\n' "$OUT"
