#!/usr/bin/env bash
# Recover the highest-recall corpus and ship it as the submission.
#
# What this session established:
#   * The best measured recall proxy is 40.33/50 (out/frozen/measure-all+purehelp.json)
#     built from out/frozen/candidate-all+purehelp.external.jsonl (68,355 rows).
#   * The shipped submission scores 30.13/50 because the keyless corpus lost the
#     review/sentiment rows (Google Places is excluded by source policy) and never
#     ran the Purehelp directory connector, which is keyless and org-number keyed.
#   * Purehelp alone lifted two_platforms 0.624 -> 1.0 and the whole proxy to 40.33.
#
# So: one pipeline = candidate-all + purehelp, re-verified, re-labelled, measured.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/norhound-starter-kit"

OUT="${OUT:-out/frozen}"
mkdir -p "$OUT"

echo "=== 1. profiles for the frozen corpus ==="
# The frozen corpus was built against the shipped 1,000-company profile set.
PROFILES="out/submission/profiles-promoted.jsonl"
[ -s "$PROFILES" ] || { echo "missing $PROFILES"; exit 1; }

echo "=== 2. run the keyless Purehelp directory connector (not wired into the pipeline yet) ==="
uv run python scripts/run_purehelp_directory_connector.py \
  --profiles "$PROFILES" \
  --organisations "$OUT/purehelp-orgs.txt" \
  --output "$OUT/purehelp.external.jsonl" \
  --cache "$OUT/purehelp-cache" \
  --report "$OUT/purehelp-report.json" \
  --workers 8 \
  --min-interval 0.2

echo "=== 3. merge candidate-all + purehelp ==="
uv run python scripts/merge_external_outputs.py \
  --inputs "$OUT/candidate-all.external.jsonl" "$OUT/purehelp.external.jsonl" \
  --output "$OUT/candidate-all+purehelp.external.jsonl" \
  --report "$OUT/merge-purehelp-report.json" \
  --exclude-hosts proff.no google.com google.no \
  --dedupe-latest

echo "=== 4. purge wrong-company probes ==="
uv run python scripts/purge_wrong_company_probes.py \
  --observations "$OUT/candidate-all+purehelp.external.jsonl" \
  --profiles "$PROFILES" \
  --output "$OUT/candidate-all+purehelp.external.jsonl" \
  --report "$OUT/purge-report.json"

echo "=== 5. re-verify every observation against frozen evidence ==="
uv run python scripts/verify_and_label_observations.py \
  --profiles "$PROFILES" \
  --observations "$OUT/candidate-all+purehelp.external.jsonl" \
  --labels "$OUT/labels-all+purehelp.jsonl" \
  --report "$OUT/verify-report.json"

echo "=== 6. evaluate ==="
uv run python scripts/evaluate_external_footprint.py \
  --profiles "$PROFILES" \
  --observations "$OUT/candidate-all+purehelp.external.jsonl" \
  --labels "$OUT/labels-all+purehelp.jsonl" \
  --output "$OUT/eval-all+purehelp.json" \
  --minimum-audit 300

echo "=== 7. measure the recall proxy ==="
uv run python scripts/measure_recall.py \
  --profiles "$PROFILES" \
  --observations "$OUT/candidate-all+purehelp.external.jsonl" \
  --labels "$OUT/labels-all+purehelp.jsonl" \
  --output "$OUT/measure-all+purehelp.json" \
  --minimum-audit 300

echo "=== 8. emit the terminal envelopes ==="
uv run python scripts/emit_contract_envelope.py \
  --profiles "$PROFILES" \
  --envelopes out/submission/envelopes.jsonl \
  --observations "$OUT/candidate-all+purehelp.external.jsonl" \
  --labels "$OUT/labels-all+purehelp.jsonl" \
  --output "$OUT/envelopes-all+purehelp.jsonl" \
  --report "$OUT/envelope-report-all+purehelp.json"

echo "=== 9. deterministic summaries ==="
uv run python scripts/build_deterministic_summaries.py \
  --envelopes "$OUT/envelopes-all+purehelp.jsonl" \
  --output "$OUT/summaries-all+purehelp.jsonl" \
  --report "$OUT/summaries-report-all+purehelp.json"

echo "=== 10. static viewer ==="
uv run python scripts/build_static_site.py \
  --envelopes "$OUT/envelopes-all+purehelp.jsonl" \
  --summaries "$OUT/summaries-all+purehelp.jsonl" \
  --labels "$OUT/labels-all+purehelp.jsonl" \
  --observations "$OUT/candidate-all+purehelp.external.jsonl" \
  --eval "$OUT/eval-all+purehelp.json" \
  --out "$OUT/site-all+purehelp"

echo "=== 11. family recall (official fact families) ==="
uv run python scripts/measure_family_recall.py \
  --envelopes "$OUT/envelopes-all+purehelp.jsonl" \
  --output "$OUT/measure-family-all+purehelp.json"

echo "=== 12. promote into out/submission if the gates hold ==="
python3 - <<'PY'
import json, pathlib, shutil
out = pathlib.Path("out/frozen")
ev = json.loads((out / "eval-all+purehelp.json").read_text())
print("entity_precision:", ev.get("entity_precision"))
print("wrong_entity_publications:", ev.get("wrong_entity_publications"))
print("unsupported_publications:", ev.get("unsupported_publications"))
print("coverage:", ev.get("coverage"))
m = json.loads((out / "measure-all+purehelp.json").read_text())
print("recall_proxy_50:", m.get("recall_proxy_50"))
if ev.get("entity_precision", 0) >= 0.95 and ev.get("wrong_entity_publications", 1) == 0:
    print("GATES PASSED — promote with: bash scripts/promote_submission.sh")
else:
    print("GATES FAILED — do NOT promote")
PY

echo "=== DONE ==="
