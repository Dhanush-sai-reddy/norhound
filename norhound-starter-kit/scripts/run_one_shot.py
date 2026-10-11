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
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"


QUOTA_ERRORS = (429, 403, 503)  # HTTP status codes indicating quota/rate limit


def run(cmd: list[str], cwd: Path | None = None, allow_quota: bool = False) -> tuple[int, str, str]:
    """Run command, optionally allowing quota errors to pass through gracefully.
    Returns (returncode, stdout, stderr). If allow_quota=True and quota error detected,
    returns (0, stdout, stderr) instead of exiting.
    """
    argv = [sys.executable, *cmd[1:]] if cmd and cmd[0] == "python" else cmd
    result = subprocess.run(argv, cwd=cwd or ROOT, capture_output=True, text=True, timeout=3600)
    if result.stdout and result.stdout.strip():
        print(result.stdout, flush=True)
    if result.stderr and result.returncode != 0:
        print(result.stderr, file=sys.stderr, flush=True)
    
    # Check for quota exhaustion in stderr/stdout
    quota_hit = any(str(code) in (result.stdout + result.stderr) for code in QUOTA_ERRORS)
    quota_hit = quota_hit or any(keyword in (result.stdout + result.stderr).lower() 
                                 for keyword in ("quota", "rate limit", "exceeded", "429", "403"))
    
    if result.returncode != 0:
        if allow_quota and quota_hit:
            print(f"⚠️  Quota/rate-limit detected — skipping gracefully: {' '.join(argv)}", flush=True)
            return 0, result.stdout, result.stderr
        raise SystemExit(f"FAILED: {' '.join(argv)}: exit {result.returncode}")
    return result.returncode, result.stdout, result.stderr


def run_with_fallback(cmd: list[str], fallback_msg: str, cwd: Path | None = None) -> None:
    """Run command; if quota error, log fallback and continue."""
    try:
        run(cmd, cwd=cwd, allow_quota=True)
    except SystemExit as e:
        if "FAILED" in str(e):
            print(f"⚠️  {fallback_msg} — continuing without it", flush=True)
        else:
            raise


def main():
    p = argparse.ArgumentParser(description="One-shot Signalpost submission pipeline")
    p.add_argument("--out", required=True, type=Path, help="Output root, e.g. out/submission")
    p.add_argument("--profiles", type=Path, default=DATA / "entry-manifest.jsonl")
    p.add_argument("--batch-size", type=int, default=1000)
    p.add_argument("--external-data", default=None, help="Comma-separated pre-computed observation JSONL paths to merge")
    p.add_argument("--nav-index", type=Path, default=DATA / "nav-job-index.jsonl")
    p.add_argument("--wikidata-index", type=Path, default=DATA / "wikidata-index.jsonl")
    p.add_argument("--gleif-index", type=Path, default=DATA / "gleif-index.jsonl")
    p.add_argument("--skip-gleif-index", action="store_true", help="Do not build the GLEIF Brønnøysund LEI index if absent")
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
        bulk_file = DATA / "brreg-enheter.csv"
        batch_report = out / "batch-report.json"
        run([
            "python", str(SCRIPTS / "run_competition_batch.py"),
            "--organisations", str(DATA / "entry-manifest-filtered.jsonl"),
            "--bulk", str(bulk_file),
            "--output", str(envelopes),
            "--profiles-output", str(profiles),
            "--report", str(batch_report),
            "--run-id", "batch-001",
        ])
    else:
        print(f"Using cached profiles: {profiles}")

    # ── Phase 1b: Live Proff.no enrichment (works for any company batch; needs APIFY_TOKEN)
    # Gracefully skips if APIFY_TOKEN unset or quota exhausted
    proff_raw = DATA / "proff-latest.jsonl"
    proff_obs = DATA / "proff-ratings.external.jsonl"
    run_with_fallback([
        "python", str(SCRIPTS / "fetch_proff_live.py"),
        "--profiles", str(profiles),
        "--output", str(proff_raw),
    ], "Proff.no live fetch (APIFY quota/unset)", cwd=ROOT)
    if proff_raw.exists() and proff_raw.stat().st_size > 0:
        run([
            "python", str(SCRIPTS / "store_proff_ratings.py"),
            "--input", str(proff_raw),
            "--output", str(proff_obs),
        ])

    # ── Phase 1b: GLEIF LEI index (one-off; idempotent). Gives exact org-number -> LEI joins.
    if not args.skip_gleif_index and not args.gleif_index.exists():
        print("════ GLEIF INDEX BUILD ════")
        run([
            "python", str(SCRIPTS / "run_gleif_connector.py"),
            "--build-index",
            "--index", str(args.gleif_index),
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
            "--jobs", "--reviews", "--keyless", "--nav", "--google-news", "--kunngjoring", "--gleif",
            "--nav-index", str(args.nav_index),
            "--wikidata-index", str(args.wikidata_index),
            "--gleif-index", str(args.gleif_index),
        ]
        # Add Google Places if key available (skips gracefully if quota exhausted)
        if os.environ.get("GOOGLE_PLACES_KEY"):
            cmd += ["--google-places"]
            print("Google Places key found — enabling connector (quota-fallback enabled)")
        else:
            print("No GOOGLE_PLACES_KEY — skipping Google Places connector (credential-free fallback)")
        
        # Pass pre-computed + live-fetched data into the pipeline's consolidation step
        externals = []
        if args.external_data:
            externals.append(args.external_data)
        if proff_obs.exists() and proff_obs.stat().st_size > 0:
            externals.append(str(proff_obs))
        for extra in [
            out / "gplaces-reviews.jsonl",
            out / "gmaps-reviews.jsonl",
            out / "proff-profiles.jsonl",
            out / "instagram.jsonl",
            DATA / "gulesider-ratings.jsonl",
            DATA / "apify-jobs.jsonl",
            out / "site-social-handles.jsonl",
            out / "company-feed-news.jsonl",
            out / "company-article-dates.jsonl",
            out / "finn-jobs.external.jsonl",
            out / "ats-jobs.external.jsonl",
            out / "probed-site-signals.jsonl",
            out / "registry-workforce.jsonl",
            out / "workforce-pdf.jsonl",
            out / "gleif-ext.jsonl",
            out / "wikidata-ext.jsonl",
            out / "norwegian-news-rss.jsonl",
            out / "gate474.sitedesc.jsonl",
            out / "gate474.sitemap.jsonl",
            out / "gate474.news.jsonl",
            out / "gate474.handles.jsonl",
        ]:
            if extra.exists() and extra.stat().st_size > 0:
                externals.append(str(extra))
        if externals:
            cmd += ["--external-data", ",".join(externals)]
        run_with_fallback(cmd, "External pipeline (Google Places/Apify quota)", cwd=ROOT)
    else:
        print(f"Using cached external output: {external_out}")

    # Purge known wrong-company probes before verify/label (precision gate)
    print("════ PURGE WRONG-COMPANY PROBES ════")
    purge_cmd = [
        "python", str(SCRIPTS / "purge_wrong_company_probes.py"),
        "--observations", str(external_out),
        "--profiles", str(profiles),
        "--output", str(external_out),
        "--report", str(batch_prefix.with_suffix(".purge-report.json")),
    ]
    run(purge_cmd)

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
        "--output", str(summaries),
        "--report", str(out / "summaries-report.json"),
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
