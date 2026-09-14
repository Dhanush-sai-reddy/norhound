#!/usr/bin/env python3
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

UA = "SignalpostResearchPOC/1.0 (https://builderr.ai; bounded job-post discovery)"
CAREER_KEYWORDS = ("karriere", "careers", "career", "jobs", "jobb", "stillings", "stillinger", "ledige-stilling", "recruit", "ansettelse", "join", "vaare-ansatte", "vare-ansatte", "bli-en-av-oss", "bli_en_av_oss")
CAREERS_PATH = re.compile(r"(?:^|[/_-])[^/_-]*?(?:%s)[^/_-]*?(?:$|[/_-])" % "|".join(re.escape(k) for k in CAREER_KEYWORDS), re.I)
JOB_SLUG_HINTS = re.compile(r"(?:stilling|jobb|job|rekry|recruit|avdelingsleder|medarbeider|konsulent|ingeni[øo]r|l[æa]rer|sjef|direkt|utvikler|developer|selger|r[åa]dgiver)", re.I)
# Roles that read like a vacancy title in a link anchor ("R&D Manager",
# "Barnehagelærer", "Butikksjef") rather than a service category ("SEO",
# "Omstilling og nedbemanning").
ROLE_TITLE_HINTS = re.compile(
    r"(?:stilling|sjef|leder|ledelse|direkt[øo]r|medarbeider|konsulent|r[åa]dgiver|utvikler|"
    r"ingeni[øo]r|sykepleier|l[æa]rer|førskolelærer|butikkmedarbeider|salgs|selger|analytiker|"
    r"designer|koordinator|controller|regnskaps|saksbehandler|produksjon|montør|sjåf[øo]r|"
    r"sveiser|kokk|servit[øo]r|renholder|vernepleier|psykolog|fysioterapeut|trainee|praktikant|"
    r"vikariat|vikar|deltid|heltid|resident|manager|engineer|developer|design|marketing|"
    r"administrasjon|jurist|advokat|økonom|IT-?utvikler|webutvikler|programmerer|test|QA)",
    re.I,
)
# Page-level cue that the careers section actually lists vacancies, so an HR
# consultancy's *services* section (omstilling, nedbemanning, SEO) never
# produces a job_posting observation.
APPLICATION_MARKERS_PAGE = re.compile(
    r"(?:søknadsfrist|søk(?:nads)? snerk|aktiv søknad|send oss en søknad|vi søker(?: nå| aktivt)?|"
    r"søker(?: vi)? (?:til )?(?:vår|din|en|ny)|ledig(?:e)?(?: stilling| jobb| stillinger)|"
    r"har vi ledig|er vi på jakt|bli en av oss|join our team|apply(?: now| here| via link| button)|"
    r"send inn(?: din)? søknad|scroll down.*søk|har du lyst til å bli|we are hiring|we (?:are )?looking for)",
    re.I,
)
NAVIGATION_ANCHORS = {
    "les mer", "lesmeir", "read more", "se alle stillinger", "alle stillinger", "se alle jobber",
    "alle jobber", "se stillinger", "stillinger", "karriere", "careers", "jobb", "jobs", "vi søker",
    "søk", "search", "omstilling og nedbemanning", "ekspertbistand", "slik hjelper vi deg til jobb",
    "se våre ledige stillinger", "våre ledige stillinger", "stillingsutlysninger", "åpne stillinger",
}
BLOCKED_HOST_FRAGMENTS = (
    "linkedin.com", "mediabank.", "app.myscreenspace.com", "nettskjema", "webshop",
)


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


def career_page_urls(profile: dict) -> tuple[list[str], list[str]]:
    value = ((profile.get("evidence") or {}).get("website") or {}).get("value") or {}
    urls = [str(page.get("url") or "") for page in (value.get("pages") or [])]
    captured = [url for url in urls if CAREERS_PATH.search(urllib.parse.urlparse(url).path)]
    homepage = str(value.get("final_url") or "")
    probes: list[str] = []
    if homepage.startswith(("http://", "https://")):
        base = homepage.rstrip("/")
        for candidate in ("/karriere", "/ledige-stillinger", "/stillinger", "/jobber", "/careers", "/jobs", "/join-us", "/bli-en-av-oss"):
            probes.append(base + candidate)
    return captured, probes


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
    # Require page-level evidence that this careers section actually lists
    # vacancies. HR consultancies and agencies reuse /karriere/ for service
    # catalogs; without an application cue we abstain instead of risking a
    # false job_posting.
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
        # Postings are published only when the posting host is the verified
        # company's own registered domain (or a subdomain of it). Careers pages
        # routinely point at third-party ATS platforms (easycruit, Teamtailor,
        # Workday, Nordicjobs); those are acquired-mode unknowns and abstain.
        if registered_domain and not (
            host == registered_domain or host.endswith("." + registered_domain)
        ):
            continue
        # Same-registered-domain subdomains (jobs.example.no) are company-owned
        # ATS pages. They stay exact-entity ONLY when the posting page itself
        # names the legal entity; fetching and verifying each posting is out of
        # scope here, so subdomain postings are recorded but with an explicit
        # qualifier that the identity gate re-checks before publication.
        same_domain_subdomain = host != registered_domain
        path = parsed.path.casefold()
        text = str(anchor.get_text(" ", strip=True)).strip()
        if not text:
            continue
        compact_anchor = " ".join(text.split()).casefold()
        if compact_anchor in NAVIGATION_ANCHORS:
            continue
        # A posting anchor must read like a specific role/title ("Butikksjef
        # Viksund", "R&D Engineer") or the deep slug must carry an unambiguous
        # vacancy token together with either a role anchor or an application cue.
        role_anchor = bool(ROLE_TITLE_HINTS.search(text))
        slug_role = bool(JOB_SLUG_HINTS.search(path.rsplit("/", 1)[-1])) and path.count("/") >= 2
        slug_vacancy = bool(re.search(r"(?:stilling|jobb|job|rekry|recruit|ledig)", path))
        if not role_anchor:
            if not (slug_vacancy and slug_role):
                continue
        if not markers and not slug_vacancy:
            # Only navigation-adjacent deep links (e.g. a slug with "stilling")
            # survive when the section lacks explicit apply wording.
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
            "type": "job_link_parsed_from_verified_company_site",
            "company_site_url": final_url,
            "stage": "careers_page_crawl",
            "same_registered_domain": True,
            "same_registered_domain_subdomain": posting["subdomain"],
        }
        observations.append({
            "id": "company-site-job-" + hashlib.sha256(f"{org}|{url}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "company_site",
            "signal_type": "job_posting",
            "source_url": url,
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": [identity_proof],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "company_site",
            "evidence_span": posting["title"][:1200],
            "metrics": {
                "anchor_text": posting["anchor"][:200],
                "interpretation": "Job posting link discovered on the verified company careers page; not a confirmed application.",
            },
            "strategy": "jobs_feed_discovery",
        })
    return observations


def discover(profile: dict, *, timeout: float, max_bytes: int, min_interval: float = 0.0) -> tuple[list[dict], dict]:
    org = str(profile["organisation_number"])
    if not verified(profile):
        return [], {"organisation_number": org, "status": "site_not_verified"}
    pages, probes = career_page_urls(profile)
    urls = list(dict.fromkeys(pages + probes))
    if not urls:
        return [], {"organisation_number": org, "status": "no_careers_page_captured"}
    # Resolve robots once per site from the verified homepage so a blanket
    # robots.txt disallow (common on corporate sites) stops all probing.
    homepage = urls[0]
    try:
        import urllib.error
        from norway_company_agent.website import _robots_allowed
        if not _robots_allowed(homepage, timeout):
            return [], {"organisation_number": org, "status": "robots_blocked"}
    except Exception:
        pass
    all_observations = []
    page_status = {}
    for page_url in urls[:6]:
        if min_interval:
            time.sleep(min_interval)
        html, raw, final_url = fetch_page_html(page_url, timeout=timeout, max_bytes=max_bytes)
        if not raw:
            page_status[page_url] = "fetch_error"
            continue
        posts = extract_jobs_from_page(profile, page_url, html, raw, final_url)
        page_status[page_url] = f"jobs_found:{len(posts)}" if posts else "no_jobs_parsed"
        all_observations.extend(posts)
    status = "jobs_found" if all_observations else "no_jobs_parsed"
    return all_observations, {"organisation_number": org, "status": status, "pages": page_status}


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover job postings from exact-entity verified company careers pages.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--min-interval", type=float, default=0.5)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    args = parser.parse_args()
    profiles = read_jsonl(Path(args.profiles))
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(discover, profile, timeout=args.timeout, max_bytes=args.max_bytes, min_interval=args.min_interval): str(profile["organisation_number"])
            for profile in profiles if verified(profile)
        }
        for future in as_completed(futures):
            observations, status = future.result()
            results[futures[future]] = (observations, status)
    observations = [item for org, (rows, _) in results.items() for item in rows]
    write_jsonl(Path(args.output), observations)
    orgs_with_jobs = {str(row["organisation_number"]) for row in observations}
    statuses = {}
    for org, (_, status) in results.items():
        key = status.get("status", "?").replace("jobs_found", "jobs_found")
        statuses[key] = statuses.get(key, 0) + 1
    report = {
        "connector": "exact_company_site_jobs_discovery_v1",
        "verified_profiles_scanned": len(results),
        "companies_with_jobs": len(orgs_with_jobs),
        "observations": len(observations),
        "status_counts": statuses,
        "claim_boundary": "Job posting links parsed from verified company careers pages; external ATS postings reached via those links are included exact-entity only.",
        "company_results": [status for _, status in results.items()],
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "company_results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()