#!/usr/bin/env bash
# Build the widest observation set the frozen evidence can still prove.
#
# Every connector output that exists on disk is unioned (deduped by id, first
# file wins), brand-collision probes are purged, and the identity gate is then
# re-run from scratch against the frozen profiles, so widening the input never
# widens what may be published.  Offline: no network, no keys, no cost.
set -euo pipefail
cd "$(dirname "$0")/.."

# Override to A/B a different identity gate or to write a comparison set aside.
PROFILES="${PROFILES:-out/web1000-profiles.jsonl}"
PREFIX="${PREFIX:-out/web1000batch}"

INPUTS=(
  # merged lineage first: it carries the real publication datetimes and the
  # largest social-handle set
  out/web1000batch.external-merged.jsonl
  out/web1000batch.external.jsonl
  out/keyless-nav-all.external.jsonl
  out/norhound.external.jsonl
  out/batch.external.jsonl
  # dated news with true publication timestamps
  out/company-feed-news.jsonl
  out/company-feed-news.offsets.jsonl
  out/company-article-dates.jsonl
  out/web1000batch.feed-news.jsonl
  out/web1000batch_newconnectors.feed-news.jsonl
  out/web1000batch.news.jsonl
  out/gate474.news.jsonl
  out/norwegian-news-rss.jsonl
  out/google-news.jsonl
  out/web1000batch.google-news.jsonl
  # hiring
  out/web1000batch.careers.jsonl
  out/web1000batch.nav.jsonl
  out/nav-all.jsonl
  out/finn-jobs.external.jsonl
  out/ats-jobs.external.jsonl
  out/web1000batch.ats-jobs.jsonl
  out/apify-nav-jobs.external.jsonl
  out/web1000batch.jobs.jsonl
  out/jobs1000.ua-fixed.jsonl
  # social
  out/site-social-handles.jsonl
  out/web1000batch.handles.jsonl
  out/gate474.handles.jsonl
  out/web1000batch.activity.jsonl
  out/probed-site-signals.jsonl
  out/instagram.jsonl
  out/wikidata-ext.jsonl
  # reviews and ratings
  out/gplaces-reviews.jsonl
  out/gmaps-reviews.jsonl
  out/proff-ratings.external.jsonl
  out/web1000batch.fagfolk.jsonl
  out/web1000batch.fagfolk-test.jsonl
  # identity / workforce / structure
  out/gleif-ext.jsonl
  out/web1000batch.kunngjoring.jsonl
  out/web1000batch.sitedesc.jsonl
  out/gate474.sitedesc.jsonl
  out/web1000batch.sitemap.jsonl
  out/gate474.sitemap.jsonl
  out/web1000batch.substruct.jsonl
  out/web1000batch.contacts.jsonl
  out/web1000batch.updates.jsonl
  out/web1000batch.workforce-pdf.jsonl
  out/web1000batch.workforce-registry.jsonl
  # keyless public-sector connectors (TED EU procurement, research grants,
  # Brønnøysund state-aid register) - official APIs, no keys required
  out/submission/batch.ted.jsonl
  out/submission/batch.forskningsradet.jsonl
  out/submission/batch.stotte.jsonl
)

PRESENT=()
for f in "${INPUTS[@]}"; do
  [[ -s "$f" ]] && PRESENT+=("$f")
done
echo "unioning ${#PRESENT[@]} observation files"

uv run python scripts/merge_external_outputs.py \
  --inputs "${PRESENT[@]}" \
  --output "$PREFIX.external-superset.jsonl" \
  --report "$PREFIX.superset-report.json"

uv run python scripts/purge_wrong_company_probes.py \
  --observations "$PREFIX.external-superset.jsonl" \
  --profiles "$PROFILES" \
  --output "$PREFIX.external-superset.jsonl" \
  --report "$PREFIX.purge-superset.json"

# Re-derive every label from the frozen evidence; nothing is inherited.
uv run python scripts/verify_and_label_observations.py \
  --profiles "$PROFILES" \
  --observations "$PREFIX.external-superset.jsonl" \
  --labels "$PREFIX.labels-superset.jsonl" \
  --report "$PREFIX.labels-superset-report.json"

uv run python scripts/emit_contract_envelope.py \
  --profiles "$PROFILES" \
  --observations "$PREFIX.external-superset.jsonl" \
  --labels "$PREFIX.labels-superset.jsonl" \
  --output "$PREFIX.contract-superset.jsonl" \
  --report "$PREFIX.contract-superset-report.json"
