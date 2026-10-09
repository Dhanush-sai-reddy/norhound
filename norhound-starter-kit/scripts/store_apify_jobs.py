#!/usr/bin/env python3
"""Store Apify Norway job results in our observation pipeline format.

Reads Apify dataset output from yearly_register/norway-jobs-search-api
and writes JSONL compatible with the external pipeline consolidation step
(run_external_pipeline.py merges all *.{suffix}.jsonl in a prefix dir).

Usage:
  # From Apify dataset file
  uv run python scripts/store_apify_jobs.py \
    --apify-dataset /path/to/dataset.json \
    --profiles out/web1000-profiles.jsonl \
    --output data/apify-jobs.jsonl

  # From Apify API directly (requires token)
  uv run python scripts/store_apify_jobs.py \
    --apify-run-id AbCyXyZ123 \
    --profiles out/web1000-profiles.jsonl \
    --output data/apify-jobs.jsonl

The output format matches NorHound observation schema:
  organisation_number, signal_type, platform, source_url, retrieved_at,
  evidence_span, content_sha256, exact_entity, identity_proof,
  acquisition_mode, rights_status, source_class, metrics, id, strategy
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parentmkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _org_matches(obs: dict, profile: dict) -> bool:
    """Exact org number match, 9-digit, no padding mix-up."""
    obs_org = str(obs.get("organisation_number") or "").zfill(9)
    profile_org = str(profile.get("organisation_number") or "").zfill(9)
    return obs_org == profile_org and len(obs_org) == 9


def apify_job_to_observation(job: dict, profile: dict, *, strategy: str = "multi_source_job_api") -> dict | None:
    """
    Convert a multi-source API job result to our observation schema.

    Multi-source API returns: employerOrgNumber, company, title, description,
    publishedAt, applyUrl, sources[].url, sources[].source, matchScore, etc.

    Returns None if the job's employerOrgNumber doesn't match the profile's org number.
    """
    org = str(profile.get("organisation_number") or "").zfill(9)
    emp_org = str(job.get("employerOrgNumber") or "").zfill(9)

    if emp_org != org:
        return None  # Wrong company — never publish

    # Build evidence span from available fields
    parts = []
    if job.get("title"):
        parts.append(str(job["title"]))
    if job.get("location", {}).get("displayName"):
        parts.append(str(job["location"]["displayName"]))
    if job.get("publishedAt"):
        parts.append(f"posted {str(job['publishedAt'])[:10]}")
    evidence_span = " | ".join(parts) if parts else "Job listing"

    # Primary source URL (most authoritative)
    source_urls = [s.get("url") for s in (job.get("sources") or []) if s.get("url")]
    source_url = source_urls[0] if source_urls else None
    # Fallback to apply URL
    if not source_url and job.get("applyUrl"):
        source_url = str(job["applyUrl"])

    if not source_url:
        return None

    # Build identity proof
    proof = [
        {"type": "organisation_number_on_job_posting", "value": org},
    ]
    if job.get("company"):
        proof.append({"type": "employer_name_on_job_posting", "value": str(job["company"])})

    retrieved_at = _now()
    content = json.dumps(job, ensure_ascii=False, sort_keys=True)
    content_sha256 = sha256_hex(content)

    # Metrics: capture job details
    metrics = {}
    if job.get("publishedAt"):
        metrics["published_at"] = str(job["publishedAt"])
    if job.get("deadline"):
        metrics["deadline"] = str(job["deadline"])
    if job.get("employmentType"):
        metrics["employment_type"] = str(job["employmentType"])
    if job.get("workArrangement"):
        metrics["work_arrangement"] = str(job["workArrangement"])
    if job.get("location", {}).get("displayName"):
        metrics["location"] = str(job["location"]["displayName"])
    if job.get("applyUrl"):
        metrics["apply_url"] = str(job["applyUrl"])

    return {
        "id": f"apify-job-{org}-{sha256_hex(content)[:16]}",
        "organisation_number": org,
        "signal_type": "job_posting",
        "platform": "job_board",
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "observed_at": retrieved_at[:10],
        "content_sha256": content_sha256,
        "exact_entity": True,
        "identity_proof": proof,
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "official_api",
        "evidence_span": evidence_span[:500],
        "metrics": metrics,
        "strategy": strategy,
        "text": str(job.get("description") or evidence_span)[:5000],
    }


def apify_dataset_to_observations(
    apify_records: list[dict],
    profiles: list[dict],
) -> list[dict]:
    """Convert Apify dataset records to our observation schema."""
    # Build org number → profile map for fast lookup
    profile_map = {}
    for p in profiles:
        org = str(p.get("organisation_number") or "").zfill(9)
        if org not in profile_map:
            profile_map[org] = p

    observations = []
    seen_ids = set()

    for record in apify_records:
        # Skip error rows (Apify sometimes includes failed URLs)
        if record.get("error"):
            continue
        if record.get("canonicalJobId") is None and record.get("id"):
            # Some older actor versions use 'id' instead of 'canonicalJobId'
            record["canonicalJobId"] = record["id"]

        emp_org = str(record.get("employerOrgNumber") or "").zfill(9)
        profile = profile_map.get(emp_org)

        if not profile:
            continue  # Not in our batch

        obs = apify_job_to_observation(record, profile)
        if obs:
            obs_id = obs["id"]
            if obs_id not in seen_ids:
                seen_ids.add(obs_id)
                observations.append(obs)

    return observations


def sha256_hex(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Store Apify Norway job results in pipeline format.")
    parser.add_argument("--apify-dataset", type=Path, help="Path to Apify dataset JSONL file")
    parser.add_argument("--apify-run-id", type=str, help="Fetch dataset from Apify run ID (requires APIFY_TOKEN env var)")
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.apify_dataset and not args.apify_run_id:
        parser.error("Must specify either --apify-dataset or --apify-run-id")

    # Load profiles
    profiles = load_jsonl(Path(args.profiles))
    print(f"Loaded {len(profiles)} profiles")

    # Load Apify records
    if args.apify_dataset:
        records = load_jsonl(args.apify_dataset)
        print(f"Loaded {len(records)} Apify records from {args.apify_dataset}")
    else:
        # Fetch from Apify API
        try:
            import os, urllib.request
            token = os.environ.get("APIFY_TOKEN")
            if not token:
                raise SystemExit("APIFY_TOKEN env var required to fetch by run ID")
            dataset_url = f"https://api.apify.com/v2/actor-runs/{args.apify_run_id}/dataset/items"
            req = urllib.request.Request(dataset_url)
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=30) as resp:
                records = [json.loads(l) for l in resp.read().decode().splitlines() if l.strip()]
            print(f"Loaded {len(records)} Apify records from run {args.apify_run_id}")
        except Exception as e:
            raise SystemExit(f"Failed to fetch Apify record: {e}")

    # Convert
    observations = apify_dataset_to_observations(records, profiles)
    print(f"Converted {len(observations)} observations (exact org matches only)")

    # Count by org
    from collections import Counter
    org_counts = Counter(obs["organisation_number"] for obs in observations)
    print(f"Companies with ≥1 job: {len(org_counts)}")
    print(f"Max jobs per company: {max(org_counts.values()) if org_counts else 0}")

    # Write
    write_jsonl(Path(args.output), observations)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
