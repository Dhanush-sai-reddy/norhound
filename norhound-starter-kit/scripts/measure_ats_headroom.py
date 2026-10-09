#!/usr/bin/env python3
"""Measure recall headroom: old ATS pattern vs new Nordic pattern on live sites."""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import scripts.run_ats_jobs_connector as conn  # noqa: E402

OLD_GROUPS = {"workday", "lever", "greenhouse", "greenhouse2", "smart", "teamtailor"}


def check(profile: dict) -> dict | None:
    ev = (profile.get("evidence") or {}).get("website") or {}
    if ev.get("status") != "available":
        return None
    val = ev.get("value") or {}
    ident = val.get("identity_assessment") or {}
    if str(ident.get("status") or "").lower() not in {"exact", "related_or_uncertain"}:
        return None
    site = ev.get("source_url") or val.get("final_url") or ""
    if not site:
        return None
    import urllib.parse
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(site))
    pages = [site] + [base + p for p in conn.CAREER_PATHS]
    home = None
    old_hit = None
    new_hit = None
    for i, page in enumerate(pages):
        html = conn.fetch_html(page)
        if i == 0:
            home = html
        if not html:
            continue
        m = conn.find_ats(html)
        if m:
            g = [k for k, v in m.groupdict().items() if v]
            provider = g[0] if g else "?"
            if provider in OLD_GROUPS:
                if not old_hit:
                    old_hit = provider
                if not new_hit:
                    new_hit = provider
            else:
                if not new_hit:
                    new_hit = provider
            if old_hit:
                break
    # discovery boost: careers links found on homepage
    if not new_hit and home:
        for link in conn.collect_careers_page_links(home, site)[:3]:
            html = conn.fetch_html(link)
            if not html:
                continue
            m = conn.find_ats(html)
            if m:
                g = [k for k, v in m.groupdict().items() if v]
                provider = g[0] if g else "?"
                if not new_hit:
                    new_hit = provider
                if provider in OLD_GROUPS and not old_hit:
                    old_hit = provider
                break
    return {"org": profile["organisation_number"], "old": old_hit, "new": new_hit}


def main() -> None:
    profiles = [json.loads(l) for l in (ROOT / "out/web1000-profiles.jsonl").read_text().splitlines() if l.strip()]
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = [pool.submit(check, p) for p in profiles[:n]]
        for f in as_completed(futs):
            r = f.result()
            if r:
                results.append(r)
    old_cos = [r for r in results if r["old"]]
    new_cos = [r for r in results if r["new"]]
    new_only = [r for r in results if r["new"] and not r["old"]]
    out = {
        "scanned": len(results),
        "old_pattern_hits": len(old_cos),
        "new_pattern_hits": len(new_cos),
        "new_only_hits": len(new_only),
        "new_only_providers": {},
        "new_only_examples": new_only[:15],
    }
    for r in new_only:
        out["new_only_providers"][r["new"]] = out["new_only_providers"].get(r["new"], 0) + 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    (ROOT / "out/ats-headroom-report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
