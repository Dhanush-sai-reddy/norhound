#!/usr/bin/env python3
"""Publish real job postings from a company's applicant-tracking system (ATS).

Discovers an ATS link on the verified company site (careers page), then queries
the ATS's public JSON/RSS feed for genuine role cards. Identity basis is
"linked_from_verified_site": the ATS link was published by the exact-identity
company site, so the postings belong to that exact entity.

Supports: Workday, Lever, Greenhouse, SmartRecruiters, Teamtailor (RSS).
No API key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.website import USER_AGENT, _robots_allowed, assert_public_url  # noqa: E402

CAREER_PATHS = ("/careers", "/karriere", "/job", "/jobb", "/jobs", "/ledige-stillinger", "/om-oss/jobb-hos-oss/", "/about/careers")
ATS_PATTERN = re.compile(
    r"https?://(?:"
    r"(?P<workday>[a-z0-9-]+)\.wd(?P<wdn>\d+)\.myworkdayjobs\.com/(?P<wdsite>[A-Za-z0-9_-]+)"
    r"|jobs\.lever\.co/(?P<lever>[A-Za-z0-9-]+)"
    r"|boards\.greenhouse\.io/(?P<greenhouse>[A-Za-z0-9-]+)"
    r"|job-boards\.greenhouse\.io/(?P<greenhouse2>[A-Za-z0-9-]+)"
    r"|(?P<smart>[A-Za-z0-9-]+)\.smartrecruiters\.com"
    r"|(?P<teamtailor>[A-Za-z0-9-]+)\.teamtailor\.com"
    r"|(?P<workable>apply\.workable\.com/(?P<workable_slug>[A-Za-z0-9_-]+))"
    r"|(?P<webcruiter>[A-Za-z0-9-]+\.webcruiter\.com)"
    r"|(?P<jobylon>www\.jobylon\.com/jobs/(?P<jobylon_id>\d+))"
    r"|(?P<reachmee>[A-Za-z0-9-]+\.reachmee\.com)"
    r"|(?P<hrmanager>[A-Za-z0-9-]+\.hr-manager\.net)"
    r"|(?P<recman>[A-Za-z0-9-]+\.recman\.no)"
    r"|(?P<easycruit>[A-Za-z0-9-]+\.easycruit\.com)"
    r"|(?P<jobbnorge>www\.jobbnorge\.no)"
    r")", re.I)
LINKED_ATS_PROVIDERS = ("workable", "webcruiter", "jobylon", "reachmee", "hrmanager", "recman", "easycruit", "jobbnorge")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def http(url: str, *, data: bytes | None = None, timeout: float = 12.0, max_bytes: int = 500_000, headers: dict | None = None) -> bytes | None:
    try:
        assert_public_url(url)
    except ValueError:
        return None
    h = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html,application/rss+xml,*/*"}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, data=data, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read(max_bytes)
    except Exception:
        return None


def fetch_html(url: str) -> str | None:
    if not _robots_allowed(url, 8.0):
        return None
    raw = http(url, max_bytes=500_000)
    return raw.decode("utf-8", "replace") if raw else None


CAREERS_LINK_RE = re.compile(
    r"/(karriere|careers|jobb?|jobs|ledige-stillinger|stillinger|job-hos-oss)(/|$|\?)", re.I)
CAREERS_LINK_LIMIT = 5


def _iter_anchor_hrefs(html: str):
    from html.parser import HTMLParser

    class _A(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                for k, v in attrs:
                    if k.lower() == "href" and v:
                        self.hrefs.append(v)

    p = _A()
    p.feed(html)
    return p.hrefs


def collect_careers_page_links(home_html: str, site: str) -> list[str]:
    site_netloc = urllib.parse.urlparse(site).netloc.lower()
    out = []
    seen = set()
    for href in _iter_anchor_hrefs(home_html):
        url = urllib.parse.urljoin(site, href)
        parts = urllib.parse.urlparse(url)
        if parts.netloc.lower() != site_netloc:
            continue
        if not CAREERS_LINK_RE.search(parts.path):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= CAREERS_LINK_LIMIT:
            break
    return out


ROLE_STOPWORDS = (
    "logg", "kontakt", "personvern", "cookies", "vilkår", "hjem", "meny",
    "les mer her", "les mer", "abonner", "del", "les saken", "forrige",
    "neste", "se alle", "alle ledige",
)
ROLE_CARD_LIMIT = 20
ROLE_TEXT_MIN = 3
ROLE_TEXT_MAX = 140


def extract_role_cards(html: str, base: str) -> list[dict]:
    from html.parser import HTMLParser

    class _Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.items = []
            self._href = None
            self._parts = []

        def handle_starttag(self, tag, attrs):
            if tag == "a" and self._href is None:
                for k, v in attrs:
                    if k.lower() == "href" and v:
                        self._href = v
                        self._parts = []
                        break
                else:
                    self._href = None

        def handle_endtag(self, tag):
            if tag == "a" and self._href is not None:
                self.items.append((self._href, "".join(self._parts)))
                self._href = None
                self._parts = []

        def handle_data(self, data):
            if self._href is not None:
                self._parts.append(data)

    p = _Links()
    p.feed(html)
    base_netloc = urllib.parse.urlparse(base).netloc.lower()
    out = []
    seen = set()
    for href, raw_text in p.items:
        url = urllib.parse.urljoin(base, href)
        parts = urllib.parse.urlparse(url)
        if parts.netloc.lower() != base_netloc:
            continue
        text = " ".join(raw_text.split())
        if not (ROLE_TEXT_MIN <= len(text) <= ROLE_TEXT_MAX):
            continue
        if len(text.split()) < 2:
            continue
        low = text.lower()
        if any(low.startswith(w) for w in ROLE_STOPWORDS):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append({"title": text, "url": url})
        if len(out) >= ROLE_CARD_LIMIT:
            break
    return out


def find_ats(html: str) -> re.Match | None:
    return ATS_PATTERN.search(html)


def workday_jobs(tenant: str, wdn: str, site: str) -> list[dict]:
    url = f"https://{tenant}.wd{wdn}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    body = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}).encode()
    raw = http(url, data=body, headers={"Content-Type": "application/json"})
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    out = []
    for j in data.get("jobPostings", []) or []:
        title = j.get("title")
        path = j.get("externalPath")
        if not title:
            continue
        out.append({"title": title, "url": f"https://{tenant}.wd{wdn}.myworkdayjobs.com/{site}{path}" if path else url, "posted": j.get("postedOn")})
    return out


def lever_jobs(co: str) -> list[dict]:
    raw = http(f"https://api.lever.co/v0/postings/{co}")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return [{"title": j.get("text"), "url": j.get("hostedUrl"), "posted": None} for j in data if j.get("text")]


def greenhouse_jobs(token: str) -> list[dict]:
    raw = http(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return [{"title": j.get("title"), "url": j.get("absolute_url"), "posted": j.get("updated_at")} for j in data.get("jobs", []) if j.get("title")]


def smartrecruiters_jobs(co: str) -> list[dict]:
    raw = http(f"https://api.smartrecruiters.com/v1/companies/{co}/postings")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    out = []
    for j in data.get("content", []) or []:
        if j.get("name"):
            out.append({"title": j["name"], "url": None, "posted": j.get("releasedDate")})
    return out


def teamtailor_jobs(slug: str) -> list[dict]:
    raw = http(f"https://{slug}.teamtailor.com/jobs.rss")
    if not raw:
        return []
    text = raw.decode("utf-8", "replace")
    out = []
    for block in re.findall(r"<item>(.*?)</item>", text, re.S):
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S)
        l = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        if t:
            out.append({"title": t.group(1).strip(), "url": l.group(1).strip() if l else None, "posted": d.group(1).strip() if d else None})
    return out


def process(profile: dict) -> list[dict]:
    ev = (profile.get("evidence") or {}).get("website") or {}
    if ev.get("status") != "available":
        return []
    val = ev.get("value") or {}
    ident = val.get("identity_assessment") or {}
    if str(ident.get("status") or "").lower() not in {"exact", "related_or_uncertain"}:
        return []
    site = ev.get("source_url") or val.get("final_url") or ""
    if not site:
        return []
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(site))
    home_html = fetch_html(site)
    pages: list[tuple[str, str | None]] = []
    if home_html:
        pages.append((site, home_html))
        pages.extend((link, None) for link in collect_careers_page_links(home_html, site))
    pages.extend((base + p, None) for p in CAREER_PATHS)
    match = None
    ats_page = None
    for page, cached in pages:
        html = cached if cached is not None else fetch_html(page)
        if not html:
            continue
        m = find_ats(html)
        if m:
            match = m
            ats_page = page
            break
    if not match:
        return []
    gd = match.groupdict()
    try:
        if gd.get("workday"):
            jobs = workday_jobs(gd["workday"], gd["wdn"], gd["wdsite"])
            ats = "workday"
        elif gd.get("lever"):
            jobs = lever_jobs(gd["lever"]); ats = "lever"
        elif gd.get("greenhouse") or gd.get("greenhouse2"):
            jobs = greenhouse_jobs(gd.get("greenhouse") or gd.get("greenhouse2")); ats = "greenhouse"
        elif gd.get("smart"):
            jobs = smartrecruiters_jobs(gd["smart"]); ats = "smartrecruiters"
        elif gd.get("teamtailor"):
            jobs = teamtailor_jobs(gd["teamtailor"]); ats = "teamtailor"
        else:
            provider = next((k for k in LINKED_ATS_PROVIDERS if gd.get(k)), None)
            if not provider:
                return []
            ats = provider
            ats_url = match.group(0)
            host = re.sub(r"^https?://", "", ats_url, flags=re.I)
            full = re.search(r'href=["\']([^"\']*' + re.escape(host) + r'[^"\'\s#]*)["\']', html, re.I)
            if full:
                ats_url = urllib.parse.urljoin(page, full.group(1))
            elif not ats_url.lower().startswith("http"):
                ats_url = "https://" + ats_url
            ats_html = fetch_html(ats_url)
            if not ats_html:
                return []
            jobs = extract_role_cards(ats_html, ats_url)
    except Exception:
        return []
    org = str(profile["organisation_number"])
    rows = []
    for j in jobs[:20]:
        if not j.get("title"):
            continue
        digest = hashlib.sha256(f"{org}|{j.get('url') or j['title']}".encode()).hexdigest()[:16]
        rows.append({
            "organisation_number": org,
            "platform": "job_board",
            "source_url": j.get("url") or ats_page,
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "content_sha256": hashlib.sha256((j["title"] + str(j.get("posted"))).encode()).hexdigest(),
            "exact_entity": True,
            "identity_proof": [{"type": "linked_from_verified_site", "ats": ats, "ats_link_page": ats_page, "company_site": site}],
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "job_board",
            "strategy": "ats_role_card",
            "id": f"ats-job-{org}-{ats}-{digest}",
            "signal_type": "job_posting",
            "evidence_span": f"{j['title']} ({ats} role card via {site})"[:1200],
            "metrics": {"ats": ats, "posted": j.get("posted"), "role_card": True},
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    if args.limit:
        profiles = profiles[: args.limit]
    out: list[dict] = []
    stats = {"profiles": 0, "companies": 0, "jobs": 0, "ats_counts": {}}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process, p): p for p in profiles}
        for fut in as_completed(futures):
            stats["profiles"] += 1
            rows = fut.result() or []
            out.extend(rows)
            for r in rows:
                a = (r.get("metrics") or {}).get("ats")
                stats["ats_counts"][a] = stats["ats_counts"].get(a, 0) + 1
    stats["companies"] = len({r["organisation_number"] for r in out})
    stats["jobs"] = len(out)
    write_jsonl(Path(args.output), out)
    stats["output"] = args.output
    Path(args.report).write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
