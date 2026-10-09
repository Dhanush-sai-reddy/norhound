#!/usr/bin/env python3
"""Zero-cost website discovery: registry email domain + legal-name slug probes.

For companies without an exact-identity website, generates candidates from
(a) the BRREG-registered email domain and (b) deterministic legal-name slugs,
fetches each (bounded, robots-aware), and keeps only candidates our own
identity gate scores exact. Output doubles as pipeline --discovery-input.
No search API, no key.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.website import fetch_website  # noqa: E402
from norway_company_agent.identity import assess_website_identity  # noqa: E402

FREE_MAIL = {
    "gmail.com", "hotmail.com", "hotmail.no", "outlook.com", "outlook.no", "yahoo.com",
    "yahoo.no", "icloud.com", "online.no", "broadpark.no", "live.no", "live.com", "msn.com",
}
LEGAL_TAIL = re.compile(r"\b(as|asa|ans|da|sa|ba|enk|nuf|avd|avdeling|aksjeselskap)\b", re.I)
STOPWORDS = {"og", "and", "the", "group", "gruppen", "norge", "norway", "avd", "avdeling", "enhet", "for"}
# Aggregator/directory/social domains that are never a company's own website
# (independent discovery; same class as krgr's blocklist).
BLOCKED_DOMAINS = {
    "proff.no", "purehelp.no", "gulesider.no", "180.no", "1881.no", "io.no",
    "facebook.com", "linkedin.com", "instagram.com", "youtube.com", "youtu.be",
    "tiktok.com", "twitter.com", "x.com", "wikipedia.org", "spotify.com",
    "soundcloud.com", "forvalt.no", "areg.no", "listings.no", "lei.report",
    "nordlei.org", "norgelei.no", "regnskapstall.no", "regnskapsbasen.no",
    "firmadatabasen.no", "virksomhet.brreg.no", "sgregister.dibk.no",
    "northdata.com", "merinfo.no", "prospeo.io", "restaurantmeny.no",
    "smartmeny.no", "biztrac.no", "opencompanydatabase.com",
}


def slug_tokens(name: str) -> list[str]:
    norm = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().casefold()
    toks = [t for t in re.findall(r"[a-z0-9]+", norm) if t not in STOPWORDS]
    toks = [t for t in toks if not LEGAL_TAIL.fullmatch(t)]
    return toks


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def candidates_for(profile: dict) -> list[str]:
    out: list[str] = []
    reg = ((profile.get("evidence") or {}).get("registry") or {}).get("value") or {}
    em = str(reg.get("epostadresse") or "")
    if "@" in em:
        dom = em.split("@")[-1].strip().lower()
        if dom and "." in dom and dom not in FREE_MAIL and not dom.endswith((".kommune.no", ".gov.no", ".fylke.no")):
            out.append("https://" + dom + "/")
    toks = slug_tokens(str(profile.get("name") or ""))
    if toks:
        joined = "".join(toks)
        base = toks[0] if len(toks) == 1 else joined
        for tld in (".no", ".com"):
            out.append(f"https://{joined}{tld}/")
            if "-" not in joined and len(toks) > 1:
                out.append(f"https://{'-'.join(toks)}{tld}/")
            if base != joined:
                out.append(f"https://{base}{tld}/")
    # dedupe, drop aggregators, cap 5
    seen: list[str] = []
    for u in out:
        host = urllib.parse.urlparse(u).hostname or ""
        if host in BLOCKED_DOMAINS or any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS):
            continue
        if u not in seen:
            seen.append(u)
        if len(seen) >= 5:
            break
    return seen


def process(profile: dict) -> dict | None:
    ev = (profile.get("evidence") or {}).get("website") or {}
    val = ev.get("value") or {}
    ia = val.get("identity_assessment") or {}
    if str(ia.get("status") or "").lower() == "exact":
        return None
    org = str(profile["organisation_number"])
    for url in candidates_for(profile):
        try:
            rec, _ = fetch_website(url)
        except Exception:
            continue
        if rec.get("status") != "available":
            continue
        tmp = {**profile, "evidence": {**(profile.get("evidence") or {}), "website": rec}}
        score = assess_website_identity(tmp)
        if score.get("status") == "exact":
            return {
                "organisation_number": org,
                "website": (rec.get("value") or {}).get("final_url") or url,
                "identity_score": score.get("score"),
                "method": "email_or_slug_probe_v1",
                "candidate": url,
            }
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    if args.limit:
        profiles = profiles[: args.limit]
    out: list[dict] = []
    stats = {"profiles": 0, "verified": 0}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process, p): p for p in profiles}
        for fut in as_completed(futures):
            stats["profiles"] += 1
            row = fut.result()
            if row:
                out.append(row)
    stats["verified"] = len(out)
    write_jsonl(Path(args.output), out)
    stats["output"] = args.output
    Path(args.report).write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
