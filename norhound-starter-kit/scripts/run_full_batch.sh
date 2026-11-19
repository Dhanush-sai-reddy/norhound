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
# The annual-report workforce stage downloads and OCRs a full annual report per
# company. It is the run's longest stage, so its worker count is tunable.
WORKFORCE_WORKERS="${WORKFORCE_WORKERS:-8}"
MIN_AUDIT="${MIN_AUDIT:-300}"
ENTRY_MANIFEST="${ENTRY_MANIFEST:-}"

OUT="out/run-$RUN_ID"
CACHE="${CACHE:-.cache/run-$RUN_ID}"
mkdir -p "$OUT" "$CACHE" "$OUT/logs"

# The request counter is installed by the interpreter itself (sitecustomize.py),
# so every subprocess of this run is counted: host, method and status only, no
# path and no query string. It is inert unless NORHOUND_REQUEST_LOG is set,
# and it never changes what a request returns. The run report reads this log.
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export NORHOUND_REQUEST_LOG="$OUT/requests.jsonl"

# Frozen official inputs. They are downloaded once and reused when present.
UNIVERSE="$CACHE/norhound-universe.jsonl.gz"
BRREG_JSON="$CACHE/enheter_alle.json.gz"
DOMAIN_INDEX="${DOMAIN_INDEX:-data/registry-domain-unique.jsonl.gz}"

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
  if [[ "$(cd "$(dirname "$ENTRY_MANIFEST")" && pwd)/$(basename "$ENTRY_MANIFEST")" != "$(cd "$(dirname "$OUT/entry.jsonl")" && pwd)/$(basename "$OUT/entry.jsonl")" ]]; then
    cp "$ENTRY_MANIFEST" "$OUT/entry.jsonl"
  fi
  expected_count="$(wc -l < "$OUT/entry.jsonl" | tr -d ' ')"
  echo "using supplied manifest $ENTRY_MANIFEST ($expected_count organisations)"
else
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

# The stages from here on read the profiles the external pipeline worked on.
# The browser rescue inside that pipeline rewrites the website evidence of the
# homepages it recovers, and the verifier re-derives identity from the frozen
# profile: a stage that still read the pre-rescue file would verify every
# recovered observation against a profile that no longer exists and drop it.
PROFILES="$OUT/profiles-promoted.jsonl"

say "5. external footprint: every keyless connector"
# Fagfolkguiden is the only keyless source that yields a scored rating (0.032 of
# both ratings_reviews and sentiment) and costs ~46 min per 1,000 companies, so
# it runs by default. The annual-report PDF/OCR extractor measured 3 h 22 min
# and 0 scored points (RECALL_LEVERS.md): opt in with SLOW_STAGES=1.
SLOW_FLAGS=""
if [[ "${SLOW_STAGES:-0}" == "1" ]]; then
  SLOW_FLAGS="--workforce-pdf"
fi
run uv run python scripts/run_external_pipeline.py \
  --profiles "$OUT/profiles-promoted.jsonl" \
  --envelopes "$OUT/envelopes.jsonl" \
  --prefix "$OUT/batch" \
  --jobs --keyless --nav --workforce --kunngjoring --google-news $SLOW_FLAGS \
  --rescue-workers "${RESCUE_WORKERS:-16}" \
  --rescue-timeout "${RESCUE_TIMEOUT:-20}" \
  --nav-index "${NAV_INDEX:-data/nav-job-index.jsonl}" \
  --wikidata-index "${WIKIDATA_INDEX:-data/wikidata-index.jsonl}" \
  --workforce-workers "$WORKFORCE_WORKERS" \
  --minimum-audit "$MIN_AUDIT"

if [[ -s "$OUT/batch-rescued-profiles.jsonl" ]]; then
  PROFILES="$OUT/batch-rescued-profiles.jsonl"
  echo "using browser-rescued profiles: $PROFILES"
fi

say "6. merge every connector output into one observation corpus"
# Only real connector outputs are merged. The glob "$OUT"/batch.*.jsonl also
# catches three derived files, and merging them back in corrupts the corpus:
#   batch.keyless.jsonl  — the concatenation of the keyless parts, so merging
#                          it and its parts inserts every row twice
#   batch.external.jsonl  — the consolidated corpus itself
#   batch.enriched.jsonl  — one row per company: an ENVELOPE, not an observation
#   batch.labels.jsonl    — one row per observation: a LABEL, not an observation
# A label row and its observation share an id, and the merge keeps the first
# row it sees for an id, so a label row can silently displace the observation
# it belongs to.
# proff.no cannot be re-verified and carries third-party financial figures;
# google.com is excluded because the Places API needs a key and the Maps rows
# were scraped against Google's Terms of Service.
INPUTS=()
for tag in activity news jobs rolecards sole-declarer ats nav nav-search registry-site purehelp \
           workforce-registry workforce-pdf fagfolk google-news kunngjoring \
           contacts sitedesc substruct sitemap updates wikidata gleif discovery \
           linkedin reddit handles; do
  f="$OUT/batch.$tag.jsonl"
  if [[ -s "$f" ]]; then
    INPUTS+=("$f")
    printf '  %-22s %s rows\n' "$tag" "$(wc -l < "$f" | tr -d ' ')"
  fi
done
[[ ${#INPUTS[@]} -gt 0 ]] || { echo "no connector outputs found"; exit 1; }
run uv run python scripts/merge_external_outputs.py \
  --inputs "${INPUTS[@]}" \
  --output "$OUT/external-final.jsonl" \
  --report "$OUT/merge-report.json" \
  --exclude-hosts proff.no google.com \
  --stamp-observed-at \
  --dedupe-latest

say "7. purge wrong-company probes"
run uv run python scripts/purge_wrong_company_probes.py \
  --observations "$OUT/external-final.jsonl" \
  --profiles "$PROFILES" \
  --output "$OUT/external-final.jsonl" \
  --report "$OUT/purge-report.json"

say "8. re-verify every observation against frozen evidence"
run uv run python scripts/verify_and_label_observations.py \
  --profiles "$PROFILES" \
  --observations "$OUT/external-final.jsonl" \
  --labels "$OUT/labels-final.jsonl" \
  --report "$OUT/verify-report.json" \
  --domain-index "${DOMAIN_INDEX:-data/registry-domain-unique.jsonl.gz}"

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
import json, pathlib, sys
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

say "done"
printf 'artifacts: %s\n' "$OUT"
printf 'envelopes: %s\n' "$OUT/envelopes-final.jsonl"
printf 'measure:   %s\n' "$OUT/measure-final.json"
