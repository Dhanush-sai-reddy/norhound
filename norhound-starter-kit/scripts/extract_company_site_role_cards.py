#!/usr/bin/env python3
"""Publish role cards from a company's identity-gated website.

A careers page says a company has a careers section. A **role card** says a
company has a *specific open role* and how to apply for it: a role title and an
apply action on a page of the company's own site. The shipped jobs connector
published zero role cards (all 159 rows were `careers_page`), so the hiring
family — the only scored family below 99 % (49 / 84 companies) — left the
companies that do publish their vacancies empty.

Four rules decide whether a page becomes a role card, and all four must hold:

1. **Page**: the page is HTML on the verified company's own registered domain
   (or a subdomain of it). A link to a third-party board is not the company's
   own page and is not published here.
2. **Title**: the page names a role — a JSON-LD `JobPosting.title`, a heading,
   a "vi søker ..." line, or the link text that led to it. The title must not
   be a generic label ("Ledige stillinger", "Jobb hos oss"), must not be a
   negation ("vi har ingen ledige stillinger"), and must not be the company's
   own name.
3. **Apply action**: the page carries an action that applies for the role — a
   link or button whose label or target says so (`Søk på stillingen`,
   `Send søknad`, `apply`). A same-page `#fragment` counts only when the page
   really contains a form with a submit control.
4. **Identity**: the page names the company — its organisation number, at
   least half of its distinctive legal-name tokens, or the host BRREG declares
   for it. This is what keeps a group site from publishing another entity's
   vacancy.

Every emitted row carries the source URL, the retrieval time, the SHA-256 of
the page body, the date the page states (when it states one) and the identity
proof, so the fail-safe verifier can re-derive the decision from frozen
evidence.

Usage:
    uv run python scripts/extract_company_site_role_cards.py \
        --profiles out/frozen/web1000-profiles.jsonl \
        --output out/rolecards.jsonl \
        --report out/rolecards-report.json
"""

from __future__ import annotations

import argparse
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
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from norway_company_agent.website import (  # noqa: E402
    SAFE_OPENER,
    USER_AGENT,
    _registered_domain,
    _robots_allowed,
    assert_public_url,
)
from extract_company_site_careers import CAREERS_PATH  # noqa: E402
from extract_company_site_news import date_from_page_body, find_publication_datetime  # noqa: E402
from verify_and_label_observations import _fold, _legal_name_tokens  # noqa: E402

# How many role cards one company may publish, and how many role links one
# careers page may contribute. Both bounds keep a rerun byte-identical.
MAX_CARDS = 8
MAX_ROLE_LINKS = 12

# Careers sections that are worth probing when the frozen homepage mentions
# hiring at all. The probe is skipped otherwise, so most companies cost no
# request.
CAREERS_PROBES = (
    "/karriere",
    "/ledige-stillinger",
    "/stillinger",
    "/jobber",
    "/careers",
    "/jobs",
    "/join-us",
    "/bli-en-av-oss",
)

# A URL that names a vacancy: the page path itself is evidence that the page
# is about a role, not about the careers section.
VACANCY_PATH = re.compile(
    r"(?:stilling|stillinger|jobb|job|jobber|rekry|recruit|ledig|vakt|intern|"
    r"praktikant|trainee|stillings|jobs)",
    re.I,
)

# Link text that names a vacancy.
ROLE_CUE = re.compile(
    r"(vi\s+s[øo]ker|ledige\s+stillinger|open\s+positions|available\s+positions|"
    r"jobb\s+hos\s+oss|bli\s+en\s+av\s+oss|stillinger|utlyser\s+stilling)",
    re.I,
)

# The frozen homepage mentions hiring: only then is a careers probe worth it.
CAREERS_CUE = re.compile(
    r"(karriere|career|jobb|job|stilling|ledige\s+stillinger|bli\s+en\s+av\s+oss|"
    r"join\s+us|ansettelse|rekry)",
    re.I,
)

# An action that applies for a role.
APPLY_HINT = re.compile(
    r"(s[øo]knad|soknad|apply|s[øo]k\s+p[åa]\s+stilling|stillingss[øo]knad|"
    r"send\s+(?:inn\s+)?s[øo]knad|melde\s+deg|s[øo]k\s+stilling)",
    re.I,
)

# Titles that are not a role.
GENERIC_TITLE = re.compile(
    r"(ledige\s+stillinger|v[åa]re\s+stillinger|stillingsliste|stillingsoversikt|"
    r"stillinger\b|jobb\s+hos\s+oss|jobs\s+hos\s+oss|job\s+openings|karriere|"
    r"careers?\b|open\s+positions|available\s+positions|om\s+oss|kontakt|nyheter|"
    r"vi\s+s[øo]ker|vil\s+du\s+jobbe|bli\s+en\s+av\s+oss)",
    re.I,
)

# A lead-in that introduces the role, stripped before the title is judged.
LEAD_IN = re.compile(
    r"^(?:fremhevet|vi\s+s[øo]ker(?:\s+en|\s+til|\s+deg\s+som:)?|"
    r"ledige\s+stillinger|jobb\s+hos\s+oss|vil\s+du\s+jobbe\s+med\s+oss|"
    r"bli\s+en\s+av\s+oss)\s*:?\s*",
    re.I,
)

# A page that says it has no open position.
NEGATION = re.compile(
    r"(ingen\s+(?:ledige\s+)?stillinger|vi\s+har\s+ingen|ikke\s+ledige\s+stillinger|"
    r"no\s+open\s+positions)",
    re.I,
)

# "Vi søker en BPA-assistent" — the role named in the body copy.
ROLE_BODY = re.compile(r"vi\s+s[øo]ker\s+(?:en\s+|til\s+|deg\s+som:?\s*)?([^.!?\n]{3,80})", re.I)

# A role title must name a ROLE. A live probe published "FACEBOOK",
# "Hovedlenker topp", "Job opportunities" and "Internasjonalisering" as job
# titles: those are navigation labels and prose, not roles. Requiring a
# role-indicating token keeps the title claim honest.
ROLE_TOKEN = re.compile(
    r"(stilling|stillinger|rolle|roller|manager|leder|ledere|sjef|"
    r"direkt[øo]r|assistent|assistenter|medarbeider|utvikler|ingeni[øo]r|"
    r"konsulent|r[åa]dgiver|sykepleier|psykolog|sykolog|lege|l[æa]rer|"
    r"pedagog|elektriker|operat[øo]r|mont[øo]r|sveiser|kokk|servit[øo]r|"
    r"selger|salgs|analytiker|designer|koordinator|controller|regnskapsf[øo]rer|"
    r"saksbehandler|innkj[øo]pssjef|prosjektleder|skrivetalent|markedsf[øo]rer|"
    r"innholdsprodusent|grafiker|journalist|fotograf|trainee|praktikant|"
    r"internship|engineer|developer|specialist|technician|supervisor|"
    r"deltidsjobb|heltidsjobb|dr[øo]mmejobb|vakans|vacanc|position)",
    re.I,
)

MAX_BODY_EXCERPT = 600
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


def site_domain(profile: dict) -> str:
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    domain = str(value.get("registered_domain") or "").strip().lower().lstrip(".")
    if domain:
        return domain
    return _registered_domain(str(value.get("final_url") or website.get("source_url") or "")).lower()


def publishable(profile: dict) -> bool:
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    return website.get("status") == "available" and bool(identity.get("publishable"))


def careers_page_urls(profile: dict) -> list[str]:
    """The careers pages of this company: the captured ones and the probes.

    The probes are only worth a request when the frozen homepage mentions
    hiring at all; that keeps the connector at roughly one request per company
    that has any hiring signal.
    """
    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    urls: list[str] = []
    for page in value.get("pages") or []:
        url = str(page.get("url") or "")
        if url.startswith(("http://", "https://")) and CAREERS_PATH.search(urllib.parse.urlparse(url).path):
            urls.append(url)
    homepage = str(value.get("final_url") or website.get("source_url") or "")
    excerpt = " ".join(
        str(value.get(key) or "")
        for key in ("title", "description", "main_text_excerpt")
    )
    if homepage.startswith(("http://", "https://")) and CAREERS_CUE.search(excerpt):
        base = homepage.rstrip("/")
        urls.extend(base + probe for probe in CAREERS_PROBES)
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _same_site(host: str, domain: str) -> bool:
    if not domain:
        return False
    return host == domain or host.endswith("." + domain)


def role_links(html: str, base_url: str, registered_domain: str, *, limit: int = MAX_ROLE_LINKS) -> list[str]:
    """Same-domain links from a careers page that point at a role."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urllib.parse.urljoin(base_url, href).split("#")[0]
        if absolute in seen:
            continue
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        host = (parsed.hostname or "").lower()
        if not _same_site(host, registered_domain):
            continue
        label = anchor.get_text(" ", strip=True)
        if not (VACANCY_PATH.search(parsed.path) or ROLE_CUE.search(label)):
            continue
        seen.add(absolute)
        links.append(absolute)
        if len(links) >= limit:
            break
    return links


def _clean_title(text: str, profile: dict) -> str | None:
    """A role title, or None when the text is not one."""
    value = " ".join(str(text or "").split()).strip(" -–—|·•\t")
    if not value:
        return None
    value = LEAD_IN.sub("", value, count=1).strip()
    if not value:
        return None
    if value.casefold().startswith("hos "):
        return None
    if value.endswith(":"):
        return None
    if NEGATION.search(value):
        return None
    if GENERIC_TITLE.search(value):
        return None
    if not 3 <= len(value) <= 120:
        return None
    if len(value.split()) > 14:
        return None
    if sum(1 for character in value if character.isalpha()) < 3:
        return None
    if not ROLE_TOKEN.search(value):
        return None
    name = " ".join(str(profile.get("name") or "").casefold().split())
    if value.casefold() == name:
        return None
    return value


def _jsonld_role_titles(html: str) -> list[str]:
    try:
        import extruct

        structured = extruct.extract(html, syntaxes=["json-ld"])
    except Exception:
        return []
    titles: list[str] = []
    for block in structured.get("json-ld", []) or []:
        items = block if isinstance(block, list) else [block]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph") if isinstance(item.get("@graph"), list) else [item]
            for node in graph:
                if isinstance(node, dict) and "JobPosting" in str(node.get("@type", "")):
                    title = node.get("title")
                    if isinstance(title, str) and title.strip():
                        titles.append(title.strip())
    return titles


def role_title(html: str, url: str, hint: str | None = None, *, profile: dict | None = None) -> str | None:
    """The role the page names, or None when it names none."""
    profile = profile or {}
    for candidate in _jsonld_role_titles(html):
        cleaned = _clean_title(candidate, profile)
        if cleaned:
            return cleaned
    soup = BeautifulSoup(html, "lxml")
    for tag in ("h1", "h2"):
        node = soup.find(tag)
        if node:
            cleaned = _clean_title(node.get_text(" ", strip=True), profile)
            if cleaned:
                return cleaned
    text = soup.get_text(" ", strip=True)
    match = ROLE_BODY.search(text)
    if match:
        cleaned = _clean_title(match.group(1), profile)
        if cleaned:
            return cleaned
    if hint:
        cleaned = _clean_title(hint, profile)
        if cleaned:
            return cleaned
    return None


def apply_actions(html: str) -> list[dict]:
    """The apply actions on the page."""
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form")
    submit = False
    if form is not None:
        submit = bool(
            form.find("input", attrs={"type": "submit"})
            or form.find("button", attrs={"type": "submit"})
            or form.find("button")
        )
    actions: list[dict] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        label = anchor.get_text(" ", strip=True)
        if not href or href.startswith(("javascript:", "tel:")):
            continue
        decoded = urllib.parse.unquote(href)
        if not (APPLY_HINT.search(label) or APPLY_HINT.search(decoded)):
            continue
        if href.startswith("#") and not submit:
            # A fragment that only scrolls to a form is not an apply action
            # unless the form really submits something.
            continue
        actions.append({"label": label[:120], "href": href[:300]})
    return actions


def identity_ok(page_text: str, profile: dict, host: str) -> bool:
    """True when the page names this organisation."""
    org = str(profile.get("organisation_number") or "")
    digits = re.sub(r"\D", "", page_text or "")
    if org and org in digits:
        return True
    tokens = _legal_name_tokens(str(profile.get("name") or ""))
    if tokens:
        folded = _fold(page_text or "")
        hits = sum(1 for token in tokens if token in folded)
        if hits >= max(1, -(-len(tokens) // 2)):
            return True
    declared = _registered_domain(str(profile.get("website") or "")).lower()
    if declared and host and declared == host:
        return True
    return False


def role_card(profile: dict, url: str, html: str, raw: bytes, *, hint: str | None = None) -> dict | None:
    """One role-card observation, or None when the page is not a role card."""
    if not publishable(profile):
        return None
    domain = site_domain(profile)
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not _same_site(host, domain):
        return None
    title = role_title(html, url, hint, profile=profile)
    if not title:
        return None
    actions = apply_actions(html)
    if not actions:
        return None
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    if not identity_ok(text, profile, host):
        return None

    website = (profile.get("evidence") or {}).get("website") or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    published = find_publication_datetime(html)
    date_precision = "machine_readable" if published else None
    if not published:
        mined = date_from_page_body(html)
        if mined:
            published = mined
            date_precision = "mined_from_text"
    action = actions[0]
    org = str(profile["organisation_number"])
    observation = {
        "id": "company-site-role-" + hashlib.sha256(f"{org}|{url}".encode()).hexdigest()[:24],
        "organisation_number": org,
        "platform": "company_site",
        "signal_type": "job_posting",
        "source_url": url,
        "retrieved_at": website.get("retrieved_at"),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "exact_entity": True,
        "identity_proof": [
            {"type": "website_identity_gate", "score": identity.get("score"), "method": identity.get("method")},
            {
                "type": "company_site_role_card",
                "role_title": title,
                "apply_url": action["href"],
                "same_registered_domain": True,
            },
        ],
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "source_class": "company_site",
        "evidence_span": (f"{title}\n\nApply: {action['label']} -> {action['href']}\n\n{text}")[:1200],
        "metrics": {
            "job_title": title,
            "apply_url": action["href"],
            "apply_label": action["label"],
            "employer": str(profile.get("name") or ""),
            "role_page_url": url,
            "interpretation": "Company-owned role card: the company's own site names the role and how to apply.",
        },
        "strategy": "company_site_role_card",
    }
    if published:
        observation["observed_at"] = published
        observation["metrics"]["published"] = published
        observation["metrics"]["date_precision"] = date_precision
    return observation


def observations(profile: dict, fetched: dict[str, bytes], *, max_cards: int = MAX_CARDS) -> list[dict]:
    """The role cards of one company, bounded and ordered."""
    if not publishable(profile):
        return []
    rows: list[dict] = []
    for url in sorted(fetched):
        raw = fetched[url]
        if not isinstance(raw, (bytes, bytearray)):
            continue
        card = role_card(profile, url, bytes(raw).decode("utf-8", "replace"), bytes(raw))
        if card:
            rows.append(card)
        if len(rows) >= max_cards:
            break
    return rows


def fetch(url: str, *, timeout: float = FETCH_TIMEOUT) -> tuple[bytes | None, str]:
    """Fetch a public page. Returns (body, note)."""
    try:
        assert_public_url(url)
    except ValueError as exc:
        return None, f"blocked:{str(exc)[:60]}"
    try:
        if not _robots_allowed(url, timeout):
            return None, "robots"
    except Exception:
        return None, "robots_error"
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        with SAFE_OPENER.open(request, timeout=timeout) as response:
            raw = response.read(FETCH_MAX_BYTES)
            content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            return None, f"content_type:{content_type[:30]}"
        return raw, "ok"
    except Exception as exc:
        return None, type(exc).__name__


def collect_company(profile: dict, sitemap_rows: list[dict], *, max_role_links: int = MAX_ROLE_LINKS) -> tuple[dict[str, bytes], dict[str, str]]:
    """Fetch the careers pages and the role pages of one company."""
    fetched: dict[str, bytes] = {}
    hints: dict[str, str] = {}
    domain = site_domain(profile)
    candidates = careers_page_urls(profile)
    for row in sitemap_rows:
        url = str((row.get("metrics") or {}).get("page_url") or "")
        if url.startswith(("http://", "https://")) and VACANCY_PATH.search(urllib.parse.urlparse(url).path):
            candidates.append(url)
    role_candidates: list[str] = []
    for url in candidates[: MAX_ROLE_LINKS + len(careers_page_urls(profile))]:
        if url in fetched:
            continue
        raw, note = fetch(url)
        if raw is None:
            continue
        fetched[url] = raw
        html = raw.decode("utf-8", "replace")
        soup = BeautifulSoup(html, "lxml")
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = urllib.parse.urljoin(url, href).split("#")[0]
            label = anchor.get_text(" ", strip=True)
            if absolute not in hints:
                hints[absolute] = label
        for link in role_links(html, url, domain, limit=max_role_links):
            if link not in role_candidates:
                role_candidates.append(link)
    for url in role_candidates:
        if url in fetched:
            continue
        raw, _note = fetch(url)
        if raw is not None:
            fetched[url] = raw
    return fetched, hints


def main() -> None:
    parser = argparse.ArgumentParser(description="Role-card connector for verified company sites.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--sitemap", default="")
    parser.add_argument("--max-role-links", type=int, default=MAX_ROLE_LINKS)
    parser.add_argument("--max-cards", type=int, default=MAX_CARDS)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    profiles = read_jsonl(Path(args.profiles))
    sitemap_by_org: dict[str, list[dict]] = {}
    if args.sitemap and Path(args.sitemap).exists():
        for row in read_jsonl(Path(args.sitemap)):
            sitemap_by_org.setdefault(str(row.get("organisation_number") or ""), []).append(row)

    candidates = [profile for profile in profiles if publishable(profile)]
    observations_out: list[dict] = []
    pages_fetched = 0

    def work(profile: dict) -> tuple[list[dict], int]:
        fetched, hints = collect_company(
            profile,
            sitemap_by_org.get(str(profile.get("organisation_number") or ""), []),
            max_role_links=args.max_role_links,
        )
        rows: list[dict] = []
        for url in sorted(fetched):
            raw = fetched[url]
            card = role_card(
                profile,
                url,
                raw.decode("utf-8", "replace"),
                raw,
                hint=hints.get(url),
            )
            if card:
                rows.append(card)
            if len(rows) >= args.max_cards:
                break
        return rows, len(fetched)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rows, fetched_count in pool.map(work, candidates):
            observations_out.extend(rows)
            pages_fetched += fetched_count

    observations_out.sort(key=lambda row: (row["organisation_number"], row["source_url"]))
    write_jsonl(Path(args.output), observations_out)
    report = {
        "connector": "company_site_role_cards_v1",
        "profiles": len(profiles),
        "publishable_profiles": len(candidates),
        "pages_fetched": pages_fetched,
        "role_cards": len(observations_out),
        "companies_with_a_role_card": len({row["organisation_number"] for row in observations_out}),
        "per_company_cap": args.max_cards,
        "claim_boundary": "A role card is a role title plus an apply action on the company's own identity-gated site. A careers page alone is never a role card.",
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
