#!/usr/bin/env bash
#
# run_stages_5_13.sh — the post-crawl half of the pipeline, with the two
# unbounded stages switched off.
#
# Stages 5-13 of run_full_batch.sh assume they may spend hours on two
# connectors:
#
#   * Fagfolkguiden reviews  — one page per organisation, produced 0 rows after
#                              4 h on the 2026-11-07 run.
#   * annual-report PDF/OCR  — one full annual report per company, 10800 s cap.
#
# Both are still reachable from run_full_batch.sh; this script is the fast
# path: it skips them (--no-reviews --no-workforce-pdf) and keeps the registry
# employee count, NAV, Wikidata, Purehelp, jobs, announcements and news.
#
# Usage:
#   RUN_ID=fresh-20261115T073743Z scripts/run_stages_5_13.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_ID="${RUN_ID:?set RUN_ID to an existing out/run-<id> directory}"
OUT="out/run-$RUN_ID"
CACHE="${CACHE:-.cache/run-$RUN_ID}"
MIN_AUDIT="${MIN_AUDIT:-300}"
WORKFORCE_WORKERS="${WORKFORCE_WORKERS:-8}"
RESCUE_WORKERS="${RESCUE_WORKERS:-16}"
RESCUE_TIMEOUT="${RESCUE_TIMEOUT:-20}"
NAV_INDEX="${NAV_INDEX:-data/nav-job-index.jsonl}"
WIKIDATA_INDEX="${WIKIDATA_INDEX:-data/wikidata-index.jsonl}"

PROFILES="$OUT/profiles-promoted.jsonl"
[[ -s "$PROFILES" ]] || { echo "missing $PROFILES (run stages 1-4 first)"; exit 1; }

say() { printf '\n=== %s ===\n' "$*"; }
run() { printf '+ %s\n' "$*"; "$@"; }

say "5. external footprint (fast connectors only)"
run uv run python scripts/run_external_pipeline.py \
  --profiles "$PROFILES" \
  --envelopes "$OUT/envelopes.jsonl" \
  --prefix "$OUT/batch" \
  --jobs --no-reviews --no-workforce-pdf --keyless --nav --workforce --kunngjoring --google-news \
  --rescue-workers "$RESCUE_WORKERS" \
  --rescue-timeout "$RESCUE_TIMEOUT" \
  --nav-index "$NAV_INDEX" \
  --wikidata-index "$WIKIDATA_INDEX" \
  --workforce-workers "$WORKFORCE_WORKERS" \
  --minimum-audit "$MIN_AUDIT"

if [[ -s "$OUT/batch-rescued-profiles.jsonl" ]]; then
  PROFILES="$OUT/batch-rescued-profiles.jsonl"
  echo "using browser-rescued profiles: $PROFILES"
fi

say "6. merge every connector output into one observation corpus"
run uv run python scripts/merge_external_outputs.py \
  --inputs "$OUT"/batch.*.jsonl \
  --output "$OUT/external-merged.jsonl" \
  --report "$OUT/merge-report.json" \
  --exclude-hosts proff.no google.com \
  --dedupe-latest

say "7. purge wrong-company probes"
run uv run python scripts/purge_wrong_company_probes.py \
  --observations "$OUT/external-merged.jsonl" \
  --profiles "$PROFILES" \
  --output "$OUT/external-merged.jsonl" \
  --report "$OUT/purge-report.json"

say "8. re-verify every observation against frozen evidence"
run uv run python scripts/verify_and_label_observations.py \
  --profiles "$PROFILES" \
  --observations "$OUT/external-merged.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --report "$OUT/verify-report.json"

say "9. evaluate the labeled corpus"
run uv run python scripts/evaluate_external_footprint.py \
  --profiles "$PROFILES" \
  --observations "$OUT/external-merged.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --output "$OUT/eval.json" \
  --minimum-audit "$MIN_AUDIT"

say "10. emit the terminal contract envelopes"
run uv run python scripts/emit_contract_envelope.py \
  --profiles "$PROFILES" \
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

say "13. recall proxy (six-field) + family recall"
run uv run python scripts/measure_recall.py \
  --profiles "$PROFILES" \
  --observations "$OUT/external-merged.jsonl" \
  --labels "$OUT/labels.jsonl" \
  --output "$OUT/measure.json" \
  --minimum-audit "$MIN_AUDIT"
run uv run python scripts/measure_family_recall.py \
  --envelopes "$OUT/envelopes-final.jsonl" \
  --output "$OUT/measure-family.json"

say "done"
python3 - "$OUT" <<'PY'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
ev = json.loads((out / "eval.json").read_text())
m = json.loads((out / "measure.json").read_text())
print("published:", ev.get("published_audited"), "of", ev.get("observations"))
print("entity_precision:", ev.get("entity_precision"), "wrong_entity:", ev.get("wrong_entity_publications"))
print("coverage:", json.dumps(ev.get("coverage")))
print("recall_proxy_50:", m.get("recall_proxy_50"))
fam = out / "measure-family.json"
if fam.exists():
    print("family:", json.dumps(json.loads(fam.read_text()).get("families", {})))
PY
