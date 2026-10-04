#!/usr/bin/env python3
import json
import subprocess
import os
import time

# Run all 20 batches
for i in range(1, 21):
    input_file = f"data/jobs_batch_inputs/batch_{i:02d}_input.json"
    if not os.path.exists(input_file):
        print(f"Missing: {input_file}")
        continue
    
    with open(input_file) as f:
        input_data = json.load(f)
    
    input_data["query"] = "utvikler"
    
    cmd = [
        'apify', 'run', 'yearly_register/norway-jobs-search-api',
        '--input', json.dumps(input_data),
        '--token', os.environ.get('APIFY_TOKEN')
    ]
    
    print(f"Running batch {i}/20...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    if result.returncode == 0:
        print(f"  Batch {i}: OK")
    else:
        print(f"  Batch {i} FAILED: {result.stderr[:200]}")
    
    time.sleep(2)  # Rate limiting

print("All batches done")