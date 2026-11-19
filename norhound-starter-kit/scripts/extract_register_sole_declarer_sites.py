#!/usr/bin/env python3
"""A proven second platform for directory-only companies.

374 of the 1,000 companies publish exactly one source outside the register: the
Purehelp/Fagfolkguiden directory. 371 state a website domain there and 175 of
those domains are declared by the *same* organisation number in the register's
sole-declarer index (82,398 domains, each declared by exactly one entity, 0
mismatches among the 371). A live probe fetched 72 of the 175; 37 named the
legal company and were not parked.

This connector fetches those domains and emits a `website_description` only
when BOTH hold:

* the domain is declared by this organisation alone in the register's
  sole-declarer index (this connector never publishes a shared domain), and
* the page body names this organisation (its organisation number, or at least
  half of its distinctive legal-name tokens) and is not parked.

The identity proof is `registry_sole_declarer_domain_match`. The verifier
re-derives it from the frozen index, the profile's registry field and the body
excerpt stored on the observation: without the index the row is **not**
trusted, so a corpus verified without `--domain-index` publishes none of these.

Usage:
    uv run python scripts/extract_register_sole_declarer_sites.py \
        --profiles out/frozen/web1000-profiles.jsonl \
        --index data/registry-domain-unique.jsonl.gz \
        --output out/sole-declarer.jsonl \
        --report out/sole-declarer-report.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from verify_and_label_observations import _fold, _legal_name_tokens  # noqa: E402

INDEX_PATH = ROOT / "data" / "registry-domain-unique.jsonl.gz"
UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
PARKED = re.compile(
    r"(is parked|til\s+salgs|for\s+sale|domene\s+til\s+salgs|coming\s+soon|"
    r"under\s+construction|parked\s+at|ledig\s+domene|buy\s+this\s+domain)",
    re.I,
)
BODY_EXCERPT_LIMIT = 2000
FETCH_TIMEOUT = 15.0
FETCH_MAX_BYTES = 1_500_000


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def load_index(path: Path) -> dict[str, str]:
    """domain -> the sole organisation number that declares it.

    The index builder writes only domains declared by exactly one organisation,
    so a domain appearing twice is ambiguous and is dropped here too.
    """
    index: dict[str, str] = {}
    counts: dict[str, int] = {}
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            domain = str(row.get("domain") or "").lower().lstrip(".")
            org = str(row.get("organisation_number") or "")
            if not domain or not org:
                continue
            counts[domain] = counts.get(domain, 0) + 1
            index[domain] = org
    for domain, count in counts.items():
        if count > 1:
            index.pop(domain, None)
    return index


def _host(value: str) -> str:
    text = str(value or "").strip().lower()
    if "://" not in text:
        text = "https://" + text
    try:
        host = (urllib.parse.urlparse(text).hostname or "").strip()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _names_company(text: str, profile: dict) -> bool:
    org = str(profile.get("organisation_number") or "")
    digits = re.sub(r"\D", "", text or "")
    if org and org in digits:
        return True
    tokens = _legal_name_tokens(str(profile.get("name") or ""))
    if not tokens:
        return False
    folded = _fold(text or "")
    hits = sum(1 for token in tokens if token in folded)
    return hits >= max(1, -(-len(tokens) // 2))


def sole_declarer_targets(profiles: list[dict], index: dict[str, str], has_site: list[str]) -> list[dict]:
    """Companies with no website evidence whose declared domain is theirs alone."""
    seen: set[str] = set()
    targets: list[dict] = []
    for profile in profiles:
        org = str(profile.get("organisation_number") or "")
        if not org or org in has_site or org in seen:
            continue
        host = _host(profile.get("website") or "")
        if not host or index.get(host) != org:
            continue
        seen.add(org)
        targets.append({"organisation_number": org, "name": str(profile.get("name") or ""), "host": host})
    return targets


def describe_site(html: str, url: str, profile: dict) -> dict:
    """The title, description and bounded body text of a fetched site."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description = ""
    for meta in soup.find_all("meta"):
        if str(meta.get("name") or "").casefold() == "description" or str(meta.get("property") or "") == "og:description":
            description = str(meta.get("content") or "").strip()
            break
    text = soup.get_text(" ", strip=True)
    return {
        "title": title[:300],
        "description": description[:300],
        "body_excerpt": text[:BODY_EXCERPT_LIMIT],
        "parked": bool(PARKED.search((title + " " + text)[:4000])),
        "source_url": url,
    }


def site_observation(profile: dict, url: str, html: str, raw: bytes, host: str) -> dict | None:
    """One website-description observation, or None when the site is unproven."""
    org = str(profile.get("organisation_number") or "")
    if not org or _host(url) != host or _host(profile.get("website") or "") != host:
        return None
    described = describe_site(html, url, profile)
    if described["parked"]:
        return None
    if not _names_company(described["body_excerpt"] + " " + described["title"], profile):
        return None
    observed_at = None
    return {
        "id": "sole-declarer-site-" + hashlib.sha256(f"{org}|{url}".encode()).hexdigest()[:24],
        "organisation_number": org,
        "platform": "company_site",
        "signal_type": "website_description",
        "source_url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "exact_entity": True,
        "identity_proof": [{
            "type": "registry_sole_declarer_domain_match",
            "matched_organisation_number": org,
            "domain": host,
            "sole_declarer": True,
            "source": "brreg",
        }],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_site",
        "evidence_span": (described["title"] + "\n\n" + described["description"] + "\n\n" + described["body_excerpt"])[:1200],
        "metrics": {
            **{key: value for key, value in described.items() if key != "parked"},
            "registry_domain": host,
            "interpretation": "The register declares this domain for this organisation alone, and the page names the organisation.",
        },
        "strategy": "registry_sole_declarer_site",
        **({"observed_at": observed_at} if observed_at else {}),
    }


def fetch(url: str, timeout: float = FETCH_TIMEOUT) -> tuple[bytes | None, str]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(FETCH_MAX_BYTES)
            content_type = response.headers.get("content-type", "")
        return (raw, "ok") if "html" in content_type.lower() else (None, f"content_type:{content_type[:30]}")
    except Exception as exc:
        return None, type(exc).__name__


def main() -> None:
    parser = argparse.ArgumentParser(description="Register-sole-declarer website connector.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--index", default=str(INDEX_PATH))
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    index = load_index(Path(args.index))
    has_site = [
        str(profile.get("organisation_number") or "")
        for profile in profiles
        if ((profile.get("evidence") or {}).get("website") or {}).get("status") == "available"
    ]
    targets = sole_declarer_targets(profiles, index, has_site)
    by_org = {str(profile.get("organisation_number") or ""): profile for profile in profiles}
    rows: list[dict] = []
    fetched = 0

    def work(target: dict) -> dict | None:
        nonlocal fetched
        host = target["host"]
        for url in (f"https://{host}/", f"https://www.{host}/"):
            raw, _note = fetch(url)
            if raw is None:
                continue
            fetched += 1
            observation = site_observation(by_org[target["organisation_number"]], url, raw.decode("utf-8", "replace"), raw, host)
            if observation:
                return observation
            break
        return None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(work, targets):
            if result:
                rows.append(result)
    rows.sort(key=lambda row: row["organisation_number"])
    write_jsonl(Path(args.output), rows)
    report = {
        "connector": "registry_sole_declarer_sites_v1",
        "profiles": len(profiles),
        "targets": len(targets),
        "fetch_attempts": fetched,
        "published": len(rows),
        "claim_boundary": "A site is published only when the register declares the domain for this organisation alone and the page body names the organisation.",
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
