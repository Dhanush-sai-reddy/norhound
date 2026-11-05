#!/usr/bin/env python3
"""Page-1 OCR connector: extracts dated facts from the BRREG annual-report cover.

The first page of every BRREG annual-report PDF ("GENERELL INFORMASJON")
contains these exact-entity, dated, keyless facts:

- approval date  (Dato for fastsettelse)
- auditor name   (Bekreftet av)
- accounting rules (Regler for små foretak)
- business address (Forretningsadresse)
- signing officer (Signer)
- organisation number (Organisasjonsnummer)

Each field is published as a separate observation with the OCR text retained
as evidence. OCR uses the Norwegian traineddata (`nor`) for correct names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
TESSDATA_PREFIX = "/tmp/opencode/tessdata"
OCR_DPI = 130

# Field extractors: (signal_type, metric_key, regex, value_transform)
# Regexes search the folded OCR text (lowercased, å/ø/æ → a/o/ae) but
# value_transform receives the ORIGINAL text match to preserve case.
FIELD_SPECS = [
    (
        "annual_report_approval_date",
        "approval_date",
        re.compile(r"(?i)dato\s+for\s+(?:fastsettelse|fastsattelse)(?:\s+av\s+\w+)?\s*[:\u3000]?\s*(\d{2}\.\d{2}\.\d{4})"),
        lambda m: m.group(1),
    ),
    (
        "annual_report_auditor",
        "auditor",
        re.compile(r"(?i)bekreftet\s+av\s*[:\u3000]?\s*([^\n]{2,80})"),
        lambda m: m.group(1).strip(),
    ),
    (
        "annual_report_accounting_rules",
        "accounting_rules",
        re.compile(r"(?i)regler\s+for\s+sm.{1,3}\s+foretak.{0,40}?[:\u3000]?\s*([^\n]{2,80})"),
        lambda m: m.group(1).strip(),
    ),
    (
        "annual_report_business_address",
        "business_address",
        re.compile(r"(?i)forretningsadresse\s*[:\u3000]?\s*([^\n]{3,120})"),
        lambda m: m.group(1).strip(),
    ),
    (
        "annual_report_signing_officer",
        "signing_officer",
        re.compile(r"(?i)(?<!signer)(?<!signert)\bsigner[æa]?\s*[:\u3000]?\s*([^\n]{2,80})"),
        lambda m: m.group(1).strip(),
    ),
    (
        "annual_report_org_number",
        "org_number",
        re.compile(r"(?i)organisasjonsnummer\s*[:\u3000]?\s*(\d{3}\s?\d{3}\s?\d{3})"),
        lambda m: re.sub(r"\s+", "", m.group(1)),
    ),
]


def _fold(text: str) -> str:
    """Lowercase and transliterate Norwegian letters for robust matching."""
    return text.lower().replace("ø", "o").replace("å", "a").replace("æ", "ae")


def _ocr_page1(pdf_path: Path, *, fixture_text: str | None = None) -> str:
    """OCR page 1 of a PDF, or return fixture text if provided."""
    if fixture_text is not None:
        return fixture_text

    env = dict(os.environ, TESSDATA_PREFIX=TESSDATA_PREFIX)
    with tempfile.TemporaryDirectory(prefix="ar-page1-") as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(
            ["pdftoppm", "-f", "1", "-l", "1", "-jpeg", "-r", str(OCR_DPI), str(pdf_path), str(prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        images = sorted(Path(tmp).glob("page-*.jpg"))
        if not images:
            return ""
        done = subprocess.run(
            ["tesseract", str(images[0]), "stdout", "-l", "nor", "--psm", "6"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        return done.stdout


def extract_page1_facts(profile: dict, *, pdf_path: Path, fixture_text: str | None = None) -> list[dict]:
    """Extract the six cover facts from page-1 OCR text."""
    org = str(profile.get("organisation_number") or "")
    name = str(profile.get("name") or "")
    text = _ocr_page1(pdf_path, fixture_text=fixture_text)
    folded = _fold(text)

    # Verify the org number appears in the OCR text (exact-entity gate)
    if org and org not in re.sub(r"\D", "", folded):
        return []

    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    content_sha256 = hashlib.sha256(text.encode()).hexdigest()

    observations: list[dict] = []
    for signal_type, metric_key, pattern, transform in FIELD_SPECS:
        m = pattern.search(folded)
        if not m:
            continue
        # Map the folded match position back to original text for case-preserving value
        orig_start = m.start()
        orig_end = m.end()
        # The folded text has same length as original (only char substitutions)
        orig_match = text[orig_start:orig_end]
        # Re-run pattern on original substring to get groups
        orig_m = re.search(pattern.pattern, orig_match, pattern.flags)
        if not orig_m:
            continue
        value = transform(orig_m)
        if not value:
            continue

        # Build a concise evidence span from the matched line (original text)
        line_start = folded.rfind("\n", 0, m.start()) + 1
        line_end = folded.find("\n", m.end())
        if line_end < 0:
            line_end = len(folded)
        evidence_span = text[line_start:line_end].strip()[:400]

        obs_id = f"ar-page1-{org}-{signal_type}-{content_sha256[:16]}"
        observation = {
            "id": obs_id,
            "organisation_number": org,
            "platform": "brreg",
            "signal_type": signal_type,
            "source_url": pdf_path.as_uri() if pdf_path.is_file() else str(pdf_path),
            "retrieved_at": retrieved_at,
            "content_sha256": content_sha256,
            "exact_entity": True,
            "identity_proof": [
                {"type": "official_report_url_organisation_number", "value": org},
                {"type": "organisation_number_in_pdf", "value": org},
            ],
            "acquisition_mode": "official_api",
            "rights_status": "approved",
            "source_class": "official_annual_account_copy",
            "evidence_span": evidence_span,
            "metrics": {
                metric_key: value,
                "ocr_text_sha256": content_sha256,
                "ocr_chars": len(text),
            },
            "strategy": "annual_report_page1_ocr",
        }
        observations.append(observation)

    return observations


def _download_pdf(url: str, cache_dir: Path, org: str) -> Path | None:
    """Download PDF to cache, or return existing cached PDF from workforce cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    # First check the workforce PDF cache (main checkout)
    workforce_cache = Path("/home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/data/workforce-pdf-cache")
    expected_name = f"{org}-2025.pdf"
    workforce_pdf = workforce_cache / expected_name
    if workforce_pdf.exists():
        # Copy to local cache
        local_cache = cache_dir / expected_name
        if not local_cache.exists():
            import shutil
            shutil.copy2(workforce_pdf, local_cache)
        return local_cache

    # Fallback: download from URL
    fname = hashlib.sha256(url.encode()).hexdigest()[:16] + ".pdf"
    cache_path = cache_dir / fname
    if cache_path.exists():
        return cache_path

    import urllib.request
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/pdf"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read(30_000_000)
        if len(raw) > 30_000_000 or not raw.startswith(b"%PDF"):
            return None
        cache_path.write_bytes(raw)
        return cache_path
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract page-1 facts from BRREG annual-report PDFs via OCR.")
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--organisations", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--fixture-ocr-text", help="Path to fixture OCR text for testing (skips OCR)")
    args = parser.parse_args()

    wanted = [
        line.strip()
        for line in Path(args.organisations).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        wanted = wanted[: args.limit]

    profiles = {
        str(row["organisation_number"]): row
        for row in (
            json.loads(line)
            for line in Path(args.profiles).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if str(row["organisation_number"]) in set(wanted)
    }

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    all_observations: list[dict] = []
    all_statuses: list[dict] = []

    fixture_text = None
    if args.fixture_ocr_text:
        fixture_text = Path(args.fixture_ocr_text).read_text(encoding="utf-8")

    for org in wanted:
        profile = profiles.get(org)
        if not profile:
            all_statuses.append({"organisation_number": org, "status": "missing_profile"})
            continue

        pdfs = (((profile.get("evidence") or {}).get("financial_history") or {}).get("value") or {}).get("pdfs") or []
        if not pdfs:
            all_statuses.append({"organisation_number": org, "status": "no_pdf_url"})
            continue

        latest = pdfs[0]  # already sorted newest first by upstream
        pdf_url = latest.get("url")
        if not pdf_url:
            all_statuses.append({"organisation_number": org, "status": "no_pdf_url"})
            continue

        pdf_path = _download_pdf(pdf_url, cache_dir, org)
        if not pdf_path:
            all_statuses.append({"organisation_number": org, "status": "pdf_download_failed"})
            continue

        try:
            observations = extract_page1_facts(profile, pdf_path=pdf_path, fixture_text=fixture_text)
            all_observations.extend(observations)
            all_statuses.append({
                "organisation_number": org,
                "status": "accepted" if observations else "no_facts_extracted",
                "facts_extracted": len(observations),
            })
        except Exception as exc:
            all_statuses.append({
                "organisation_number": org,
                "status": "error",
                "error": f"{type(exc).__name__}: {str(exc)[:180]}",
            })

    # Write output
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in all_observations),
        encoding="utf-8",
    )

    # Write report
    report = {
        "connector": "annual_report_page1_ocr_v1",
        "companies_processed": len(wanted),
        "companies_with_facts": sum(1 for s in all_statuses if s.get("facts_extracted", 0) > 0),
        "total_observations": len(all_observations),
        "errors": sum(1 for s in all_statuses if s.get("status") == "error"),
        "claim_boundary": (
            "Page-1 OCR of official BRREG annual-report PDFs. Each fact (approval date, auditor, "
            "accounting rules, business address, signing officer, org number) is published as a "
            "separate observation with the OCR text hashed and retained."
        ),
        "company_results": all_statuses,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "company_results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()