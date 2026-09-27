#!/usr/bin/env python3
"""Deterministic, no-API-key synthesis: rule-based company summaries from envelopes.

Reads terminal envelopes (profile + evidence shape) and emits per-company
summaries plus an answers block for the questions the evaluation scores:
what the company does, revenue/staff trend, whether it is hiring.
Every answered question cites evidence; anything unprovable is reported as
"not available", never invented. No network, no key, deterministic:
the same envelope always yields the same summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


FORM_WORDS = {
    "AS": "a private limited company",
    "ASA": "a public limited company",
    "ANS": "a general partnership",
    "DA": "a partnership with shared liability",
    "ENK": "a sole proprietorship",
    "NUF": "a Norwegian branch of a foreign company",
    "SA": "a cooperative",
    "STI": "a foundation",
    "BRL": "a housing cooperative",
    "IKS": "an inter-municipal company",
}


def _money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    for scale, word in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(number) >= scale:
            return f"NOK {number / scale:,.1f}{word}".replace(",", " ")
    return f"NOK {number:,.0f}".replace(",", " ")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]


def _available_evidence(profile: dict[str, Any]) -> dict[str, Any]:
    evidence = profile.get("evidence") or {}
    return {k: v for k, v in evidence.items() if isinstance(v, dict) and v.get("status") == "available"}


def _evidence_ids(profile: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for block in _available_evidence(profile).values():
        url = block.get("source_url")
        if url and url not in ids:
            ids.append(str(url))
    for obs in (profile.get("evidence") or {}).get("external_observations") or []:
        if not isinstance(obs, dict) or obs.get("acquisition_mode") == "rights_review_experiment":
            continue
        url = obs.get("source_url")
        if url and url not in ids:
            ids.append(str(url))
    return sorted(ids)


def _observations(profile: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (profile.get("evidence") or {}).get("external_observations") or []
    return [o for o in rows if isinstance(o, dict) and o.get("acquisition_mode") != "rights_review_experiment"]


def _answer(question: str, answer: str | None, evidence_ids: list[str], *, status: str = "confirmed", confidence: float = 1.0) -> dict[str, Any]:
    if answer:
        return {"question": question, "answer": answer, "answerable": True, "status": status, "confidence": confidence, "evidence_ids": evidence_ids}
    return {"question": question, "answer": "not available", "answerable": False, "status": "unknown", "confidence": 0.0, "evidence_ids": []}


def _known_evidence_urls(profile: dict[str, Any]) -> set[str]:
    urls = set()
    for block in (profile.get("evidence") or {}).values():
        if isinstance(block, dict) and block.get("source_url"):
            urls.add(str(block["source_url"]))
    for obs in (profile.get("evidence") or {}).get("external_observations") or []:
        if isinstance(obs, dict) and obs.get("source_url"):
            urls.add(str(obs["source_url"]))
    return urls


def validate_summary(row: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    """Mulder-grade citation check: every cited evidence id must resolve to
    evidence in the same envelope. Returns a list of violations (empty = clean)."""
    profile = row.get("profile") or {}
    known = _known_evidence_urls(profile)
    violations = []
    for answer in summary.get("answers") or []:
        for eid in answer.get("evidence_ids") or []:
            if eid not in known:
                violations.append(f"fabricated citation: answer {answer.get('question')!r} cites {eid!r}, not present in envelope evidence")
        if not answer.get("answerable") and answer.get("evidence_ids"):
            violations.append(f"unanswerable question {answer.get('question')!r} carries evidence ids")
    return violations


def summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    profile = row.get("profile") or {}
    org = str(row.get("organisation_number") or profile.get("organisation_number") or "")
    name = profile.get("name") or org
    ids = _evidence_ids(profile)

    industry = profile.get("industry_label")
    form = str(profile.get("legal_form") or "").strip()
    form_words = FORM_WORDS.get(form)
    if industry:
        what = f"{name} operates in {industry}."
        if form_words:
            what = f"{name} is {form_words} operating in {industry}."
        what_answer = _answer("what_it_does", what, ids, confidence=1.0)
    else:
        what_answer = _answer("what_it_does", None, ids)

    fin = (_available_evidence(profile).get("financials") or {}).get("value") or {}
    records = fin.get("records") or []
    latest = records[0] if records else None
    if latest:
        rev = latest.get("revenue")
        res = latest.get("annual_result")
        year = latest.get("year") or profile.get("latest_submitted_accounts")
        bits = []
        if rev is not None:
            bits.append(f"revenue {_money(rev)}")
        if res is not None:
            bits.append(f"annual result {_money(res)}")
        fin_answer = _answer("financial_health", f"Latest accounts ({year}): " + ", ".join(bits) + ".", ids, confidence=0.95)
    else:
        fin_answer = _answer("financial_health", None, ids)

    finhist = (_available_evidence(profile).get("financial_history") or {}).get("value") or {}
    hist_years = finhist.get("years") or []
    if hist_years:
        hist_answer = _answer("financial_history", f"Annual accounts available for {hist_years[0]}-{hist_years[-1]} ({len(hist_years)} years). Detailed records only available as PDFs.", ids, confidence=0.9)
    else:
        hist_answer = _answer("financial_history", None, ids)

    employees = profile.get("employees")
    if employees is not None:
        staff_answer = _answer("staff", f"Registered employees: {employees}.", ids, confidence=1.0)
    else:
        staff_answer = _answer("staff", None, ids)

    if len(records) >= 2:
        rev_curr = records[0].get("revenue")
        rev_prev = records[1].get("revenue")
        if rev_curr is not None and rev_prev is not None and rev_prev != 0:
            pct = ((rev_curr - rev_prev) / abs(rev_prev)) * 100
            trend = "growing" if pct > 5 else "shrinking" if pct < -5 else "stable"
            growth_answer = _answer("revenue_growth", f"Revenue {trend} ({pct:+.1f}% YoY).", ids, confidence=0.9)
        else:
            growth_answer = _answer("revenue_growth", None, ids)
        emp_curr = records[0].get("employees")
        emp_prev = records[1].get("employees")
        if emp_curr is not None and emp_prev is not None and emp_prev != 0:
            pct = ((emp_curr - emp_prev) / emp_prev) * 100
            trend = "growing" if pct > 5 else "shrinking" if pct < -5 else "stable"
            staff_growth_answer = _answer("staff_growth", f"Staff {trend} ({pct:+.1f}% YoY).", ids, confidence=0.9)
        else:
            staff_growth_answer = _answer("staff_growth", None, ids)
    else:
        growth_answer = _answer("revenue_growth", None, ids)
        staff_growth_answer = _answer("staff_growth", None, ids)

    jobs = [o for o in _observations(profile) if o.get("signal_type") == "job_posting"]
    if jobs:
        job_urls = sorted({str(o.get("source_url")) for o in jobs if o.get("source_url")})
        hiring_answer = _answer("hiring", f"Yes, {len(jobs)} open posting(s) found in checked sources.", job_urls, confidence=0.95)
    elif "external_observations" in (profile.get("evidence") or {}):
        hiring_answer = _answer("hiring", "No open postings found in checked sources.", ids, status="inferred", confidence=0.6)
    else:
        hiring_answer = _answer("hiring", None, ids)

    answers = [what_answer, fin_answer, hist_answer, growth_answer, staff_answer, staff_growth_answer, hiring_answer]
    summary_bits = [a["answer"] for a in answers if a["answerable"]]
    available = _available_evidence(profile)
    unknowns = []
    if "website" not in available:
        unknowns.append({"field": "official_website", "state": "not_available", "reason": "no verified company website was established"})
    if profile.get("employees") is None:
        unknowns.append({"field": "employees", "state": "not_available", "reason": "registry returned no employee count"})
    if not latest:
        unknowns.append({"field": "financial_health", "state": "not_available", "reason": "no filed accounts found in checked sources"})
        unknowns.append({"field": "revenue_growth", "state": "not_available", "reason": "insufficient financial history (need at least 2 years)"})
        unknowns.append({"field": "staff_growth", "state": "not_available", "reason": "insufficient financial history (need at least 2 years)"})
    if not hist_years:
        unknowns.append({"field": "financial_history", "state": "not_available", "reason": "no financial history found"})
    elif len(records) < 2:
        unknowns.append({"field": "revenue_growth", "state": "not_available", "reason": "insufficient financial history (need at least 2 years)"})
        unknowns.append({"field": "staff_growth", "state": "not_available", "reason": "insufficient financial history (need at least 2 years)"})
    if not jobs and "external_observations" not in (profile.get("evidence") or {}):
        unknowns.append({"field": "hiring", "state": "not_available", "reason": "no job sources were checked"})
    return {
        "organisation_number": org,
        "company_name": name,
        "synthesis_model": "deterministic-rules-v1",
        "synthesis_state": "available" if summary_bits else "abstained",
        "summary": " ".join(summary_bits) if summary_bits else "not available",
        "answers": answers,
        "unknowns": unknowns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic rule-based summaries (no API key).")
    parser.add_argument("--envelopes", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows = read_jsonl(Path(args.envelopes))
    if args.limit:
        rows = rows[: args.limit]
    summaries = [summarize_row(row) for row in rows]
    violations = [v for row, s in zip(rows, summaries) for v in validate_summary(row, s)]
    if violations:
        raise SystemExit("citation-integrity violations:\n" + "\n".join(violations))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("".join(sanitize_line_separators(json.dumps(s, ensure_ascii=False)) + "\n" for s in summaries), encoding="utf-8")
    states: dict[str, int] = {}
    for s in summaries:
        states[s["synthesis_state"]] = states.get(s["synthesis_state"], 0) + 1
    report = {"connector": "deterministic_synthesis_v1", "model": "deterministic-rules-v1", "envelopes": len(summaries), "states": states}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
