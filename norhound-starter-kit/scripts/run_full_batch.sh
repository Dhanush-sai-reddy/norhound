#!/usr/bin/env bash
#
# run_full_batch.sh — the whole Signalpost pipeline in one executable.
#
# Every stage below runs WITHOUT an API key, a login or a paid account. The
# only network sources are public pages and official registries:
#
#   * BRREG Enhetsregisteret   — official registry API + official bulk dump
#   * BRREG Kunngjoringer      — official announcements feed
#   * NAV job feed             — official job postings (frozen index)
#   * GLEIF / Wikidata         — public identity registries (frozen indexes)
#   * Fagfolkguiden            — public directory pages
#   * the companies' own sites — public pages
#
# Nothing here needs GOOGLE_PLACES_KEY, FIRECRAWL_API_KEY, NVIDIA_API_KEY or
# any other credential. The run is fail-fast: the first failing stage stops it.
#
# Usage:
#   scripts/run_full_batch.sh                 # full 1,000-company run
#   ENTRY_MANIFEST=smoke30.jsonl scripts/run_full_batch.sh   # smaller batch
#   COUNT=1200 scripts/run_full_batch.sh      # larger than 1,000
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COUNT="${COUNT:-1000}"
SEED="${SEED:-20260823}"
RUN_ID="${RUN_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
WORKERS="${WORKERS:-8}"
MIN_AUDIT="${MIN_AUDIT:-300}"
ENTRY_MANIFEST="${ENTRY_MANIFEST:-}"

OUT="out/run-$RUN_ID"
CACHE="${CACHE:-.cache/run-$RUN_ID}"
mkdir -p "$OUT" "$CACHE" "$OUT/logs"

# Frozen official inputs. They are downloaded once and reused when present.
UNIVERSE="$CACHE/norhound-universe.jsonl.gz"
BRREG_JSON="$CACHE/enheter_alle.json.gz"
DOMAIN_INDEX="data/registry-domain-unique.jsonl.gz"

say() { printf '\n=== %s ===\n' "$*"; }
run() { printf '+ %s\n' "$*"; "$@"; }

say "0. official inputs (keyless public downloads)"
if [[ ! -s "$UNIVERSE" ]]; then
  run curl -sSL --retry 3 -o "$UNIVERSE" \
    'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz'
fi
if [[ ! -s "$BRREG_JSON" ]]; then
  run curl -sSL --retry 3 -o "$BRREG_JSON" \
    'https://data.brreg.no/enhetsregisteret/api/enheter/lastned'
fi

say "1. sole-declarer domain index (register domains claimed by exactly one org)"
if [[ ! -s "$DOMAIN_INDEX" ]]; then
  run uv run python scripts/build_registry_domain_index.py \
    --register "$BRREG_JSON" \
    --output "$DOMAIN_INDEX" \
    --report "$OUT/domain-index-report.json"
else
  echo "reusing $DOMAIN_INDEX"
fi

say "2. select the entry batch (same seed and website filter as the submission)"
# A submission must cover 1,000 companies, so the selector enforces that floor.
# The pipeline itself has no such floor: pointing ENTRY_MANIFEST at an existing
# manifest runs the rest of the pipeline on exactly those organisations.
if [[ -n "$ENTRY_MANIFEST" ]]; then
  cp "$ENTRY_MANIFEST" "$OUT/entry.jsonl"
  expected_count="$(wc -l < "$OUT/entry.jsonl" | tr -d ' ')"
  echo "using supplied manifest $ENTRY_MANIFEST ($expected_count organisations)"
else
  run uv run python select_entry_batch.py \
    --universe "$UNIVERSE" \
    --count "$COUNT" \
    --seed "$SEED" \
    --website-only \
    --output "$OUT/entry.jsonl"
  expected_count="$COUNT"
fi

say "3. base batch: registry enrichment + exact-identity website capture"
run uv run python scripts/run_competition_batch.py \
  --organisations "$OUT/entry.jsonl" \
  --bulk "$BRREG_JSON" \
  --profiles-output "$OUT/profiles.jsonl" \
  --output "$OUT/envelopes.jsonl" \
  --report "$OUT/run-report.json" \
  --run-id "$RUN_ID" \
  --expected-count "$expected_count" \
  --workers "$WORKERS"

say "4. promote sites proved by the register's own website filing"
run uv run python scripts/promote_registry_declared_sites.py \
  --profiles "$OUT/profiles.jsonl" \
  --output "$OUT/profiles-promoted.jsonl" \
  --report "$OUT/promote-report.json" \
  --index "$DOMAIN_INDEX"

say "5. external footprint: every keyless connector"
run uv run python scripts/run_external_pipeline.py \
  --profiles "$OUT/profiles-promoted.jsonl" \
  --envelopes "$OUT/envelopes.jsonl" \
  --prefix "$OUT/batch" \
  --jobs --reviews --keyless --nav --workforce --kunngjoring --google-news \
  --nav-index data/nav-job-index.jsonl \
  --wikidata-index data/wikidata-index.jsonl \
  --minimum-audit "$MIN_AUDIT"

say "6. merge every connector output into one observation corpus"
run uv run python scripts/merge_external_outputs.py \
  --inputs "$OUT"/batch.*.jsonl \
  --output "$OUT/external-merged.jsonl" \
  --report "$OUT/merge-report.json" \
  --exclude-hosts proff.no \
  --dedupe-latest

say "7. purge wrong-company probes"
run uv run python scripts/purge_wrong_company_probes.py \
  --observations "$OUT/external-merged.jsonl" \
  --profiles "$OUT/profiles-promoted.jsonl" \
  --output "$OUT/external-merged.jsonl" \
  --report "$OUT/purge-report.json"

say "8. re-verify every observation against frozen evidence"
run uv run python scripts/verify_and_label_observations.py \
  --profiles "$OUT/profiles-promoted.jsonl" \
  --observations "$OUT/external-merged.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --report "$OUT/verify-report.json"

say "9. evaluate the labeled corpus"
run uv run python scripts/evaluate_external_footprint.py \
  --profiles "$OUT/profiles-promoted.jsonl" \
  --observations "$OUT/external-merged.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --output "$OUT/eval.json" \
  --minimum-audit "$MIN_AUDIT"

say "10. emit the terminal contract envelopes"
run uv run python scripts/emit_contract_envelope.py \
  --profiles "$OUT/profiles-promoted.jsonl" \
  --envelopes "$OUT/envelopes.jsonl" \
  --observations "$OUT/external-merged.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --output "$OUT/envelopes-final.jsonl" \
  --report "$OUT/envelope-report.json"

say "11. deterministic grounded summaries (no model, no key)"
run uv run python scripts/build_deterministic_summaries.py \
  --envelopes "$OUT/envelopes-final.jsonl" \
  --output "$OUT/summaries.jsonl" \
  --report "$OUT/summaries-report.json"

say "12. static viewer"
run uv run python scripts/build_static_site.py \
  --envelopes "$OUT/envelopes-final.jsonl" \
  --summaries "$OUT/summaries.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --observations "$OUT/external-merged.jsonl" \
  --eval "$OUT/eval.json" \
  --out "$OUT/site"

say "13. measure the recall proxy"
run uv run python scripts/measure_recall.py \
  --profiles "$OUT/profiles-promoted.jsonl" \
  --observations "$OUT/external-merged.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --output "$OUT/measure.json" \
  --minimum-audit "$MIN_AUDIT"

say "done"
printf 'artifacts: %s\n' "$OUT"
printf 'envelopes: %s\n' "$OUT/envelopes-final.jsonl"
printf 'measure:   %s\n' "$OUT/measure.json"
