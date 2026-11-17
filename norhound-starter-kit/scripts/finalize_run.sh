#!/usr/bin/env bash
#
# finalize_run.sh — wait for the slow connectors of one run, then rebuild every
# artifact from the merged corpus.
#
# The 2026-11-15 fresh run deliberately skipped the two unbounded stages
# (Fagfolkguiden reviews, annual-report PDF/OCR). They were then run on their
# own against the same profiles, so this script waits for them and folds their
# output into the corpus before re-verifying, re-evaluating and re-emitting.
#
# Only real connector outputs are merged: the derived files the pipeline writes
# (batch.external.jsonl, batch.enriched.jsonl, batch.labels.jsonl) are excluded
# so no observation can enter the corpus twice.
#
# Usage:
#   RUN_ID=fresh-20261115T073743Z WAIT_PIDS="201147 201148 201977" scripts/finalize_run.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_ID="${RUN_ID:?set RUN_ID}"
OUT="out/run-$RUN_ID"
MIN_AUDIT="${MIN_AUDIT:-300}"
WAIT_PIDS="${WAIT_PIDS:-}"

# The request counter is installed by the interpreter itself (sitecustomize.py),
# so every subprocess of this run is counted: host, method and status only.
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export NORHOUND_REQUEST_LOG="$OUT/requests.jsonl"

say() { printf '\n=== %s ===\n' "$*"; }
run() { printf '+ %s\n' "$*"; "$@"; }

if [[ -n "$WAIT_PIDS" ]]; then
  say "waiting for the slow connectors: $WAIT_PIDS"
  while :; do
    alive=""
    for pid in $WAIT_PIDS; do
      if kill -0 "$pid" 2>/dev/null; then alive="$alive $pid"; fi
    done
    [[ -z "$alive" ]] && break
    sleep 30
  done
  echo "all slow connectors finished"
fi

PROFILES="$OUT/profiles-promoted.jsonl"
[[ -s "$OUT/batch-rescued-profiles.jsonl" ]] && PROFILES="$OUT/batch-rescued-profiles.jsonl"

say "connector outputs"
INPUTS=()
# Every entry is a real connector output. Deliberately absent:
#   batch.keyless.jsonl  — concatenation of contacts/sitedesc/substruct/
#                          sitemap/updates/wikidata, so merging both it and
#                          its parts would insert every row twice
#   batch.external.jsonl, batch.enriched.jsonl, batch.labels.jsonl
#                        — derived from the merge, never an input to it
for tag in activity news jobs ats nav nav-search registry-site purehelp \
           workforce-registry workforce-pdf fagfolk google-news kunngjoring \
           contacts sitedesc substruct sitemap updates wikidata; do
  f="$OUT/batch.$tag.jsonl"
  if [[ -s "$f" ]]; then
    INPUTS+=("$f")
    printf '  %-22s %s rows\n' "$tag" "$(wc -l < "$f" | tr -d ' ')"
  fi
done
[[ ${#INPUTS[@]} -gt 0 ]] || { echo "no connector outputs found"; exit 1; }

say "6. merge every connector output into one observation corpus"
run uv run python scripts/merge_external_outputs.py \
  --inputs "${INPUTS[@]}" \
  --output "$OUT/external-final.jsonl" \
  --report "$OUT/merge-final-report.json" \
  --exclude-hosts proff.no google.com \
  --stamp-observed-at \
  --dedupe-latest

say "7. purge wrong-company probes"
run uv run python scripts/purge_wrong_company_probes.py \
  --observations "$OUT/external-final.jsonl" \
  --profiles "$PROFILES" \
  --output "$OUT/external-final.jsonl" \
  --report "$OUT/purge-final-report.json"

say "8. re-verify every observation against frozen evidence"
run uv run python scripts/verify_and_label_observations.py \
  --profiles "$PROFILES" \
  --observations "$OUT/external-final.jsonl" \
  --labels "$OUT/labels-final.jsonl" \
  --report "$OUT/verify-final-report.json"

say "9. evaluate the labeled corpus"
run uv run python scripts/evaluate_external_footprint.py \
  --profiles "$PROFILES" \
  --observations "$OUT/external-final.jsonl" \
  --labels "$OUT/labels-final.jsonl" \
  --output "$OUT/eval-final.json" \
  --minimum-audit "$MIN_AUDIT"

say "10. emit the terminal contract envelopes"
run uv run python scripts/emit_contract_envelope.py \
  --profiles "$PROFILES" \
  --envelopes "$OUT/envelopes.jsonl" \
  --observations "$OUT/external-final.jsonl" \
  --labels "$OUT/labels-final.jsonl" \
  --output "$OUT/envelopes-final.jsonl" \
  --report "$OUT/envelope-final-report.json"

say "11. deterministic grounded summaries"
run uv run python scripts/build_deterministic_summaries.py \
  --envelopes "$OUT/envelopes-final.jsonl" \
  --output "$OUT/summaries.jsonl" \
  --report "$OUT/summaries-report.json"

say "12. static viewer"
run uv run python scripts/build_static_site.py \
  --envelopes "$OUT/envelopes-final.jsonl" \
  --summaries "$OUT/summaries.jsonl" \
  --labels "$OUT/labels-final.jsonl" \
  --observations "$OUT/external-final.jsonl" \
  --eval "$OUT/eval-final.json" \
  --out "$OUT/site"

say "13. recall proxies"
run uv run python scripts/measure_recall.py \
  --profiles "$PROFILES" \
  --observations "$OUT/external-final.jsonl" \
  --labels "$OUT/labels-final.jsonl" \
  --output "$OUT/measure-final.json" \
  --minimum-audit "$MIN_AUDIT"
run uv run python scripts/measure_family_recall.py \
  --envelopes "$OUT/envelopes-final.jsonl" \
  --output "$OUT/measure-family-final.json"

say "result"
python3 - "$OUT" <<'PY'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
ev = json.loads((out / "eval-final.json").read_text())
m = json.loads((out / "measure-final.json").read_text())
fam = json.loads((out / "measure-family-final.json").read_text())
print("published:", ev.get("published_audited"), "of", ev.get("observations"))
print("entity_precision:", ev.get("entity_precision"), "wrong_entity:", ev.get("wrong_entity_publications"))
print("coverage:", json.dumps(ev.get("coverage")))
print("recall_proxy_50:", round(m.get("recall_proxy_50", 0), 2))
for name, row in fam["family_company_recall"].items():
    print(f"  {name:12} {row['covered']:5}/{row['opportunities']:<5} {row['recall']:.3f}")
PY
