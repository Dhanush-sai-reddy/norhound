#!/usr/bin/env bash
# NorHound -- ONE command for the complete submission pipeline.
#
#   bash scripts/norhound_live.sh
#
# Runs every stage that produces a submitted artifact, in order, and prints a
# final scorecard:
#
#   0  dependency install (pinned)
#   1  download official Brregregistry bulk CSV + the official company universe
#   2  deterministic 1,000-company manifest (seed 20260823, website-only)
#   3  base batch      -> registry enrichment + exact-identity website capture
#   4  external pipeline -> company-site activity/news, NAV official job feed,
#                           Fagfolkguiden reviews, registry contacts/structure/
#                           updates, sitemap lastmod, Wikidata  (all default-on)
#   5  verify + label  -> re-verify every observation against frozen evidence
#   6  evaluate        -> precision / coverage / qualification gate
#   7  summaries       -> deterministic, grounded, no API key
#   8  static site     -> searchable viewer (file:// openable)
#
# Env knobs (all optional):
#   COUNT=1000          companies in the manifest
#   EXPECTED=$COUNT     terminal envelopes required
#   SMOKE=1             10-company dry run of the same chain (fast, no guard)
#   SKIP_DOWNLOAD=1     reuse existing data/ inputs
#
# Container note: this is the entrypoint for `docker compose run --rm
# norhound-full`, so it must keep working with only Docker on the host.
set -euo pipefail
cd "$(dirname "$0")/.."

SMOKE="${SMOKE:-0}"
COUNT="${COUNT:-1000}"
EXPECTED="${EXPECTED:-$COUNT}"
PFX="${PFX:-out/norhound}"

# The official Brregregistry bulk export may already sit at the repo root (as
# shipped) or in data/ (as downloaded by step 1). Resolve either, and fail loudly
# rather than silently running without the registry.
BULK="${BULK:-}"
if [ -z "$BULK" ]; then
  for cand in data/brreg-enheter.csv brreg-enheter.csv; do
    [ -s "$cand" ] && BULK="$cand" && break
  done
fi
if [ -z "$BULK" ]; then
  echo "ERROR: Brregregistry bulk CSV not found (looked for data/brreg-enheter.csv, brreg-enheter.csv)." >&2
  echo "       Run without SKIP_DOWNLOAD, or set BULK=/path/to/brreg-enheter.csv" >&2
  exit 1
fi

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# ---------------------------------------------------------------- 0 deps ----
if [ "$SMOKE" != "1" ]; then
  say "step 0: pinned dependencies"
  uv sync --frozen
fi

# ------------------------------------------------------------ 1 downloads ----
if [ "$SMOKE" != "1" ] && [ "${SKIP_DOWNLOAD:-0}" != "1" ]; then
  say "step 1: official inputs (idempotent)"
  mkdir -p data
  [ -s data/brreg-enheter.csv ] || curl -L --fail --retry 3 \
    'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' \
    -o data/brreg-enheter.csv
  [ -s data/norhound-universe.jsonl.gz ] || curl -L --fail --retry 3 \
    'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' \
    -o data/norhound-universe.jsonl.gz
fi

# -------------------------------------------------------------- 2 manifest ----
if [ "$SMOKE" = "1" ]; then
  say "step 2: 10-company smoke manifest (publicity guard bypassed)"
  mkdir -p out data
  head -n 10 entry-web1000.jsonl > out/smoke-manifest.jsonl
  MANIFEST=out/smoke-manifest.jsonl
  EXPECTED=10
  PFX=out/smoke
else
  say "step 2: $COUNT-company manifest (seed 20260823, website-only)"
  mkdir -p out data
  uv run python select_entry_batch.py \
    --universe data/norhound-universe.jsonl.gz \
    --count "$COUNT" \
    --seed 20260823 \
    --website-only \
    --bulk "$BULK" \
    --output data/entry-manifest.jsonl
  MANIFEST=data/entry-manifest.jsonl
fi

# ------------------------------------------------------------ 3 base batch ----
say "step 3: base batch (registry + exact-identity website capture)"
uv run python scripts/run_competition_batch.py \
  --organisations "$MANIFEST" \
  --bulk "$BULK" \
  --profiles-output "$PFX-profiles.jsonl" \
  --output "$PFX-envelopes.jsonl" \
  --report "$PFX-run-report.json" \
  --run-id norhound-one-command \
  --expected-count "$EXPECTED"

# ------------------------------------------------------- 4 external pipeline ----
say "step 4: external pipeline (NAV jobs + reviews + keyless all default-on)"
uv run python scripts/run_external_pipeline.py \
  --profiles "$PFX-profiles.jsonl" \
  --envelopes "$PFX-envelopes.jsonl" \
  --prefix "$PFX" \
  --jobs --reviews --keyless --nav

# --------------------------------------------------------- 5 verify + label ----
# NOTE: steps 4 already ran verify_and_label_observations.py and
# evaluate_external_footprint.py internally (that is what makes publication
# conditional on a verified exact_entity label). We only re-run the evaluation
# when VERIFY_RECHECK=1, as an independent reproducibility audit that the
# in-pipeline labels are not an artefact of the same code path.
if [ "${VERIFY_RECHECK:-0}" = "1" ]; then
  say "step 5: independent verify + label recheck (audit)"
  uv run python scripts/verify_and_label_observations.py \
    --profiles "$PFX-profiles.jsonl" \
    --observations "$PFX.external.jsonl" \
    --labels "$PFX.labels.recheck.jsonl" \
    --report "$PFX.label-report.recheck.json"
  MIN_AUDIT=300
  [ "$SMOKE" = "1" ] && MIN_AUDIT=1
  uv run python scripts/evaluate_external_footprint.py \
    --profiles "$PFX-profiles.jsonl" \
    --observations "$PFX.external.jsonl" \
    --labels "$PFX.labels.recheck.jsonl" \
    --output "$PFX.external-eval.recheck.json" \
    --minimum-audit "$MIN_AUDIT"
fi

# ------------------------------------------------------------- 7 summaries ----
say "step 7: deterministic grounded summaries (no API key)"
uv run python scripts/build_deterministic_summaries.py \
  --envelopes "$PFX-envelopes.jsonl" \
  --output "$PFX.summaries.jsonl" \
  --report "$PFX.summaries-report.json"

# ------------------------------------------------------------ 8 static site ----
say "step 8: searchable static site"
uv run python scripts/build_static_site.py \
  --envelopes "$PFX-envelopes.jsonl" \
  --summaries "$PFX.summaries.jsonl" \
  --out "$PFX-site"

# -------------------------------------------------------------- scorecard ----
say "DONE -- artifacts"
uv run python - "$PFX" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
ev = json.loads((p.parent / (p.name + ".external-eval.json")).read_text())
print(f"  profiles              {ev['profiles']}")
print(f"  observations          {ev['observations']}")
print(f"  published (verified)  {ev['published_audited']}")
print(f"  entity precision      {ev['entity_precision']}")
print(f"  metric precision      {ev['metric_precision']}")
print(f"  wrong-entity pubs     {ev['wrong_entity_publications']}")
print(f"  unsupported pubs      {ev['unsupported_publications']}")
print(f"  qualification passed  {ev['qualification_passed']}")
print(f"  coverage any_external {ev['coverage']['any_external']}")
print(f"  workforce_jobs        {ev['coverage']['workforce_jobs']}")
print(f"  ratings_reviews       {ev['coverage']['ratings_reviews']}")
print(f"\n  viewer: {p.parent / (p.name + '-site') / 'index.html'}")
print(f"  eval:    {p.parent / (p.name + '.external-eval.json')}")
print(f"  labels:  {p.parent / (p.name + '.labels.jsonl')}")
PY
