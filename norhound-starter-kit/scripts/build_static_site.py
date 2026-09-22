#!/usr/bin/env python3
"""Render terminal envelopes + summaries sidecar into a static searchable site.

    python3 scripts/build_static_site.py --envelopes out/envelopes.jsonl \
        --summaries out/summaries.jsonl --out site/

Writes site/index.html (searchable/sortable company directory) and
site/c/<org>.html (one page per company: summary, answers with evidence
links, facts, observations, changes, errors, raw JSON). Stdlib only,
no network, no CDN — opens from file://. All HTML is escaped; missing
facts render as "not available", never blank.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

CSS = (
    "body{font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:12px}"
    "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ccc}"
    "input{font:inherit;padding:6px 10px;width:100%;box-sizing:border-box;margin:8px 0}"
    ".muted{color:#666}.card{background:#f3f4f6;padding:10px 12px;border-radius:8px;margin:8px 0}"
    "blockquote{border-left:3px solid #0b57d0;margin:6px 0;padding-left:8px;white-space:pre-wrap}"
)
INDEX_JS = (
    "var q=document.getElementById('q');q.addEventListener('input',function(){"
    "var s=q.value.toLowerCase();document.querySelectorAll('#tb tr').forEach(function(r){"
    "r.style.display=r.textContent.toLowerCase().indexOf(s)>=0?'':'none'})});"
)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _link(url: str) -> str:
    u = esc(url)
    return f'<a href="{u}" rel="noopener">{u}</a>'


def _val(value: Any) -> str:
    if value is None or value == "":
        return '<span class="muted">not available</span>'
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:,}".replace(",", " ")
    if isinstance(value, list):
        return "<br>".join(_val(v) for v in value) if value else '<span class="muted">not available</span>'
    if isinstance(value, dict):
        parts = [f"{esc(k)}: {_val(v)}" for k, v in value.items() if v not in (None, "", [])]
        return "; ".join(parts) if parts else '<span class="muted">not available</span>'
    s = str(value)
    return _link(s) if s.startswith(("http://", "https://")) else esc(s)


def _page(title: str, body: str, tail: str = "") -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title><style>{CSS}</style></head>"
        f"<body>{body}{tail}</body></html>"
    )


def _row_summary(env: dict, summary: dict | None) -> dict:
    profile = env.get("profile") or {}
    org = str(env.get("organisation_number") or profile.get("organisation_number") or "")
    fin = ((profile.get("evidence") or {}).get("financials") or {}).get("value") or {}
    records = fin.get("records") or []
    rev = records[0].get("revenue") if records else None
    obs = (profile.get("evidence") or {}).get("external_observations") or []
    hiring = any(isinstance(o, dict) and o.get("signal_type") == "job_posting" for o in obs)
    return {
        "org": org,
        "name": profile.get("name") or org,
        "industry": profile.get("industry_label"),
        "employees": profile.get("employees"),
        "revenue": rev,
        "hiring": hiring,
        "state": env.get("state"),
        "summary": (summary or {}).get("summary"),
    }


def _index_page(rows: list[dict]) -> str:
    trs = []
    for r in rows:
        trs.append(
            "<tr><td><a href=\"c/" + esc(r["org"]) + ".html\">" + esc(r["name"]) + "</a></td>"
            f"<td>{esc(r['org'])}</td><td>{_val(r['industry'])}</td><td>{_val(r['employees'])}</td>"
            f"<td>{_val(r['revenue'])}</td><td>{'yes' if r['hiring'] else '—'}</td></tr>"
        )
    body = (
        f"<h1>NorHound — company directory</h1><p class=muted>{len(rows)} companies. "
        "Every fact on a company page links to its source.</p>"
        '<input id=q type=search placeholder="Search name, org number, industry" aria-label="Search">'
        "<table><thead><tr><th>Name</th><th>Org. number</th><th>Industry</th>"
        "<th>Employees</th><th>Revenue</th><th>Hiring</th></tr></thead>"
        f"<tbody id=tb>{''.join(trs)}</tbody></table>"
    )
    return _page("NorHound — company directory", body, f"<script>{INDEX_JS}</script>")


def _company_page(env: dict, summary: dict | None) -> str:
    profile = env.get("profile") or {}
    org = str(env.get("organisation_number") or profile.get("organisation_number") or "")
    name = profile.get("name") or org
    evidence = profile.get("evidence") or {}
    parts = [f'<p><a href="../index.html">← Directory</a></p><h1>{esc(name)}</h1><p>Org. number {esc(org)}']
    if profile.get("industry_label"):
        parts.append(f" · {esc(profile['industry_label'])}")
    parts.append("</p>")

    summary_text = (summary or {}).get("summary")
    parts.append("<h2>Summary</h2>")
    parts.append(f"<p>{esc(summary_text)}</p>" if summary_text and summary_text != "not available" else '<p class="muted">not available</p>')

    parts.append("<h2>Questions the evidence answers</h2>")
    answers = (summary or {}).get("answers") or []
    if answers:
        items = []
        for a in answers:
            links = " ".join(_link(u) for u in (a.get("evidence_ids") or []))
            items.append(f"<div class=card><b>{esc(a.get('question'))}</b>: {_val(a.get('answer'))}<br>{links}</div>")
        parts.append("".join(items))
    else:
        parts.append('<p class="muted">not available</p>')

    parts.append("<h2>Facts</h2><dl>")
    for key in ("industry_label", "employees", "latest_submitted_accounts", "municipality", "legal_form", "website"):
        parts.append(f"<dt>{esc(key)}</dt><dd>{_val(profile.get(key))}</dd>")
    fin = (evidence.get("financials") or {}).get("value") or {}
    parts.append(f"<dt>latest_accounts</dt><dd>{_val((fin.get('records') or [{}])[0])}</dd>")
    parts.append("</dl>")

    parts.append("<h2>Observations</h2>")
    obs = evidence.get("external_observations") or []
    if obs:
        for o in obs:
            parts.append(
                f"<div class=card><b>{esc(o.get('signal_type'))}</b> ({esc(o.get('platform'))}): "
                f"{esc(o.get('evidence_span') or '')}<br>{_link(o.get('source_url') or '')}</div>"
            )
    else:
        parts.append('<p class="muted">not available</p>')

    parts.append("<h2>Evidence</h2>")
    blocks = [b for b in evidence.values() if isinstance(b, dict) and b.get("source_url")]
    if blocks:
        for b in blocks:
            parts.append(
                f"<div class=card>{_link(str(b.get('source_url')))} "
                f"<span class=muted>· {esc(b.get('status'))} · retrieved {esc(b.get('retrieved_at'))}</span></div>"
            )
    else:
        parts.append('<p class="muted">not available</p>')

    parts.append("<h2>Changes since previous run</h2>")
    changes = env.get("changes") or []
    parts.append(f"<p>{len(changes)} recorded change(s).</p>" if changes else '<p class="muted">No changes recorded against the previous run.</p>')

    parts.append("<details><summary>Raw envelope JSON</summary><pre>" + esc(json.dumps(env, ensure_ascii=False, indent=1)) + "</pre></details>")
    return _page(f"{name} ({org}) — NorHound", "".join(parts))


def build(envelopes: Path, summaries: Path | None, out: Path) -> dict:
    envs = [json.loads(line) for line in Path(envelopes).read_text(encoding="utf-8").splitlines() if line.strip()]
    sums: dict[str, dict] = {}
    if summaries is not None and Path(summaries).exists():
        for line in Path(summaries).read_text(encoding="utf-8").splitlines():
            if line.strip():
                s = json.loads(line)
                sums[str(s.get("organisation_number"))] = s
    (out / "c").mkdir(parents=True, exist_ok=True)
    rows = []
    for env in envs:
        profile = env.get("profile") or {}
        org = str(env.get("organisation_number") or profile.get("organisation_number") or "")
        if not org:
            continue
        (out / "c" / f"{org}.html").write_text(_company_page(env, sums.get(org)), encoding="utf-8")
        rows.append(_row_summary(env, sums.get(org)))
    rows.sort(key=lambda r: (r["name"] or "", r["org"]))
    (out / "index.html").write_text(_index_page(rows), encoding="utf-8")
    return {"companies": len(rows), "index": str(out / "index.html")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the static NorHound site from envelopes + summaries.")
    ap.add_argument("--envelopes", required=True, type=Path)
    ap.add_argument("--summaries", required=False, default=None, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    r = build(a.envelopes, a.summaries, a.out)
    print(f"wrote {r['companies']} company pages and {r['index']}")
    return 0


if __name__ == "__main__":
    main()
