#!/usr/bin/env python3
"""Sealed external-footprint stage: run site connectors, discovery, and envelope assembly.

For a completed competition batch, this runs:
  1. company-site activity/news/jobs extractors on the frozen profiles
  2. optional Firecrawl discovery for missing-website companies (resumable)
  3. envelope assembly attaching publishable observations to terminal envelopes
  4. an observation-level footprint report

The stage is deterministic given frozen profiles and JSONL inputs. Missing or
empty connector outputs are allowed (valid zero-result stages).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"stage failed: {' '.join(command)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sealed external-footprint pipeline for a completed batch.")
    parser.add_argument("--profiles", required=True, help="Frozen batch profiles JSONL")
    parser.add_argument("--envelopes", required=True, help="Terminal envelopes JSONL")
    parser.add_argument("--prefix", required=True, help="Output prefix, e.g. out/batch1000")
    parser.add_argument("--discovery-input", default=None, help="Optional discovery candidate JSONL (for missing-website orgs)")
    parser.add_argument("--discovery-limit", type=int, default=0, help="Max discovery queries (0 = auto all missing-website)")
    parser.add_argument("--jobs", action="store_true", help="Run the jobs extractor (network) ")
    parser.add_argument("--promote", action="store_true", help="Promote Firecrawl-verified sites into canonical website evidence")
    parser.add_argument("--api-key-env", default="FIRECRAWL_API_KEY")
    args = parser.parse_args()

    prefix = Path(args.prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    activity_out = prefix.with_suffix(prefix.suffix + ".activity.jsonl")
    news_out = prefix.with_suffix(prefix.suffix + ".news.jsonl")
    jobs_out = prefix.with_suffix(prefix.suffix + ".jobs.jsonl")
    discovery_out = prefix.with_suffix(prefix.suffix + ".discovery.jsonl")
    external_out = prefix.with_suffix(prefix.suffix + ".external.jsonl")
    enriched_out = prefix.with_suffix(prefix.suffix + ".enriched.jsonl")
    eval_out = prefix.with_suffix(prefix.suffix + ".external-eval.json")

    run([
        "python", str(SCRIPTS / "extract_company_site_activity.py"),
        "--profiles", args.profiles,
        "--output", str(activity_out),
        "--report", str(prefix.with_suffix(prefix.suffix + ".activity-report.json")),
    ])
    run([
        "python", str(SCRIPTS / "extract_company_site_news.py"),
        "--profiles", args.profiles,
        "--output", str(news_out),
        "--report", str(prefix.with_suffix(prefix.suffix + ".news-report.json")),
    ])
    if args.jobs:
        run([
            "python", str(SCRIPTS / "extract_company_site_jobs.py"),
            "--profiles", args.profiles,
            "--output", str(jobs_out),
            "--report", str(prefix.with_suffix(prefix.suffix + ".jobs-report.json")),
            "--workers", "8",
            "--timeout", "20",
            "--min-interval", "0.5",
        ])

    if args.discovery_input and args.promote:
        discovery_candidates = [json.loads(line) for line in Path(args.discovery_input).read_text(encoding="utf-8").splitlines() if line.strip()]
        missing = sum(1 for row in discovery_candidates if not row.get("website"))
        limit = args.discovery_limit or missing
        run([
            "python", str(SCRIPTS / "run_firecrawl_discovery.py"),
            "--input", args.discovery_input,
            "--output", str(discovery_out),
            "--report", str(prefix.with_suffix(prefix.suffix + ".discovery-report.json")),
            "--limit", str(limit),
            "--count", "5",
            "--timeout", "20",
            "--min-interval", "2.0",
            "--max-429-backoff", "45",
            "--promote-verified",
        ])

    observation_files = [activity_out, news_out, jobs_out]
    if discovery_out.exists():
        observation_files.append(discovery_out)
    existing = [str(path) for path in observation_files if path.exists() and path.stat().st_size > 0]

    consolidated = []
    for path in existing:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                consolidated.append(json.loads(line))
    external_out = prefix.with_suffix(prefix.suffix + ".external.jsonl")
    external_out.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in consolidated), encoding="utf-8")

    run([
        "python", str(SCRIPTS / "attach_external_observations.py"),
        "--envelopes", args.envelopes,
        "--observations", *existing,
        "--output", str(enriched_out),
        "--report", str(prefix.with_suffix(prefix.suffix + ".enrich-report.json")),
    ])
    labels_path = prefix.with_suffix(prefix.suffix + ".labels.jsonl")
    if not labels_path.exists():
        labels_path.write_text("", encoding="utf-8")
    run([
        "python", str(SCRIPTS / "evaluate_external_footprint.py"),
        "--profiles", args.profiles,
        "--observations", str(external_out),
        "--labels", str(labels_path),
        "--output", str(eval_out),
        "--minimum-audit", "0",
    ])
    print(json.dumps({"stage": "external_pipeline", "prefix": str(prefix), "observation_files": existing, "consolidated_observations": str(external_out), "note": "labels file is optional; eval runs with minimum-audit 0."}, indent=2))


if __name__ == "__main__":
    main()