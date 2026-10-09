#!/usr/bin/env python3
"""Run Gulesider scraper for all 1,000 companies with checkpoints."""
import os
import sys
import json
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# We'll use the MCP apify_call_actor tool via a wrapper
# This script generates the input files for batch processing
# The actual Apify calls will be made via the MCP tools

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_company_names(profiles_path):
    names = []
    with open(profiles_path, 'r') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                name = r.get('name', '').strip()
                if name:
                    names.append(name)
    return names


def generate_batch_inputs():
    """Generate input JSON files for each batch."""
    profiles_path = ROOT / "out/web1000-profiles.jsonl"
    names = load_company_names(profiles_path)
    print(f"Loaded {len(names)} company names")

    batch_size = 50
    batches = [names[i:i+50] for i in range(0, len(names), 50)]
    print(f"Total batches: {len(batches)}")

    batch_inputs_dir = DATA_DIR / "gulesider_batch_inputs"
    batch_inputs_dir.mkdir(parents=True, exist_ok=True)

    for i, batch in enumerate(batches):
        batch_num = i + 1
        input_data = {
            "mode": "search",
            "companyInclude": batch,
            "fetchDetails": True,
            "ratedOnly": True,
            "maxItems": len(batch),
            "stateKey": f"gulesider-batch-{batch_num}"
        }
        input_file = batch_inputs_dir / f"batch_{batch_num:02d}_input.json"
        with open(input_file, 'w') as f:
            json.dump(input_data, f)
        print(f"  Generated batch {batch_num}/{len(batches)} input: {input_file}")

    print(f"\nAll {len(batches)} batch inputs generated in {batch_inputs_dir}")
    print("Run them via: apify run crawlerbros/gulesider-scraper --input <file> --token <token>")
    return len(batches)


def check_results():
    """Check and consolidate results from completed batches."""
    results_dir = DATA_DIR / "gulesider_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # This would check for completed runs and consolidate
    # For now, just list what we have
    print("Checking for completed runs...")
    # This would need to be run after Apify runs complete


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gulesider batch runner")
    parser.add_argument("--generate", action="store_true", help="Generate batch input files")
    parser.add_argument("--check", action="store_true", help="Check for completed results")
    args = parser.parse_args()

    if args.generate:
        generate_batch_inputs()
    elif args.check:
        check_results()
    else:
        generate_batch_inputs()


if __name__ == "__main__":
    main()