#!/usr/bin/env python3
"""Publish social handles that sit on an exact-identity-gated company website.

A company that links a social profile from its own verified website provides
identity evidence ("linked_from_verified_site"). This recovers handles that the
name-token gate withholds when the brand handle differs from the legal name.
Offline, no network, no API key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

PLATFORM_BY_HOST = {
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "instagram.com": "instagram",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1).lower() if m else "").removeprefix("www.")


def platform_of(url: str) -> str | None:
    h = host_of(url)
    for dom, plat in PLATFORM_BY_HOST.items():
        if h == dom or h.endswith("." + dom):
            return plat
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    stats = {"profiles": len(profiles), "site_exact": 0, "emitted": 0, "skipped_not_exact": 0, "skipped_dup": 0}

    for p in profiles:
        org = str(p["organisation_number"])
        ev = (p.get("evidence") or {}).get("website") or {}
        if ev.get("status") != "available":
            continue
        val = ev.get("value") or {}
        ident = val.get("identity_assessment") or {}
        status = str(ident.get("status") or ident.get("decision") or "").lower()
        if status not in {"exact", "verified"}:
            stats["skipped_not_exact"] += 1
            continue
        stats["site_exact"] += 1
        site_url = ev.get("source_url") or val.get("final_url") or val.get("requested_url") or ""
        retrieved = ev.get("retrieved_at")
        sha = ev.get("content_sha256") or val.get("content_sha256")
        assessments = {(a.get("platform"), a.get("url")): a for a in (val.get("social_link_assessments") or []) if isinstance(a, dict)}
        links = list(val.get("social_links") or []) + list(val.get("discovered_social_links") or [])
        for link in links:
            if not isinstance(link, dict):
                continue
            url = str(link.get("url") or "")
            plat = link.get("platform") or platform_of(url)
            if not url or not plat:
                continue
            key = (org, plat)
            if key in seen:
                stats["skipped_dup"] += 1
                continue
            seen.add(key)
            a = assessments.get((plat, url)) or {}
            digest = hashlib.sha256(f"{org}|{plat}|{url}".encode()).hexdigest()[:16]
            out.append({
                "organisation_number": org,
                "platform": plat,
                "source_url": site_url,
                "retrieved_at": retrieved,
                "content_sha256": sha,
                "exact_entity": True,
                "identity_proof": [{
                    "type": "linked_from_verified_site",
                    "company_site_url": site_url,
                    "identity_score": a.get("identity_score"),
                    "matched_tokens": a.get("matched_tokens"),
                    "name_token_gate": a.get("publishable"),
                    "method": "linked_from_verified_site_v1",
                }],
                "acquisition_mode": "permitted_public_page",
                "rights_status": "approved",
                "source_class": "company_site",
                "strategy": "site_linked_social_handle",
                "id": f"site-social-{org}-{plat}-{digest}",
                "signal_type": "profile_handle",
                "evidence_span": f"Social handle linked from the exact-identity-gated company website {site_url}."[:1200],
                "metrics": {"platform": plat, "url": url, "identity_score": a.get("identity_score")},
            })
            stats["emitted"] += 1

    write_jsonl(Path(args.output), out)
    orgs = len({o["organisation_number"] for o in out})
    report = {**stats, "orgs_with_handles": orgs, "output": args.output}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
