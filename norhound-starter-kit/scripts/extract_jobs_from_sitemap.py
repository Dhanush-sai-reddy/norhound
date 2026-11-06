#!/usr/bin/env python3
"""Extract job postings from sitemap-discovered career pages on verified company sites.

This re-uses the exact-entity sitemap pages that have job-like URLs in their
metrics.page_url, fetches them, and parses job posting anchors — similar to
extract_company_site_jobs.py but seeded from sitemap discovery rather than
homepage crawl probes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 NorHoundResearchPOC/1.0"

# Same patterns as extract_company_site_jobs.py
CAREER_KEYWORDS = (
    "karriere", "careers", "career", "jobs", "jobb", "stillings", "stillinger",
    "ledige-stilling", "recruit", "ansettelse", "join", "vaare-ansatte",
    "vare-ansatte", "bli-en-av-oss", "bli_en_av_oss",
)
CAREERS_PATH = re.compile(
    r"(?:^|[/_-])[^/_-]*?(?:%s)[^/_-]*?(?:$|[/_-])"
    % "|".join(re.escape(k) for k in CAREER_KEYWORDS),
    re.I,
)
JOB_SLUG_HINTS = re.compile(
    r"(?:stilling|jobb|job|rekry|recruit|avdelingsleder|medarbeider|konsulent|ingeni[øo]r|l[æa]rer|sjef|direkt|utvikler|developer|selger|r[åa]dgiver)",
    re.I,
)
ROLE_TITLE_HINTS = re.compile(
    r"(?:stilling|sjef|leder|ledelse|direkt[øo]r|medarbeider|konsulent|r[åa]dgiver|utvikler|"
    r"ingeni[øo]r|sykepleier|l[æa]rer|f[øo]rskolel[æa]rer|butikkmedarbeider|salgs|selger|analytiker|"
    r"designer|koordinator|controller|regnskaps|saksbehandler|produksjon|mont[øo]r|sj[åa]f[øo]r|"
    r"sveiser|kokk|servit[øo]r|renholder|vernepleier|psykolog|fysioterapeut|trainee|praktikant|"
    r"vikariat|vikar|deltid|heltid|resident|manager|engineer|developer|design|marketing|"
    r"administrasjon|jurist|advokat|[øo]konom|IT-?utvikler|webutvikler|programmerer|test|QA)",
    re.I,
)
APPLICATION_MARKERS_PAGE = re.compile(
    r"(?:s[øo]knadsfrist|s[øo]k(?:nads)? snerk|aktiv s[øo]knad|send oss en s[øo]knad|vi s[øo]ker(?: n[åa]| aktivt)?|"
    r"s[øo]ker(?: vi)? (?:til )?(?:v[åa]r|din|en|ny)|ledig(?:e)?(?: stilling| jobb| stillinger)|"
    r"har vi ledig|er vi p[åa] jakt|bli en av oss|join our team|apply(?: now| here| via link| button)|"
    r"send inn(?: din)? s[øo]knad|scroll down.*s[øo]k|har du lyst til [åa] bli|we are hiring|we (?:are )?looking for|"
    r"karriere|careers|ledige stillinger|v[åa]re stillinger|jobber hos oss|stillinger|open positions|vacancies|"
    r"stillinger vi har|jobbe hos|bli med|dine nye kolleger|utviklingsmuligheter|din karriere|"
    r"stillingstype|heltid|deltid|startdato|start dato|ansvar|oppgaver|kvalifikasjoner|vi tilbyr|"
    r"arbeidsgiver|arbeidssted|l[øo]nn|pensjon|feriepenger|avtale|kollektiv|fagforening)",
    re.I,
)
NAVIGATION_ANCHORS = {
    "les mer", "lesmeir", "read more", "se alle stillinger", "alle stillinger", "se alle jobber",
    "alle jobber", "se stillinger", "stillinger", "karriere", "careers", "jobb", "jobs", "vi s[øo]ker",
    "s[øo]k", "search", "omstilling og nedbemanning", "ekspertbistand", "slik hjelper vi deg til jobb",
    "se v[åa]re ledige stillinger", "v[åa]re ledige stillinger", "stillingsutlysninger", "[åa]pne stillinger",
}
GENERIC_ANCHOR = re.compile(
    r"^(ledige stillinger|ledelsen( og styret)?|styret|design|kontakt( oss)?|om oss|nyheter|"
    r"personvern(erkl[æa]ring)?|informasjonskapsler|cookies?|"
    r"salgs- og leveringsbetingelser|salgsbetingelser|leveringsbetingelser|betingelser|"
    r"(salgs|kj?[øo]ps)?[ -]?vilk[åa]r(ene)?|les vilk[åa]rene|bestill \w+|"
    r"handlekurv|logg inn|forsiden|"
    r"hjem|home|meny|menu|tilbake|se mer)$|"
    r"(want to see .*statistics|important reading|recruitment scam|workforce.*statistics|"
    r"unng[åa] svindel|svindelfors[øo]k)",
    re.I,
)
TITLE_SHAPE = re.compile(r"[A-Za-zÆØÅæøå]{3}")
BLOCKED_HOST_FRAGMENTS = (
    "linkedin.com", "mediabank.", "app.myscreenspace.com", "nettskjema", "webshop",
)

# --- Date extraction ---
ISO_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
NO_MONTHS = {m: i + 1 for i, m in enumerate((
    "januar", "februar", "mars", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "desember"))}
NO_DATE = re.compile(r"(\d{1,2})\.?\s+(" + "|".join(NO_MONTHS) + r")\s+(20\d{2})", re.I)
NUMERIC_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(20\d{2})")


def find_dates(text: str) -> list[str]:
    found = set()
    for match in ISO_DATE.findall(text or ""):
        found.add(f"{match[0]}-{match[1]}-{match[2]}")
    for day, month, year in NO_DATE.findall(text or ""):
        found.add(f"{year}-{NO_MONTHS[month.casefold()]:02d}-{int(day):02d}")
    for day, month, year in NUMERIC_DATE.findall(text or ""):
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            found.add(f"{year}-{int(month):02d}-{int(day):02d}")
    return sorted(found)


def date_from_page_body(html: str | bytes) -> str | None:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text)
    dates = find_dates(text)
    return dates[-1] if dates else None


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def verified(profile: dict) -> bool:
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    return website.get("status") == "available" and identity.get("publishable")


def fetch_page_html(url: str, *, timeout: float, max_bytes: int) -> tuple[str, bytes, str | None]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
        final_url = response.geturl()
        if len(raw) > max_bytes:
            return "", b"", "oversized_page"
        return raw.decode("utf-8", errors="replace"), raw, final_url
    except Exception as exc:
        return "", b"", f"{type(exc).__name__}: {str(exc)[:120]}"


def extract_jobs_from_page(profile: dict, page_url: str, html: str, raw: bytes, final_url: str) -> list[dict]:
    org = str(profile["organisation_number"])
    value = ((profile.get("evidence") or {}).get("website") or {}).get("value") or {}
    registered_domain = str(value.get("registered_domain") or "").casefold().lstrip(".")

    soup = BeautifulSoup(html, "lxml")
    page_text = " ".join(soup.get_text(" ", strip=True).split())[:200_000]
    markers = bool(APPLICATION_MARKERS_PAGE.search(page_text))
    base = page_url.rsplit("/", 1)[0] + "/" if not page_url.endswith("/") else page_url

    postings = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urllib.parse.urljoin(base, href)
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or any(fragment in host for fragment in BLOCKED_HOST_FRAGMENTS):
            continue
        # Same-registered-domain (or subdomain) postings only
        if registered_domain and not (host == registered_domain or host.endswith("." + registered_domain)):
            continue
        same_domain_subdomain = host != registered_domain
        path = parsed.path.casefold()
        text = str(anchor.get_text(" ", strip=True)).strip()
        if not text:
            continue
        compact_anchor = " ".join(text.split()).casefold()
        if compact_anchor in NAVIGATION_ANCHORS:
            continue
        if GENERIC_ANCHOR.search(compact_anchor):
            continue
        if not (3 <= len(compact_anchor) <= 120 and len(compact_anchor.split()) <= 14 and TITLE_SHAPE.search(compact_anchor)):
            continue
        role_anchor = bool(ROLE_TITLE_HINTS.search(text))
        last_seg = path.rsplit("/", 1)[-1]
        slug_role = bool(JOB_SLUG_HINTS.search(last_seg)) and path.count("/") >= 2 and "-" in last_seg
        slug_vacancy = bool(re.search(r"(?:stilling|jobb|job|rekry|recruit|ledig)", path))
        if not role_anchor:
            if not (slug_vacancy and slug_role):
                continue
        if not markers and not slug_vacancy:
            continue
        postings[url] = {
            "url": url,
            "title": text[:500],
            "anchor": text,
            "subdomain": same_domain_subdomain,
        }

    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256(raw).hexdigest()
    observations = []

    for url in sorted(postings):
        posting = postings[url]
        identity_proof = {
            "type": "job_link_parsed_from_sitemap_career_page",
            "company_site_url": final_url,
            "stage": "sitemap_career_page_crawl",
            "same_registered_domain": True,
            "same_registered_domain_subdomain": posting["subdomain"],
        }

        # Extract date from the posting page (reuse the already-fetched page if it's the career page)
        observed_at = None
        if page_url == url:
            observed_at = date_from_page_body(html)
        if not observed_at:
            observed_at = retrieved_at[:10]

        observations.append({
            "id": "company-site-job-" + hashlib.sha256(f"{org}|{url}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "company_site",
            "signal_type": "job_posting",
            "source_url": url,
            "retrieved_at": retrieved_at,
            "observed_at": observed_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": [identity_proof],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_site",
            "evidence_span": posting["title"][:1200],
            "metrics": {
                "anchor_text": posting["anchor"][:200],
                "career_page_url": page_url,
                "interpretation": "Job posting link discovered on verified company career page (via sitemap); not a confirmed application.",
            },
            "strategy": "jobs_feed_discovery",
        })
    return observations


def discover_from_sitemap(profile: dict, *, timeout: float, max_bytes: int, min_interval: float = 0.0) -> tuple[list[dict], dict]:
    org = str(profile["organisation_number"])
    if not verified(profile):
        return [], {"organisation_number": org, "status": "site_not_verified"}

    # Find sitemap pages with job-like URLs from the external observations
    # We'll read from the merged external file
    return [], {"organisation_number": org, "status": "not_implemented_yet"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract job postings from sitemap-discovered career pages on verified company sites.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--sitemap-obs", required=True, help="External observations JSONL containing sitemap_page signals")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--min-interval", type=float, default=0.5)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    parser.add_argument("--per-org-limit", type=int, default=10, help="Max career pages to crawl per org")
    args = parser.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    profile_map = {str(p["organisation_number"]): p for p in profiles}

    # Load sitemap pages with job-like URLs
    sitemap_by_org: dict[str, list[dict]] = {}
    for line in Path(args.sitemap_obs).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obs = json.loads(line)
        if obs.get("signal_type") != "sitemap_page":
            continue
        page_url = obs.get("metrics", {}).get("page_url", "")
        if not page_url:
            continue
        if not CAREERS_PATH.search(urllib.parse.urlparse(page_url).path):
            continue
        org = str(obs.get("organisation_number"))
        if org not in profile_map:
            continue
        if not verified(profile_map[org]):
            continue
        sitemap_by_org.setdefault(org, []).append(obs)

    print(f"Found sitemap career pages for {len(sitemap_by_org)} orgs")

    all_observations = []
    statuses = {}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for org, obs_list in sitemap_by_org.items():
            profile = profile_map[org]
            # Dedupe by page_url
            seen = set()
            unique_obs = []
            for obs in obs_list:
                url = obs.get("metrics", {}).get("page_url", "")
                if url not in seen:
                    seen.add(url)
                    unique_obs.append(obs)
            # Limit per org
            unique_obs = unique_obs[:args.per_org_limit]

            for obs in unique_obs:
                page_url = obs.get("metrics", {}).get("page_url", "")
                futures[pool.submit(
                    crawl_single_page, profile, page_url, args.timeout, args.max_bytes
                )] = (org, page_url)

        for future in as_completed(futures):
            org, page_url = futures[future]
            try:
                observations, status = future.result()
                all_observations.extend(observations)
                statuses.setdefault(org, {"pages_crawled": 0, "jobs_found": 0, "page_statuses": {}})
                statuses[org]["pages_crawled"] += 1
                statuses[org]["jobs_found"] += len(observations)
                statuses[org]["page_statuses"][page_url] = f"jobs_found:{len(observations)}" if observations else "no_jobs_parsed"
            except Exception as exc:
                statuses.setdefault(org, {"pages_crawled": 0, "jobs_found": 0, "page_statuses": {}})
                statuses[org]["pages_crawled"] += 1
                statuses[org]["page_statuses"][page_url] = f"error: {exc}"

    write_jsonl(Path(args.output), all_observations)

    orgs_with_jobs = {str(row["organisation_number"]) for row in all_observations}
    report = {
        "connector": "exact_company_site_jobs_from_sitemap_v1",
        "orgs_with_sitemap_career_pages": len(sitemap_by_org),
        "verified_profiles_scanned": len(statuses),
        "companies_with_jobs": len(orgs_with_jobs),
        "observations": len(all_observations),
        "claim_boundary": "Job posting links parsed from verified company career pages discovered via sitemap; same-registered-domain only.",
        "status_summary": {k: sum(1 for v in statuses.values() if v.get(k)) for k in ("jobs_found", "no_jobs_parsed", "error")},
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def crawl_single_page(profile: dict, page_url: str, timeout: float, max_bytes: int) -> tuple[list[dict], str]:
    html, raw, final_url = fetch_page_html(page_url, timeout=timeout, max_bytes=max_bytes)
    if not raw:
        return [], "fetch_error"
    posts = extract_jobs_from_page(profile, page_url, html, raw, final_url)
    return posts, "jobs_found" if posts else "no_jobs_parsed"


if __name__ == "__main__":
    main()