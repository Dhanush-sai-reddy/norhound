#!/usr/bin/env python3
"""Purge obviously-wrong-company rows from merged observations.

The merge_synthesis sets exact_entity=True for new connector rows. Some probed
sites (heroes.com, myriad.com, sandero.com etc.) are brand-collision false
positives that passed the token gate. This script marks them exact_entity=False
so they cannot be published — precision gate stays 1.0.

Conservative: only rows from strategy=site_linked_social_handle or
probed_site_social_handle where the source domain's token is NOT in the legal
name AND not in known .no domain are dropped.
"""
from __future__ import annotations

import argparse, json, re
from pathlib import Path

def rd(p):
    if not Path(p).exists(): return []
    out=[]
    with open(p, encoding="utf-8") as f:
        for l in f:
            l=l.strip()
            if l: out.append(json.loads(l))
    return out
def wr(p, rows):
    with open(p, "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False, separators=(",",":"))+"\n")

DOMAIN_RE = re.compile(r"https?://(?:www\.)?([^/]+)")
LETTER_RE = re.compile(r"[^a-z]")

def stem(url):
    url = str(url or "").lower()
    m = DOMAIN_RE.match(url)
    if not m: return ""
    host = m.group(1)
    if host.endswith(".no"): host = host[:-3]
    return re.sub(r"[^a-z0-9]", "", host)

def wordtokens(text):
    return set(re.findall(r"[a-z0-9æøå]{3,}", (text or "").casefold()))

RISKY_STEMS = {"sandero", "myriad", "heroes", "hydor", "inotech", "petabitscale",
               "security-first", "vt-elektro", "netcode", "satlog", "astaart", "domainriviera",
               "mulium", "nuga", "patonomics", "gavin", "autoproducts", "prolek"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--observations", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    obs = rd(args.observations)
    profs = {str(p["organisation_number"]): p for p in rd(args.profiles)}
    risky = []; kept = []
    for o in obs:
        str_ = o.get("strategy") or ""
        if str_ not in ("site_linked_social_handle", "probed_site_social_handle"):
            kept.append(o); continue
        org = str(o["organisation_number"]); name = str((profs.get(org) or {}).get("name") or "").lower()
        src = o.get("source_url") or o.get("source") or ""
        s = stem(src)
        # Keep if stem is in legal name OR name tokens entirely in stem
        ntext = LETTER_RE.sub(" ", (name or "").casefold())
        compact = re.sub(r"[^a-z0-9]", "", ntext)
        safe_tokens = {"sandero","myriad","heroes","hydor","inotech","petabitscale",
               "security-first","vt-elektro","netcode","satlog","astaart","domainriviera",
               "mulium","nuga","patonomics","gavin","autoproducts","prolek"}
        if s in compact or compact in s:
            kept.append(o)
        elif s in safe_tokens or any(t in s for t in safe_tokens):
            o["exact_entity"] = False
            o["identity_proof"] = (o.get("identity_proof") or []) + [{"type":"wrong_company_rejected","because":"brand-collision domain, token not in legal name","source": src}]
            risky.append(o)
        else:
            kept.append(o)
    wr(args.output, kept)
    rep = {"rows_in": len(obs), "rows_out": len(kept), "dropped": len(risky), "drop_orgs": len({r["organisation_number"] for r in risky}), "output": args.output}
    Path(args.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(rep, ensure_ascii=False))

if __name__=="__main__":
    main()
