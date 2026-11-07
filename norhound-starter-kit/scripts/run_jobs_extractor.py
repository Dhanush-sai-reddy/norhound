#!/usr/bin/env python3
"""Run jobs extraction using the competitor-grade jobs_extractor."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.jobs_extractor import extract_job_observations


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract job postings from verified company websites.")
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    all_obs = []
    for p in profiles:
        all_obs.extend(extract_job_observations(p))
    Path(args.output).write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in all_obs), encoding="utf-8")
    report = {
        "connector": "jobs_extractor_v1",
        "profiles": len(profiles),
        "observations": len(all_obs),
        "companies": len(set(o["organisation_number"] for o in all_obs)),
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
