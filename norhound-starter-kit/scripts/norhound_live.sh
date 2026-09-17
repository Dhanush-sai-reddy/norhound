#!/usr/bin/env bash
# NorHound full live pipeline inside the container.
# Mirrors README "Reproduce": download registry + universe, build the shipped
# website-only 1,000-company manifest, run base + external pipelines.
# The publicity guard in select_entry_batch.py rejects any manifest below
# 1,000 companies, so this replicates the shipped 1,000-company run. Set
# COUNT=1000 EXPECTED=1000 (the defaults) for the submission-scale run; the
# container only needs Docker installed -- Python/uv live inside the image.
set -euo pipefail
cd "$(dirname "$0")/.."

COUNT="${COUNT:-1000}"
EXPECTED="${EXPECTED:-$COUNT}"

echo "== step 0: dependencies =="
uv sync --frozen

echo "== step 1: download registry + universe (idempotent) =="
mkdir -p data
if [ ! -s data/brreg-enheter.csv ]; then
  curl -L --fail --retry 3 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' -o data/brreg-enheter.csv
fi
if [ ! -s data/norhound-universe.jsonl.gz ]; then
  curl -L --fail --retry 3 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' -o data/norhound-universe.jsonl.gz
fi

echo "== step 2: manifest (website-only batch, seed 20260823) =="
uv run python select_entry_batch.py \
  --universe data/norhound-universe.jsonl.gz \
  --count "$COUNT" \
  --seed 20260823 \
  --website-only \
  --bulk data/brreg-enheter.csv \
  --output data/entry-manifest.jsonl

echo "== step 3: base batch =="
uv run python scripts/run_competition_batch.py \
  --organisations data/entry-manifest.jsonl \
  --bulk data/brreg-enheter.csv \
  --profiles-output data/profiles.jsonl \
  --output data/envelopes.jsonl \
  --report data/run-report.json \
  --run-id docker-live \
  --expected-count "$EXPECTED"

echo "== step 4: external-footprint pipeline =="
uv run python scripts/run_external_pipeline.py \
  --profiles data/profiles.jsonl \
  --envelopes data/envelopes.jsonl \
  --prefix data/batch \
  --jobs --reviews

echo "== done =="
echo "Manifest:  data/entry-manifest.jsonl"
echo "Profiles:  data/profiles.jsonl"
echo "Envelopes: data/envelopes.jsonl"
echo "Report:    data/run-report.json"