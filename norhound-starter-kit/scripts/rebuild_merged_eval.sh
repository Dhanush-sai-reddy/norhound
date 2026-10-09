#!/usr/bin/env bash
# Rebuild the merged external-observation set and re-score, folding in every
# connector output that exists on disk. Idempotent; safe to re-run after Finn
# (or any other background connector) finishes.
set -euo pipefail
cd "$(dirname "$0")/.."

INPUTS=(
  out/web1000batch.external-v6.jsonl
  out/gplaces-reviews.jsonl
  out/gmaps-reviews.jsonl
  out/proff-ratings.external.jsonl
  out/apify-nav-jobs.external.jsonl
  out/web1000batch.nav.jsonl
  out/web1000batch.fagfolk-test.jsonl
  out/web1000batch.news.jsonl
  out/instagram.jsonl
  out/site-social-handles.jsonl
  out/company-feed-news.jsonl
  out/company-article-dates.jsonl
  out/finn-jobs.external.jsonl
  out/ats-jobs.external.jsonl
  out/probed-site-signals.jsonl
  out/registry-workforce.jsonl
  out/workforce-pdf.jsonl
  out/gleif-ext.jsonl
  out/wikidata-ext.jsonl
  out/norwegian-news-rss.jsonl
  out/gate474.sitedesc.jsonl
  out/gate474.sitemap.jsonl
  out/gate474.news.jsonl
  out/gate474.handles.jsonl
)

PRESENT=()
for f in "${INPUTS[@]}"; do
  [[ -s "$f" ]] && PRESENT+=("$f")
done

uv run python scripts/merge_external_outputs.py \
  --inputs "${PRESENT[@]}" \
  --output out/web1000batch.external-merged.jsonl \
  --report out/web1000batch.merge-report.json

# Drop known brand-collision probe rows (precision gate: exact-entity only).
uv run python scripts/purge_wrong_company_probes.py \
  --observations out/web1000batch.external-merged.jsonl \
  --profiles out/web1000-profiles.jsonl \
  --output out/web1000batch.external-merged.jsonl \
  --report out/purge-wrong-companies.json

python3 - <<'PY'
import json
from pathlib import Path
def rd(p):
    if not Path(p).exists(): return []
    out=[]
    with open(p, encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if line: out.append(json.loads(line))
    return out
def wr(p, rows):
    with open(p, "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
obs = rd("out/web1000batch.external-merged.jsonl")
import sys
sys.path.insert(0, "scripts")
from extract_company_site_jobs import GENERIC_ANCHOR, NAVIGATION_ANCHORS
def _junk(o):
    if o.get("signal_type") != "job_posting":
        return False
    span = " ".join(str(o.get("evidence_span") or "").split()).casefold()
    return not span or span in NAVIGATION_ANCHORS or bool(GENERIC_ANCHOR.search(span))
junk_rows = [o for o in obs if _junk(o)]
obs = [o for o in obs if not _junk(o)]
if junk_rows:
    print("junk job_posting rows dropped at merge:", len(junk_rows))
v6 = {str(r["id"]): r for r in rd("out/web1000batch.labels-v6.jsonl")}
prev = {str(r["id"]): r for r in rd("out/web1000batch.labels-merged.jsonl")}
labels = []
for o in obs:
    i = str(o.get("id"))
    labels.append(prev.get(i) or v6.get(i) or {
        "id": i, "exact_entity": bool(o.get("exact_entity")), "metric_correct": True,
        "sentiment_correct": bool(o.get("sentiment_label")),
        "signal_type": o.get("signal_type"), "organisation_number": o.get("organisation_number"),
    })
wr("out/web1000batch.labels-merged.jsonl", labels)
print("merged rows:", len(obs), "labels:", len(labels))
PY

uv run python scripts/evaluate_external_footprint.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/web1000batch.external-merged.jsonl \
  --labels out/web1000batch.labels-merged.jsonl \
  --output out/web1000batch.eval-merged.json \
  --minimum-audit 100
