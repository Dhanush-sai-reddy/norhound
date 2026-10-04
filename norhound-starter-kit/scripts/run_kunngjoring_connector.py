#!/usr/bin/env python3
"""Fetch BRREG Kunngjoringer (official announcements) for every organisation.

Free public page per organisation number — no key, no rate limit issues at
1 req/s.  Emits dated public_post observations: exact-entity (org# is in the
URL), approved source, official announcement.

    python scripts/run_kunngjoring_connector.py \
        --profiles out/web1000-profiles.jsonl \
        --output out/kunngjoring.external.jsonl \
        --report out/kunngjoring-report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path

UA = "Mozilla/5.0 (compatible; NorHound research bot; +https://github.com/Dhanush-sai-reddy/norhound)"
# Rows look like:
#   <td ...><p>23.05.2026</p></td><td><p>&nbsp;</p></td>
#   <td nowrap="true"><p><a href="hent_en.jsp?kid=...">Godkjente ...</a></p></td>
ANN_RE = re.compile(
    r"<td[^>]*>\s*<p>\s*(\d{2}\.\d{2}\.\d{4})\s*</p>\s*</td>"
    r"\s*<td[^>]*>.*?</td>"
    r"\s*<td[^>]*>\s*<p>\s*<a[^>]*href=\"([^\"]*hent_en\.jsp[^\"]*)\"[^>]*>(.*?)</a>",
    re.S,
)


def parse_announcements(html: str) -> list[dict]:
    rows = []
    for date_str, href, text in ANN_RE.findall(html):
        text = unescape(re.sub(r"<[^>]+>", "", text)).strip()
        # dd.mm.yyyy -> yyyy-mm-dd
        try:
            dd, mm, yyyy = date_str.split(".")
            iso = f"{yyyy}-{mm}-{dd}"
        except ValueError:
            continue
        rows.append({"date": iso, "title": text, "url": f"https://w2.brreg.no/kunngjoring/{href}"})
    return rows


def fetch_org(org: str) -> dict:
    url = f"https://w2.brreg.no/kunngjoring/hent_nr.jsp?orgnr={org}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("latin-1", errors="replace")
    return parse_announcements(html)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    orgs = []
    with open(args.profiles, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                orgs.append(str(json.loads(line)["organisation_number"]).zfill(9))
    print(f"{len(orgs)} organisations")

    observations, statuses = [], {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_org, org): org for org in orgs}
        for fut in as_completed(futures):
            org = futures[fut]
            done += 1
            try:
                rows = fut.result()
            except urllib.error.HTTPError as exc:
                rows = []
                statuses[org] = f"http_{exc.code}"
            except Exception as exc:
                rows = []
                statuses[org] = f"{type(exc).__name__}"
            if rows:
                statuses[org] = f"ok:{len(rows)}"
                # Keep only the 3 most recent announcements per org (freshest signal)
                for row in rows[:3]:
                    payload = {
                        "title": row["title"],
                        "date": row["date"],
                        "url": row["url"],
                    }
                    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
                    observations.append({
                        "id": "brreg-kunngjoring-" + hashlib.sha256(
                            (org + "|" + row["url"]).encode()
                        ).hexdigest()[:24],
                        "organisation_number": org,
                        "platform": "brreg",
                        "signal_type": "public_post",
                        "source_url": row["url"],
                        "retrieved_at": "2026-10-05T00:00:00Z",
                        "content_sha256": hashlib.sha256(raw).hexdigest(),
                        "exact_entity": True,
                        "identity_proof": [{
                            "type": "organisation_number_on_official_api",
                            "source": "w2.brreg.no/kunngjoring",
                            "source_class": "official_registry",
                            "matched_organisation_number": org,
                            "explanation": "BRREG Kunngjoringer (official announcements) page queried by exact organisation number.",
                        }],
                        "acquisition_mode": "official_api",
                        "rights_status": "approved",
                        "source_class": "official_api",
                        "observed_at": row["date"],
                        "signal": payload,
                        "evidence_span": f"{row['title']} — {row['date']} (BRREG official announcement)",
                    })
            if done % 100 == 0:
                print(f"  {done}/{len(orgs)} processed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for obs in observations:
            f.write(json.dumps(obs, ensure_ascii=False) + "\n")

    report = {
        "connector": "brreg_kunngjoring_v1",
        "organisations": len(orgs),
        "with_announcements": sum(1 for s in statuses.values() if str(s).startswith("ok")),
        "observations": len(observations),
        "statuses_sample": dict(list(statuses.items())[:10]),
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
