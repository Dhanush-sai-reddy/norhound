#!/usr/bin/env bash
#
# promote_run.sh — turn one finished run into the submission package.
#
# Copies the verified artifacts of a run into `out/submission/` under the
# canonical names the submission email and the package README refer to,
# writes a README with the numbers actually measured for that run, and builds
# `out/norhound-signalpost-submission.zip`.
#
# Nothing is recomputed here: the run must already have passed
# `finalize_run.sh` (or `run_full_batch.sh`) so that eval-final.json reports
# entity_precision 1.0 and zero wrong-entity publications. The script refuses
# to promote a corpus that fails those two gates.
#
# Usage:
#   RUN_ID=fresh-20261115T073743Z scripts/promote_run.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_ID="${RUN_ID:?set RUN_ID}"
SRC="out/run-$RUN_ID"
DEST="out/submission"
PKG="norhound-signalpost"
STAGE="out/package-$RUN_ID"

say() { printf '\n=== %s ===\n' "$*"; }

[[ -s "$SRC/envelopes-final.jsonl" ]] || { echo "missing $SRC/envelopes-final.jsonl"; exit 1; }
[[ -s "$SRC/eval-final.json" ]] || { echo "missing $SRC/eval-final.json"; exit 1; }

say "1. promotion gates"
python3 - "$SRC" <<'PY'
import json, sys
ev = json.load(open(f"{sys.argv[1]}/eval-final.json"))
precision = ev.get("entity_precision")
wrong = ev.get("wrong_entity_publications")
unsupported = ev.get("unsupported_publications")
print(f"entity_precision={precision} wrong_entity={wrong} unsupported={unsupported}")
if precision != 1.0 or wrong != 0:
    raise SystemExit("refusing to promote: precision gate failed")
if unsupported not in (0, None):
    raise SystemExit("refusing to promote: unsupported publications present")
PY

say "2. archive the previous package"
if [[ -d "$DEST" ]]; then
  PREV="${DEST}-prev"
  # A leftover ${DEST}-prev would otherwise make this a silent merge of the old
  # and new corpora, which is how a stale company page survives into the zip.
  [[ -d "$PREV" ]] && rm -rf "$PREV"
  mv "$DEST" "$PREV"
  echo "moved the previous package to $PREV"
fi
mkdir -p "$DEST"

say "3. copy the verified artifacts under their canonical names"
copy() {
  local from="$1" to="$2"
  [[ -s "$from" ]] || { echo "missing $from"; exit 1; }
  cp "$from" "$DEST/$to"
  printf '  %-26s %s\n' "$to" "$(du -h "$DEST/$to" | cut -f1)"
}
copy "$SRC/envelopes-final.jsonl"     envelopes.jsonl
copy "$SRC/external-final.jsonl"      observations.jsonl
copy "$SRC/labels-final.jsonl"        labels.jsonl
copy "$SRC/summaries.jsonl"           summaries.jsonl
copy "$SRC/eval-final.json"           eval.json
copy "$SRC/measure-final.json"        measure.json
copy "$SRC/measure-family-final.json" measure-family.json
copy "$SRC/entry.jsonl"               manifest.jsonl
# finalize_run.sh prefers the browser-rescued profiles when they exist, because
# that is the file the claims were derived from. Shipping profiles-promoted in
# that case would publish a different profile set from the one behind the
# evidence, so promote the same file finalize used.
if [[ -s "$SRC/batch-rescued-profiles.jsonl" ]]; then
  copy "$SRC/batch-rescued-profiles.jsonl" profiles-promoted.jsonl
else
  copy "$SRC/profiles-promoted.jsonl"      profiles-promoted.jsonl
fi
[[ -d "$SRC/site" ]] || { echo "missing $SRC/site"; exit 1; }
cp -r "$SRC/site" "$DEST/site"
echo "  site/                      $(du -sh "$DEST/site" | cut -f1)"

say "4. 100-company smoke test"
uv run python scripts/build_smoke_report.py \
  --run-dir "$SRC" --count 100 --output-dir "$DEST/smoke-100"

say "5. package README with this run's measured numbers"
python3 - "$DEST" "$RUN_ID" <<'PY'
import json, sys
from pathlib import Path

dest, run_id = Path(sys.argv[1]), sys.argv[2]
ev = json.loads((dest / "eval.json").read_text())
m = json.loads((dest / "measure.json").read_text())
fam = json.loads((dest / "measure-family.json").read_text())["family_company_recall"]

claims = evidence = 0
# A raw U+2028/U+2029 inside a JSON string is a line terminator to str.splitlines()
# and would abort the parse, so read line by line (which splits on \n only) and
# escape those two characters before decoding.
with (dest / "envelopes.jsonl").open(encoding="utf-8") as handle:
    for line in handle:
        if not line.strip():
            continue
        row = json.loads(
            line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        )
        claims += len(row.get("claims") or [])
        evidence += len(row.get("evidence") or [])

families = ", ".join(
    f"{name} {row['covered']}/{row['opportunities']}" for name, row in fam.items()
)

text = f"""# NorHound — Signalpost submission package

Generated from run `{run_id}` by `scripts/promote_run.sh`. Keyless corpus: no
API key, no login, no paid account; $0 per 100-company run.

| File | What it is |
|---|---|
| `envelopes.jsonl` | 1,000 terminal envelopes, one per organisation number: claims, the evidence behind every claim, run and operations sections |
| `observations.jsonl` | {ev.get('observations')} external observations with source URL, retrieval time, dates and content hash |
| `labels.jsonl` | The verifier's label per observation (`exact_entity` gates publication) |
| `summaries.jsonl` | Deterministic per-company brief (no model, no key) |
| `eval.json` | Footprint score: entity precision, wrong-entity publications, coverage |
| `measure.json` | The six-field recall proxy used to compare runs |
| `manifest.jsonl` | The organisation-number manifest |
| `profiles-promoted.jsonl` | The frozen profiles the claims were derived from |
| `site/` | The static viewer: `index.html` (search/sort/compare), `c/<org>.html`, `c/<org>.json`, `companies.csv` |
| `smoke-100/` | The 100-company smoke test: `smoke-envelopes.jsonl` (one complete result per input) and `smoke-report.json` (requested vs returned, per-company claim/evidence counts) |

Checks on this package:

- entity precision {ev.get('entity_precision')}, {ev.get('wrong_entity_publications')} wrong-company publications, {ev.get('unsupported_publications')} unsupported publications
- {claims:,} claims backed by {evidence:,} evidence records
- published {ev.get('published_audited')} of {ev.get('observations')} observations
- every published fact carries source URL, retrieval time, reporting date,
  content hash and extraction method
- company recall per fact family: {families}
- six-field recall proxy {round(m.get('recall_proxy_50', 0), 2)} / 50

Reproduce: `scripts/run_fresh_pipeline.sh` (see the repository README).
"""
(dest / "README.md").write_text(text, encoding="utf-8")
print(text)
PY

say "6. build the package zip"
rm -rf "$STAGE"
mkdir -p "$STAGE/$PKG"
for item in "$DEST"/*; do
  cp -rl "$item" "$STAGE/$PKG/" 2>/dev/null || cp -r "$item" "$STAGE/$PKG/"
done
# `zip` updates an existing archive in place, so a stale zip would keep entries
# from a previous run that no longer exist.
rm -f "$ROOT/out/norhound-signalpost-submission.zip"
( cd "$STAGE" && zip -qr "$ROOT/out/norhound-signalpost-submission.zip" "$PKG" )
rm -rf "$STAGE"
ls -la out/norhound-signalpost-submission.zip | awk '{print $5, $9}'

say "done — package at out/submission and out/norhound-signalpost-submission.zip"
