import json

batch_orgs = set()
with open('out/web1000-profiles.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            r = json.loads(line)
            org = r.get('organisation_number')
            if org:
                batch_orgs.add(str(org).zfill(9))

print(f'Batch orgs: {len(batch_orgs)}')

labels = {}
with open('out/batch.labels.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            r = json.loads(line)
            labels[str(r['id'])] = r

job_companies = set()
ws_companies = set()

for label in labels.values():
    sig = label.get('signal_type')
    org = label.get('organisation_number')
    if sig == 'job_posting' and org:
        job_companies.add(str(label.get('organisation_number')).zfill(9))
    elif sig == 'workforce_snapshot' and org:
        ws_companies.add(str(label.get('organisation_number')).zfill(9))

print(f'Companies with job_posting: {len(job_companies)}')
print(f'Companies with workforce_snapshot: {len(ws_companies)}')

job_in_batch = [c for c in job_companies if c in batch_orgs]
ws_in_batch = [c for c in ws_companies if c in batch_orgs]

print(f'Job companies in batch: {len(job_companies)}')
print(f'WS in batch: {len(ws_companies)}')
print(f'Total in batch: {len(set(job_companies) | set(ws_companies))}')

EOF