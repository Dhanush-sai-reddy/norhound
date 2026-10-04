#!/usr/bin/env python3
"""One-shot Signalpost submission pipeline runner.

Single command to produce your submission artifacts:
  - out/submission/profiles.jsonl (1,000 companies)
  - out/submission/envelopes.jsonl (enriched terminal envelopes)
  - out/submission/manifest.jsonl (org number manifest)
  - out/submission/summaries.jsonl (deterministic answers)
  - out/submission/site/ (HTML viewer)
  - out/submission/eval.json (footprint score report)

Pre-computed data that MUST exist before running:
  data/nav-job-index.jsonl     (built once: run_nav_job_feed_connector.py --build-index)
  data/wikidata-index.jsonl    (built once: run_wikidata_connector.py --build-index)

Pre-computed data merged via --external-data (optional, one-shot before submission):
  data/apify-jobs.jsonl        (store_apify_jobs.py)
  data/gulesider-ratings.jsonl (store_gulesider_ratings.py)

Usage:
  # First:one-time Apify pre-compute
  # apify run yearly_register/norway-jobs-search-api ... && store_apify_jobs.py ...
  # apify run crawlerbros/gulesider-scraper ... && store_gulesider_ratings.py ...

  # Then: build indexes (once, free)
  uv run python scripts/run_wikidata_connector.py --build-index --organisations data/entry-manifest.jsonl --index data/wikidata-index.jsonl --workers 24
  uv run python scripts/run_nav_job_feed_connector.py --build-index --index data/nav-job-index.jsonl --days 183 --workers 24
  uv run python scripts/run_nav_job_feed_connector.py --resolve-parents --index data/nav-job-index.jsonl --workers 24

  # Then: THE SUBMISSION COMMAND (one line, one shot)
  uv run python scripts/run_one_shot.py \
    --out out/submission \
    --external-data "data/apify-jobs.jsonl,data/gulesider-ratings.jsonl"
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    argv = [sys.executable, *cmd[1:]] if cmd and cmd[0] == "python" else cmd
    result = subprocess.run(argv, cwd=cwd or ROOT, capture_output=True, text=True)
    if result.stdout and result.stdout.strip():
        print(result.stdout, flush=True)
    if result.stderr and result.returncode != 0:
        print(result.stderr, file=sys.stderr, flush=True)
    if result.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(argv)}: exit {result.returncode}")


def main():
    p = argparse.ArgumentParser(description="One-shot Signalpost submission pipeline")
    p.add_argument("--out", required=True, type=Path, help="Output root, e.g. out/submission")
    p.add_argument("--profiles", type=Path, default=DATA / "entry-manifest.jsonl")
    p.add_argument("--batch-size", type=int, default=1000)
    p.add_argument("--external-data", default=None, help="Comma-separated pre-computed observation JSONL paths to merge")
    p.add_argument("--nav-index", type=Path, default=DATA / "nav-job-index.jsonl")
    p.add_argument("--wikidata-index", type=Path, default=DATA / "wikidata-index.jsonl")
    p.add_argument("--skip-external", action="store_true", help="Skip external pipeline (use existing output)")
    p.add_argument("--skip-batch", action="store_true", help="Skip base batch (use existing profiles)")
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    profiles = out / "profiles.jsonl"
    envelopes = out / "envelopes.jsonl"
    batch_prefix = out / "batch"

    # ── Phase 1: Base batch (always need fresh profiles if not exists)
    if not args.skip_batch:
        print("════ BASE BATCH ════")
        run([
            "python", str(SCRIPTS / "run_competition_batch.py"),
            "--batch-size", str(args.batch_size),
            "--output-dir", str(out),
        ])
    else:
        print(f"Using cached profiles: {profiles}")

    # ── Phase 1b: Live Proff.no enrichment (works for any company batch; needs APIFY_TOKEN)
    proff_raw = DATA / "proff-latest.jsonl"
    proff_obs = DATA / "proff-ratings.external.jsonl"
    run([
        "python", str(SCRIPTS / "fetch_proff_live.py"),
        "--profiles", str(profiles),
        "--output", str(proff_raw),
    ])
    if proff_raw.exists() and proff_raw.stat().st_size > 0:
        run([
            "python", str(SCRIPTS / "store_proff_ratings.py"),
            "--input", str(proff_raw),
            "--output", str(proff_obs),
        ])

    # ── Phase 2: External pipeline
    external_out = batch_prefix.with_suffix(".external.jsonl")
    if not args.skip_external:
        print("════ EXTERNAL PIPELINE ════")
        cmd = [
            "python", str(SCRIPTS / "run_external_pipeline.py"),
            "--profiles", str(profiles),
            "--envelopes", str(envelopes),
            "--prefix", str(batch_prefix),
            "--jobs", "--reviews", "--keyless", "--nav",
            "--nav-index", str(args.nav_index),
            "--wikidata-index", str(args.wikidata_index),
        ]
        # Pass pre-computed + live-fetched data into the pipeline's consolidation step
        externals = []
        if args.external_data:
            externals.append(args.external_data)
        if proff_obs.exists() and proff_obs.stat().st_size > 0:
            externals.append(str(proff_obs))
        if externals:
            cmd += ["--external-data", ",".join(externals)]
        run(cmd)
    else:
        print(f"Using cached external output: {external_out}")

    # ── Phase 3: Verify + evaluate
    labels = batch_prefix.with_suffix(".labels.jsonl")
    eval_out = batch_prefix.with_suffix(".eval.json")
    report = batch_prefix.with_suffix(".label-report.json")

    print("════ VERIFY + EVALUATE ════")
    run([
        "python", str(SCRIPTS / "verify_and_label_observations.py"),
        "--profiles", str(profiles),
        "--observations", str(external_out),
        "--labels", str(labels),
        "--report", str(report),
    ])
    run([
        "python", str(SCRIPTS / "evaluate_external_footprint.py"),
        "--profiles", str(profiles),
        "--observations", str(external_out),
        "--labels", str(labels),
        "--output", str(eval_out),
        "--minimum-audit", "300",
    ])

    # ── Phase 4: Deterministic summaries
    summaries = out / "summaries.jsonl"
    print("════ DETERMINISTIC SUMMARIES ════")
    run([
        "python", str(SCRIPTS / "build_deterministic_summaries.py"),
        "--envelopes", str(envelopes),
        "--profiles", str(profiles),
        "--output", str(summaries),
    ])

    # ── Phase 5: Viewer
    site_dir = out / "site"
    print("════ BUILD VIEWER ════")
    site_cmd = [
        "python", str(SCRIPTS / "build_static_site.py"),
        "--envelopes", str(envelopes),
        "--summaries", str(summaries),
        "--out", str(site_dir),
    ]
    if eval_out.exists():
        site_cmd += ["--eval", str(eval_out)]
    run(site_cmd)

    # ── Manifest
    if profiles.exists():
        orgs = [
            json.loads(l).get("organisation_number")
            for l in profiles.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        (out / "manifest.jsonl").write_text(
            "\n".join(json.dumps({"organisation_number": org}) for org in orgs) + "\n",
            encoding="utf-8",
        )

    print("\n═══════ SUBMISSION READY ═══════")
    print(f"  profiles:    {profiles} ({sum(1 for _ in profiles.open()) if profiles.exists() else 0})")
    print(f"  envelopes:   {envelopes}")
    print(f"  manifest:    {out / 'manifest.jsonl'}")
    print(f"  summaries:   {summaries}")
    print(f"  eval:        {eval_out}")
    print(f"  viewer:      {site_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
