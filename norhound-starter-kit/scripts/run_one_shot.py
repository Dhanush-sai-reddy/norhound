#!/usr/bin/env python3
"""One-shot Signalpost submission pipeline runner.

Fully live, credential-free. Collects everything from public sources within
the 45-minute / 2,000-request per 100-company budget — no pre-built files,
no API keys, no Apify, no Google Places.

Single command to produce your submission artifacts:
  - out/submission/profiles.jsonl (1,000 companies)
  - out/submission/envelopes.jsonl (enriched terminal envelopes)
  - out/submission/manifest.jsonl (org number manifest)
  - out/submission/summaries.jsonl (deterministic answers)
  - out/submission/site/ (HTML viewer)
  - out/submission/eval.json (footprint score report)

One-time index builds (free, run once):
  uv run python scripts/run_wikidata_connector.py --build-index --organisations data/entry-manifest.jsonl --index data/wikidata-index.jsonl --workers 24
  uv run python scripts/run_nav_job_feed_connector.py --build-index --index data/nav-job-index.jsonl --days 183 --workers 24
  uv run python scripts/run_nav_job_feed_connector.py --resolve-parents --index data/nav-job-index.jsonl --workers 24

Submission command:
  uv run python scripts/run_one_shot.py --out out/submission
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    argv = [sys.executable, *cmd[1:]] if cmd and cmd[0] == "python" else cmd
    result = subprocess.run(argv, cwd=cwd or ROOT, capture_output=True, text=True, timeout=3600)
    if result.stdout and result.stdout.strip():
        print(result.stdout, flush=True)
    if result.stderr and result.returncode != 0:
        print(result.stderr, file=sys.stderr, flush=True)
    if result.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(argv)}: exit {result.returncode}")


def main():
    p = argparse.ArgumentParser(description="One-shot Signalpost submission pipeline (live, credential-free)")
    p.add_argument("--out", required=True, type=Path, help="Output root, e.g. out/submission")
    p.add_argument("--profiles", type=Path, default=DATA / "entry-manifest.jsonl")
    p.add_argument("--batch-size", type=int, default=1000)
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

    # ── Phase 1: Base batch (live registry enrichment + exact-identity website capture)
    if not args.skip_batch:
        print("════ BASE BATCH ════")
        bulk_file = DATA / "brreg-enheter.csv"
        batch_report = out / "batch-report.json"
        run([
            "python", str(SCRIPTS / "run_competition_batch.py"),
            "--organisations", str(args.profiles),
            "--bulk", str(bulk_file),
            "--output", str(envelopes),
            "--profiles-output", str(profiles),
            "--report", str(batch_report),
            "--run-id", "batch-001",
        ])
    else:
        print(f"Using cached profiles: {profiles}")

    # ── Phase 1b: GLEIF LEI index (one-off; idempotent, free)
    if not args.skip_gleif_index and not args.gleif_index.exists():
        print("════ GLEIF INDEX BUILD ════")
        run([
            "python", str(SCRIPTS / "run_gleif_connector.py"),
            "--build-index",
            "--index", str(args.gleif_index),
        ])

    # ── Phase 2: External pipeline (all free, keyless connectors; live collection)
    external_out = batch_prefix.with_suffix(".external.jsonl")
    if not args.skip_external:
        print("════ EXTERNAL PIPELINE ════")
        cmd = [
            "python", str(SCRIPTS / "run_external_pipeline.py"),
            "--profiles", str(profiles),
            "--envelopes", str(envelopes),
            "--prefix", str(batch_prefix),
            "--jobs", "--reviews", "--keyless", "--nav", "--google-news", "--kunngjoring", "--gleif",
            "--nav-direct", "--brave-discovery", "--ats-jobs", "--smilefjes", "--feed-news",
            "--nav-index", str(args.nav_index),
            "--wikidata-index", str(args.wikidata_index),
            "--gleif-index", str(args.gleif_index),
        ]
        run(cmd)
    else:
        print(f"Using cached external output: {external_out}")

    # ── Phase 2.5: TED EU procurement (keyless)
    ted_out = str(batch_prefix) + ".ted.jsonl"
    print("════ TED EU PROCUREMENT ════")
    run([
        "python", str(SCRIPTS / "run_ted_connector.py"),
        "--organisations", str(args.profiles),
        "--output", ted_out,
        "--report", str(out / "ted-report.json"),
        "--batch-size", "100",
    ])

    # ── Phase 2.6: Støtteregisteret state aid (keyless)
    stotte_out = str(batch_prefix) + ".stotte.jsonl"
    print("════ STØTTEREGISTERET STATE AID ════")
    run([
        "python", str(SCRIPTS / "run_stotteregisteret_connector.py"),
        "--organisations", str(args.profiles),
        "--output", stotte_out,
        "--report", str(out / "stotteregisteret-report.json"),
        "--workers", "8",
    ])

    # ── Phase 2.8: Finanstilsynet financial licences (keyless)
    ft_out = str(batch_prefix) + ".finanstilsynet.jsonl"
    print("════ FINANSTILSYNET FINANCIAL LICENCES ════")
    run([
        "python", str(SCRIPTS / "run_finanstilsynet_connector.py"),
        "--organisations", str(args.profiles),
        "--output", ft_out,
        "--report", str(out / "finanstilsynet-report.json"),
        "--workers", "8",
    ])

    # ── Phase 2.9: Forskningsrådet research grants (keyless)
    rcn_out = str(batch_prefix) + ".forskningsradet.jsonl"
    print("════ FORSKNINGSRÅDET RESEARCH GRANTS ════")
    run([
        "python", str(SCRIPTS / "run_forskningsradet_connector.py"),
        "--organisations", str(args.profiles),
        "--output", rcn_out,
        "--report", str(out / "forskningsradet-report.json"),
    ])
    merged_out = str(batch_prefix) + ".external.merged.jsonl"
    print("════ MERGE EXTERNAL OBSERVATIONS ════")
    run([
        "python", str(SCRIPTS / "merge_external_outputs.py"),
        "--inputs", str(external_out), ted_out, stotte_out, ft_out, rcn_out,
        "--output", merged_out,
    ])

    # ── Phase 3: Verify + evaluate
    labels = batch_prefix.with_suffix(".labels.jsonl")
    eval_out = batch_prefix.with_suffix(".eval.json")
    report = batch_prefix.with_suffix(".label-report.json")

    print("════ VERIFY + EVALUATE ════")
    run([
        "python", str(SCRIPTS / "verify_and_label_observations.py"),
        "--profiles", str(profiles),
        "--observations", str(merged_out),
        "--labels", str(labels),
        "--report", str(report),
    ])
    run([
        "python", str(SCRIPTS / "evaluate_external_footprint.py"),
        "--profiles", str(profiles),
        "--observations", str(merged_out),
        "--labels", str(labels),
        "--output", str(eval_out),
        "--minimum-audit", "300",
    ])

    # ── Phase 3.5: Contract envelope emission (claims[] + evidence[] + snapshot_path)
    contract_out = str(batch_prefix) + ".contract.jsonl"
    snapshots_dir = str(out / "snapshots")
    print("════ CONTRACT ENVELOPES ════")
    run([
        "python", str(SCRIPTS / "emit_contract_envelope.py"),
        "--profiles", str(profiles),
        "--observations", str(merged_out),
        "--labels", str(labels),
        "--output", contract_out,
        "--envelopes", str(envelopes),
        "--snapshots-dir", snapshots_dir,
    ])

    # ── Phase 4: Deterministic summaries (no API key, no model calls)
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
