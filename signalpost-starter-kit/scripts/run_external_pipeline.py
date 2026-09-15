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


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def run(command: list[str]) -> None:
    argv = [sys.executable, *command[1:]] if command and command[0] == "python" else command
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
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
    parser.add_argument("--promote", action="store_true", help="Promote discovered sites into canonical website evidence")
    parser.add_argument("--discovery-provider", default="firecrawl", choices=["firecrawl", "duckduckgo"], help="Free keyless DuckDuckGo HTML discovery or Firecrawl Search API")
    parser.add_argument("--api-key-env", default="FIRECRAWL_API_KEY")
    parser.add_argument("--harvest-linkedin-local", action="store_true", help="Run local logged-out LinkedIn company-page harvest (no API key, experimental rights)")
    parser.add_argument("--harvest-reddit-free", action="store_true", help="Run free Reddit OAuth mention connector (requires REDDIT_CLIENT_ID/SECRET; abstains otherwise)")
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
        discovery_script = "run_firecrawl_discovery.py" if args.discovery_provider == "firecrawl" else "run_duckduckgo_discovery.py"
        discovery_command = [
            "python", str(SCRIPTS / discovery_script),
            "--input", args.discovery_input,
            "--output", str(discovery_out),
            "--report", str(prefix.with_suffix(prefix.suffix + ".discovery-report.json")),
            "--limit", str(limit),
            "--count", "5" if args.discovery_provider == "firecrawl" else "8",
            "--timeout", "20",
            "--min-interval", "2.0",
            "--promote-verified",
        ]
        if args.discovery_provider == "firecrawl":
            discovery_command += ["--max-429-backoff", "45"]
        run(discovery_command)

    observation_files = [activity_out, news_out, jobs_out]
    if discovery_out.exists():
        observation_files.append(discovery_out)
    linkedin_out = prefix.with_suffix(prefix.suffix + ".linkedin.jsonl")
    reddit_out = prefix.with_suffix(prefix.suffix + ".reddit.jsonl")
    handles_out = prefix.with_suffix(prefix.suffix + ".handles.jsonl")
    if args.harvest_linkedin_local:
        handles = [
            item
            for item in (json.loads(line) for line in activity_out.read_text(encoding="utf-8").splitlines() if line.strip())
            if item.get("signal_type") == "profile_handle" and str(item.get("platform")).casefold() == "linkedin"
        ]
        for handle in handles:
            handle["profile_url"] = (handle.get("metrics") or {}).get("url") or handle.pop("source_url", "") or ""
        handles_out.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in handles), encoding="utf-8")
        cache_dir = Path(args.envelopes).parent / f"{prefix.name}.linkedin-cache"
        run([
            "python", str(SCRIPTS / "run_linkedin_guest_experiment.py"),
            "--profiles", args.profiles,
            "--handles", str(handles_out),
            "--output", str(linkedin_out),
            "--report", str(prefix.with_suffix(prefix.suffix + ".linkedin-report.json")),
            "--cache-dir", str(cache_dir),
            "--delay", "1.0",
            "--timeout", "20",
        ])
        observation_files.append(linkedin_out)
    if args.harvest_reddit_free:
        run([
            "python", str(SCRIPTS / "run_reddit_mentions_connector.py"),
            "--profiles", args.profiles,
            "--output", str(reddit_out),
            "--report", str(prefix.with_suffix(prefix.suffix + ".reddit-report.json")),
            "--limit", "10",
            "--min-interval", "0.8",
            "--timeout", "20",
        ])
        observation_files.append(reddit_out)
    existing = [str(path) for path in observation_files if path.exists() and path.stat().st_size > 0]

    consolidated = []
    for path in existing:
        for line in sanitize_line_separators(Path(path).read_text(encoding="utf-8")).splitlines():
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