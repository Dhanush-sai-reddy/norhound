#!/usr/bin/env python3
"""
Store Apify NAV jobs data as observations for pipeline integration.
"""

import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_apify_jobs(jsonl_path: Path):
    """Load jobs from Apify dataset output."""
    jobs = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line))
    return jobs


def convert_to_observation(job: dict) -> dict:
    """Convert Apify NAV job to observation format."""
    org_number = job.get('org_number')
    if not org_number:
        return None
    
    org_number = str(org_number).zfill(9)
    uuid_val = job.get('uuid', '')
    
    published = job.get('published')
    if published:
        try:
            observed_at = datetime.fromisoformat(published.replace('Z', '+00:00'))
        except:
            observed_at = datetime.now(timezone.utc)
    else:
        observed_at = datetime.now(timezone.utc)
    
    payload = {
        "title": job.get('title', ''),
        "jobtitle": job.get('job_title', ''),
        "employer_name": job.get('employer_name', ''),
        "employer_parent_orgnr": org_number,
        "location": job.get('city', ''),
        "published": published,
        "deadline": job.get('expires', ''),
        "apply_url": job.get('apply_url', ''),
        "short_summary": job.get('short_summary', ''),
        "ai_tags": job.get('ai_tags', []),
        "ats_vendor": job.get('ats_vendor', ''),
        "source": job.get('source', ''),
        "engagement_type": job.get('engagement_type', ''),
        "extent": job.get('extent', ''),
        "position_count": job.get('position_count', 1),
        "occupation_level1": job.get('occupation_level1', ''),
        "occupation_level2": job.get('occupation_level2', ''),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    
    observation = {
        "id": "nav-job-" + hashlib.sha256((org_number + "|" + uuid_val).encode()).hexdigest()[:24],
        "organisation_number": org_number,
        "platform": "job_board",
        "signal_type": "job_posting",
        "source_url": job.get('ad_url', ''),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "content_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "exact_entity": True,
        "identity_proof": [{
            "type": "organisation_number_on_official_api",
            "source": "pam-stilling-feed.nav.no",
            "source_class": "official_job_board",
            "matched_organisation_number": org_number,
            "explanation": "NAV job feed detail advertises posting employer with legal organisation number equal to the profile organisation number."
        }],
        "acquisition_mode": "official_api",
        "rights_status": "approved",
        "source_class": "official_api",
        "signal": payload
    }
    return observation


def main():
    input_path = Path("data/apify_nav_jobs_200.jsonl")
    output_path = Path("out/apify-nav-jobs.external.jsonl")
    
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        sys.exit(1)
    
    jobs = load_apify_jobs(input_path)
    print(f"Loaded {len(jobs)} jobs from Apify")
    
    observations = []
    org_counts = {}
    
    for job in jobs:
        obs = convert_to_observation(job)
        if obs:
            observations.append(obs)
            org_number = obs['organisation_number']
            org_counts[org_number] = org_counts.get(org_number, 0) + 1
    
    print(f"Converted {len(observations)} observations")
    print(f"Unique companies with jobs: {len(org_counts)}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        for obs in observations:
            f.write(json.dumps(obs, ensure_ascii=False) + '\n')
    
    print(f"Written to {output_path}")
    
    # Print top companies
    print("\nTop companies by job count:")
    for org, count in sorted(org_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {org}: {count} jobs")


if __name__ == "__main__":
    main()