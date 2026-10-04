#!/usr/bin/env python3
"""Apify cache layer - persists actor results locally to avoid re-fetching."""
import os
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

CACHE_DIR = Path("data/apify_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

class ApifyCache:
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _cache_key(self, actor: str, input_data: dict) -> str:
        """Generate deterministic cache key from actor name and input."""
        content = json.dumps({"actor": actor, "input": input_data}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def _cache_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"
    
    def _meta_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.meta.json"
    
    def get(self, actor: str, input_data: dict) -> Optional[List[dict]]:
        """Get cached results if available and not stale (7 days)."""
        cache_key = self._cache_key(actor, input_data)
        cache_file = self._cache_path(cache_key)
        meta_file = self._meta_path(cache_key)
        
        if not cache_file.exists() or not meta_file.exists():
            return None
        
        # Check if stale (7 days)
        with open(meta_file) as f:
            meta = json.load(f)
        if time.time() - meta.get("timestamp", 0) > 7 * 24 * 3600:
            return None
        
        results = []
        with open(cache_file, 'r') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        print(f"  Cache HIT: {actor} ({len(results)} items)")
        return results
    
    def set(self, actor: str, input_data: dict, results: List[dict]) -> None:
        """Store results in cache."""
        cache_key = self._cache_key(actor, input_data)
        cache_file = self._cache_path(cache_key)
        meta_file = self._meta_path(cache_key)
        
        with open(cache_file, 'w') as f:
            for row in results:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        
        with open(meta_file, 'w') as f:
            json.dump({"timestamp": time.time(), "actor": actor, "count": len(results)}, f)
        
        print(f"  Cache SET: {actor} ({len(results)} items)")

def run_actor_cached(cache: ApifyCache, actor: str, input_data: dict, token: str) -> List[dict]:
    """Run actor with caching - checks cache first, runs if needed."""
    # Check cache first
    cached = cache.get(actor, input_data)
    if cached is not None:
        return cached
    
    # Not in cache - run actor
    import subprocess
    import os
    
    input_json = json.dumps(input_data)
    cmd = [
        'apify', 'run', actor,
        '--input', input_json,
        '--token', token
    ]
    
    env = os.environ.copy()
    env['APIFY_TOKEN'] = token
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    
    if result.returncode != 0:
        raise RuntimeError(f"Actor {actor} failed: {result.stderr}")
    
    # Parse output to get dataset ID
    # For now, just return empty - in production would parse output for dataset ID
    # and fetch items
    return []

def load_apify_results_cached(cache: ApifyCache, dataset_id: str, actor: str, input_data: dict) -> List[dict]:
    """Load Apify dataset results with caching."""
    cache_key = f"dataset_{dataset_id}"
    cache_file = Path("data/apify_cache") / f"{cache_key}.jsonl"
    meta_file = Path("data/apify_cache") / f"{cache_key}.meta.json"
    
    # Check cache
    if cache_file.exists() and meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)
        if time.time() - meta.get("timestamp", 0) <= 7 * 24 * 3600:
            results = []
            with open(cache_file) as f:
                for line in f:
                    if line.strip():
                        results.append(json.loads(line))
            print(f"  Dataset cache HIT: {dataset_id} ({len(results)} items)")
            return results
    
    # Fetch from Apify
    import subprocess
    import os

    token = os.environ.get('APIFY_TOKEN')
    if not token:
        raise SystemExit("APIFY_TOKEN environment variable is required")
    cmd = [
        'apify', 'dataset', 'get-items', dataset_id,
        '--format', 'jsonl',
        '--token', token
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch dataset {dataset_id}: {result.stderr}")
    
    # Parse results
    results = []
    for line in result.stdout.strip().split('\n'):
        if line.strip():
            results.append(json.loads(line))
    
    # Save to cache
    with open(cache_file, 'w') as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    
    with open(meta_file, 'w') as f:
        json.dump({"timestamp": time.time(), "dataset_id": dataset_id, "count": len(results)}, f)
    
    print(f"  Dataset cached: {dataset_id} ({len(results)} items)")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    
    if args.test:
        cache = ApifyCache()
        # Test cache
        test_input = {"query": "test"}
        cache.set("test_actor", test_input, [{"test": "data"}])
        result = cache.get("test_actor", test_input)
        print(f"Test result: {result}")
EOF