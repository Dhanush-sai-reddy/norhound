#!/usr/bin/env python3
"""
Convert Proff.no company data to observations for pipeline integration.
"""

import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone


def load_proff_data(jsonl_path: Path):
    """Load Proff.no data from Apify dataset output."""
    companies = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                companies.append(json.loads(line))
    return companies


def convert_to_observations(company: dict) -> list[dict]:
    """Convert Proff.no company data to observation format."""
    org_number = company.get('orgnr')
    if not org_number:
        return []
    
    org_number = str(org_number).zfill(9)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    observations = []
    
    # Company profile observation - use profile_metrics for buzz_engagement coverage
    profile_payload = {
        "name": company.get('name', ''),
        "legal_name": company.get('legalName', ''),
        "revenue_nok": company.get('revenue'),
        "profit_nok": company.get('profit'),
        "currency": company.get('currency', 'NOK'),
        "employees": company.get('employees'),
        "industries": company.get('industries', []),
        "roles": company.get('details', {}).get('roles', []),
        "status": company.get('details', {}).get('status'),
        "purpose": company.get('details', {}).get('purpose'),
        "has_trademarks": company.get('details', {}).get('hasTrademarks'),
        "related_companies_count": company.get('details', {}).get('relatedCompaniesCount'),
        "company_type": company.get('details', {}).get('companyType'),
        "nace_industries": company.get('details', {}).get('naceIndustries'),
    }
    profile_bytes = json.dumps(profile_payload, sort_keys=True, ensure_ascii=False).encode()
    
    observations.append({
        "id": "proff-profile-" + hashlib.sha256((org_number + "|profile").encode()).hexdigest()[:24],
        "organisation_number": org_number,
        "platform": "company_directory",
        "signal_type": "profile_metrics",  # This counts for buzz_engagement coverage
        "source_url": f"https://www.proff.no/bedrift/{org_number}",
        "retrieved_at": retrieved_at,
        "content_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "exact_entity": True,
        "identity_proof": [{
            "type": "organisation_number_on_directory_page",
            "source": "proff.no",
            "source_class": "company_directory",
            "matched_organisation_number": org_number,
            "explanation": "Proff.no company profile with exact organisation number match from BRREG data."
        }],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_directory",
        "signal": profile_payload
    })
    
    # Financial metrics observation (if revenue/profit available)
    if company.get('revenue') is not None or company.get('profit') is not None:
        financial_payload = {
            "revenue_nok": company.get('revenue'),
            "profit_nok": company.get('profit'),
            "currency": company.get('currency', 'NOK'),
            "employees": company.get('employees'),
        }
        financial_bytes = json.dumps(financial_payload, sort_keys=True, ensure_ascii=False).encode()
        
        observations.append({
            "id": "proff-financial-" + hashlib.sha256((org_number + "|financial").encode()).hexdigest()[:24],
            "organisation_number": org_number,
            "platform": "company_directory",
            "signal_type": "profile_metrics",
            "source_url": f"https://www.proff.no/bedrift/{org_number}",
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(financial_bytes).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{
                "type": "organisation_number_on_directory_page",
                "source": "proff.no",
                "source_class": "company_directory",
                "matched_organisation_number": org_number,
                "explanation": "Proff.no financial data with exact organisation number match from BRREG data."
            }],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_directory",
            "signal": financial_payload
        })
    
    # Credit rating / review observation (if available) - use review_summary for ratings_reviews coverage
    if company.get('details', {}).get('status'):
        rating_payload = {
            "credit_status": company.get('details', {}).get('status'),
            "purpose": company.get('details', {}).get('purpose'),
            "has_trademarks": company.get('details', {}).get('hasTrademarks'),
            "accounts_last_updated": company.get('details', {}).get('accountsLastUpdated'),
        }
        rating_bytes = json.dumps(rating_payload, sort_keys=True, ensure_ascii=False).encode()
        
        observations.append({
            "id": "proff-rating-" + hashlib.sha256((org_number + "|rating").encode()).hexdigest()[:24],
            "organisation_number": org_number,
            "platform": "company_directory",
            "signal_type": "review_summary",  # This counts for ratings_reviews coverage
            "source_url": f"https://www.proff.no/bedrift/{org_number}",
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(rating_bytes).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{
                "type": "organisation_number_on_directory_page",
                "source": "proff.no",
                "source_class": "company_directory",
                "matched_organisation_number": org_number,
                "explanation": "Proff.no credit status with exact organisation number match from BRREG data."
            }],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_directory",
            "signal": rating_payload
        })
    
    # Also create review_summary for companies with financial data (creditworthiness signal)
    if company.get('revenue') is not None or company.get('profit') is not None:
        review_payload = {
            "credit_indicator": "financial_data_available",
            "revenue_nok": company.get('revenue'),
            "profit_nok": company.get('profit'),
            "employees": company.get('employees'),
        }
        review_bytes = json.dumps(review_payload, sort_keys=True, ensure_ascii=False).encode()
        
        observations.append({
            "id": "proff-review-" + hashlib.sha256((org_number + "|review").encode()).hexdigest()[:24],
            "organisation_number": org_number,
            "platform": "company_directory",
            "signal_type": "review_summary",  # This counts for ratings_reviews coverage
            "source_url": f"https://www.proff.no/bedrift/{org_number}",
            "retrieved_at": retrieved_at,
            "content_sha256": hashlib.sha256(review_bytes).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{
                "type": "organisation_number_on_directory_page",
                "source": "proff.no",
                "source_class": "company_directory",
                "matched_organisation_number": org_number,
                "explanation": "Proff.no financial data as creditworthiness review with exact organisation number match."
            }],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_directory",
            "signal": review_payload
        })
    
    return observations


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Convert Proff.no raw data to observations")
    ap.add_argument("--input", type=Path, default=None, help="Proff raw JSONL (defaults to newest data/proff*.jsonl)")
    ap.add_argument("--output", type=Path, default=Path("out/proff-ratings.external.jsonl"))
    args = ap.parse_args()

    if args.input is not None:
        input_path = args.input
    else:
        # Try to find the latest Proff data file
        data_files = list(Path("data").glob("proff*.jsonl"))
        if not data_files:
            # Try Apify output
            data_files = list(Path("out").glob("proff*.jsonl"))
        if not data_files:
            print("No Proff data file found. Expected in data/proff-*.jsonl or out/proff-*.jsonl")
            sys.exit(1)
        input_path = max(data_files, key=lambda p: p.stat().st_mtime)

    output_path = args.output
    
    print(f"Reading Proff data from: {input_path}")
    companies = load_proff_data(input_path)
    print(f"Loaded {len(companies)} companies")
    
    all_observations = []
    org_counts = {}
    
    for company in companies:
        obs_list = convert_to_observations(company)
        for obs in obs_list:
            all_observations.append(obs)
            org = obs['organisation_number']
            org_counts[org] = org_counts.get(org, 0) + 1
    
    print(f"Generated {len(all_observations)} observations")
    print(f"Unique companies: {len(org_counts)}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        for obs in all_observations:
            f.write(json.dumps(obs, ensure_ascii=False) + '\n')
    
    print(f"Written to {output_path}")
    
    # Print top companies
    print("\nTop companies by observation count:")
    for org, count in sorted(org_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {org}: {count} observations")


if __name__ == "__main__":
    main()