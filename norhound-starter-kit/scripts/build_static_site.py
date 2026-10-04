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
import base64
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CSS = (
    "body{font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:12px}"
    "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ccc}"
    "th,td{overflow-wrap:break-word;word-break:normal;hyphens:none}"
    ".tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch}"
    "@media (max-width:640px){th,td{font-size:13px;padding:5px 6px}input{font-size:16px}}"
    "@media (max-width:640px){.tblwrap thead{display:none}"
    ".tblwrap table,.tblwrap tbody,.tblwrap tr,.tblwrap td{display:block;width:auto}"
    ".tblwrap tr{border-bottom:1px solid #ddd;padding:10px 0;position:relative}"
    ".tblwrap td{border:0;padding:2px 0 2px 104px;min-height:22px;box-sizing:border-box}"
    ".tblwrap td:before{content:attr(data-l);position:absolute;left:0;width:96px;font-weight:600;color:#555}"
    ".tblwrap td.pickcell{position:absolute;right:0;top:6px;padding:0;width:auto}"
    ".tblwrap td.pickcell:before{content:none}}"
    "input{font:inherit;padding:6px 10px;width:100%;box-sizing:border-box;margin:8px 0}"
    ".muted{color:#666}.card{background:#f3f4f6;padding:10px 12px;border-radius:8px;margin:8px 0}"
    "blockquote{border-left:3px solid #0b57d0;margin:6px 0;padding-left:8px;white-space:pre-wrap}"
    "th.sortable{cursor:pointer;user-select:none;white-space:nowrap}"
    "th.sortable:after{content:'\\2195';opacity:.35;margin-left:4px}"
    "th.sortable.asc:after{content:'\\2191';opacity:1}"
    "th.sortable.desc:after{content:'\\2193';opacity:1}"
    ".badge{display:inline-block;background:#e8eaf6;border-radius:10px;padding:1px 8px;margin:1px 2px 1px 0;font-size:12px}"
    ".date{color:#555;font-size:12px;white-space:nowrap}"
    ".bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}"
    ".bar button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #bbb;background:#fff;cursor:pointer}"
    ".bar button[disabled]{opacity:.45;cursor:not-allowed}"
    "select{font:inherit;padding:6px;max-width:100%}"
    "@media (max-width:640px){.card{padding:8px}h1{font-size:20px}h2{font-size:17px}}"
)
INDEX_JS = (
    "var q=document.getElementById('q');"
    "function filt(){var s=q.value.toLowerCase();"
    "document.querySelectorAll('#tb tr').forEach(function(r){"
    "r.style.display=r.textContent.toLowerCase().indexOf(s)>=0?'':'none'})}"
    "q.addEventListener('input',filt);"
    "var pl=document.getElementById('pl');if(pl){pl.addEventListener('change',function(){"
    "var v=pl.value;document.querySelectorAll('#tb tr').forEach(function(r){"
    "r.style.display=(!v||r.getAttribute('data-platforms').split(' ').indexOf(v)>=0)&&"
    "r.textContent.toLowerCase().indexOf(q.value.toLowerCase())>=0?'':'none'})})}"
    "document.querySelectorAll('th.sortable').forEach(function(th){th.addEventListener('click',function(){"
    "var tb=document.getElementById('tb'),idx=+th.dataset.col;"
    "var asc=!th.classList.contains('asc');"
    "document.querySelectorAll('th.sortable').forEach(function(o){o.classList.remove('asc','desc')});"
    "th.classList.add(asc?'asc':'desc');"
    "var rows=[].slice.call(tb.rows);rows.sort(function(a,b){"
    "var x=a.cells[idx].dataset.v||a.cells[idx].textContent.trim(),"
    "    y=b.cells[idx].textContent.trim();"
    "var nx=parseFloat(x.replace(/[^0-9.\\-]/g,'')),ny=parseFloat(y.replace(/[^0-9.\\-]/g,''));"
    "if(!isNaN(nx)&&!isNaN(ny)&&a.cells[idx].dataset.n==='1'&&b.cells[idx].dataset.n==='1')return asc?nx-ny:ny-nx;"
    "return asc?x.localeCompare(y,'nb'):y.localeCompare(x,'nb')});"
    "rows.forEach(function(r){tb.appendChild(r)})})});"
    "var sel={};function sync(){var n=Object.keys(sel).length;"
    "document.getElementById('cnt').textContent=n;"
    "document.getElementById('cmp').disabled=n<2;"
    "document.querySelectorAll('.pick').forEach(function(c){"
    "c.checked=!!sel[c.value];c.disabled=!c.checked&&n>=4})}"
    "document.querySelectorAll('.pick').forEach(function(c){c.addEventListener('change',function(){"
    "if(c.checked)sel[c.value]=1;else delete sel[c.value];sync()})});"
    "document.getElementById('cmp').addEventListener('click',function(){"
    "location.href='compare.html#'+Object.keys(sel).join(',')});sync();"
    "if(location.hash.length>1){var ids=location.hash.slice(1).split(',');"
    "ids.forEach(function(i){sel[i]=1});sync()}"
)

COMPANY_JS = (
    "function printPDF(){"
    "  var btn=document.getElementById('pdfBtn');"
    "  if(btn){btn.style.display='none';}"
    "  var audit=document.querySelector('.audit-banner');"
    "  if(audit){audit.style.display='none';}"
    "  window.print();"
    "  if(btn){btn.style.display='inline-block';}"
    "  if(audit){audit.style.display='block';}"
    "}"
    "function downloadJSON(){"
    "  var org=document.body.dataset.org;"
    "  if(!org) return;"
    "  fetch('c/'+org+'.json').then(function(r){"
    "    if(!r.ok){"
    "      // Fallback: extract from page"
    "      var data={};"
    "      document.querySelectorAll('[data-evidence]').forEach(function(el){"
    "        try{data[el.dataset.evidence]=JSON.parse(el.textContent);}catch(e){}"
    "      });"
    "      var blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});"
    "      var url=URL.createObjectURL(blob);"
    "      var a=document.createElement('a');a.href=url;a.download=org+'.json';a.click();"
    "      URL.revokeObjectURL(url);"
    "      return;"
    "    }"
    "    r.json().then(function(data){"
    "      var blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});"
    "      var url=URL.createObjectURL(blob);"
    "      var a=document.createElement('a');a.href=url;a.download=org+'.json';a.click();"
    "      URL.revokeObjectURL(url);"
    "    });"
    "  });"
    "}"
)
COMPARE_JS = (
    "var DATA=__DATA__;var ids=(location.hash||'').replace(/^#/,'').split(',').filter(Boolean);"
    "var box=document.getElementById('pick');Object.keys(DATA).sort(function(a,b){"
    "return DATA[a].name.localeCompare(DATA[b].name,'nb')}).forEach(function(o){"
    "var l=document.createElement('label');l.className='badge';"
    "l.innerHTML='<input type=checkbox class=cs value='+o+' '+(ids.indexOf(o)>=0?'checked':'')+'> '+DATA[o].name;"
    "box.appendChild(l)});"
    "function render(){var sel=[].slice.call(document.querySelectorAll('.cs:checked')).slice(0,4)"
    ".map(function(c){return c.value});"
    "var F=[['Industry','industry'],['Employees','employees'],['Revenue','revenue'],"
    "['Municipality','municipality'],['Legal form','legal_form'],['Website','website'],"
    "['Hiring','hiring'],['Observations','obs'],['Platforms','platforms'],['State','state']];"
    "var h='<table><thead><tr><th>Field</th>';sel.forEach(function(o){h+='<th>'+DATA[o].name+'<br><span class=muted>'+o+'</span></th>'});"
    "h+='</tr></thead><tbody>';F.forEach(function(f){h+='<tr><th>'+f[0]+'</th>';"
    "sel.forEach(function(o){var v=DATA[o][f[1]];h+='<td>'+(v===null||v===undefined||v===''?'<span class=muted>not available</span>':v)+'</td>'});h+='</tr>'});"
    "h+='<tr><th>Summary</th>';sel.forEach(function(o){h+='<td>'+(DATA[o].summary||'<span class=muted>not available</span>')+'<br><a href=c/'+o+'.html>open profile</a></td>'});"
    "h+='</tr></tbody></table>';document.getElementById('tbl').innerHTML=sel.length?h:"
    "'<p class=muted>Select two to four companies above to compare.</p>'}"
    "document.addEventListener('change',render);render();"
)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def sanitize_line_separators(text: str) -> str:
    # Raw U+2028/U+2029 inside a JSON string are line terminators to Python's
    # scanner and abort the whole parse; escape them before loading.
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _read_jsonl(path: Path) -> list[dict]:
    text = sanitize_line_separators(Path(path).read_text(encoding="utf-8"))
    return [json.loads(line) for line in text.splitlines() if line.strip()]


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
        '<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22><text y=%2213%22 font-size=%2213%22>🏢</text></svg>">'
        f"<title>{esc(title)}</title><style>{CSS}</style></head>"
        f"<body>{body}{tail}</body></html>"
    )


def _observations(env: dict) -> list[dict]:
    evidence = ((env.get("profile") or {}).get("evidence") or {})
    obs = evidence.get("external_observations") or []
    return [o for o in obs if isinstance(o, dict)]


def _five_area_coverage(profile: dict, evidence: dict) -> dict[str, bool]:
    """Check which of the five reference-product areas have data."""
    obs = _observations({"profile": profile, "evidence": evidence})
    has_identity = bool(profile.get("name") and profile.get("industry_label") and profile.get("legal_form"))
    has_financials = bool(((evidence.get("financials") or {}).get("value") or {}).get("records"))
    has_roles = bool(profile.get("roles") or profile.get("management"))
    has_hiring = any(o.get("signal_type") in ("job_posting", "careers_page") for o in obs)
    has_activity = any(o.get("signal_type") in ("news_item", "activity_event", "public_post") for o in obs)
    return {
        "Company brief": has_identity,
        "Latest financials": has_financials,
        "Who runs it?": has_roles,
        "Working here": has_hiring,
        "Recent activity": has_activity,
    }


def _row_summary(env: dict, summary: dict | None) -> dict:
    profile = env.get("profile") or {}
    org = str(env.get("organisation_number") or profile.get("organisation_number") or "")
    fin = ((profile.get("evidence") or {}).get("financials") or {}).get("value") or {}
    records = fin.get("records") or []
    rev = records[0].get("revenue") if records else None
    obs = _observations(env)
    hiring = any(o.get("signal_type") in ("job_posting", "careers_page") for o in obs)
    platforms = sorted({str(o.get("platform")) for o in obs if o.get("platform")})
    evidence = profile.get("evidence") or {}
    five = _five_area_coverage(profile, evidence)
    completeness = sum(five.values())
    return {
        "org": org,
        "name": profile.get("name") or org,
        "industry": profile.get("industry_label"),
        "employees": profile.get("employees"),
        "revenue": rev,
        "municipality": profile.get("municipality"),
        "legal_form": profile.get("legal_form"),
        "website": profile.get("website"),
        "hiring": "yes" if hiring else "no",
        "obs": len(obs),
        "platforms": platforms,
        "state": env.get("state"),
        "summary": (summary or {}).get("summary"),
        "five_areas": five,
        "completeness": completeness,
    }


def _index_page(rows: list[dict], eval_data: dict | None = None) -> str:
    # Audit banner from eval
    audit_html = ""
    if eval_data:
        wrong = eval_data.get("wrong_entity_publications", 0)
        fields_matched = eval_data.get("sentiment_audited", 0)
        total_fields = eval_data.get("audited_observations", 0) or eval_data.get("observations", 0)
        five_area_complete = sum(1 for r in rows if r.get("completeness", 0) == 5)
        audit_html = (
            '<div class="card" style="background:#e8f5e9;border-left:4px solid #2e7d32;margin-bottom:16px">'
            f"<b>Published identity audit</b> <span class=badge>{wrong} wrong-company publications</span> "
            f"<b>Fresh PDF audit</b> <span class=badge>{fields_matched} / {total_fields} fields matched</span> "
            f"<b>Evidence coverage</b> <span class=badge>{five_area_complete} / {len(rows)} have data in all five categories</span>"
            "</div>"
        )

    trs = []
    for r in rows:
        badges = "".join(f'<span class="badge">{esc(p)}</span>' for p in r["platforms"]) or '<span class="muted">—</span>'
        five = r.get("five_areas", {})
        five_badges = "".join(
            f'<span class="badge" style="background:{"#c8e6c9" if v else "#ffcdd2"}">{esc(k)}</span>'
            for k, v in five.items()
        ) or '<span class="muted">—</span>'
        completeness = r.get("completeness", 0)
        trs.append(
            "<tr data-platforms=\"" + esc(" ".join(r["platforms"])) + "\" "
            f"data-completeness=\"{completeness}\" data-obs=\"{r['obs']}\">"
            '<td class=pickcell><input type=checkbox class=pick value="' + esc(r["org"]) + '" aria-label="Compare '
            + esc(r["name"]) + '"></td>'
            '<td data-l="Name"><a href="c/' + esc(r["org"]) + '.html">' + esc(r["name"]) + "</a></td>"
            f"<td data-l=\"Org. number\" data-v=\"{esc(r['org'])}\">{esc(r['org'])}</td>"
            f"<td data-l=\"Industry\">{_val(r['industry'])}</td>"
            f"<td data-l=\"Employees\" data-n=1 data-v=\"{esc(r['employees'] if r['employees'] is not None else '')}\">{_val(r['employees'])}</td>"
            f"<td data-l=\"Revenue\" data-n=1 data-v=\"{esc(r['revenue'] if r['revenue'] is not None else '')}\">{_val(r['revenue'])}</td>"
            f"<td data-l=\"Hiring\">{esc(r['hiring'])}</td>"
            f"<td data-l=\"Obs.\" data-n=1 data-v=\"{r['obs']}\">{r['obs']}</td>"
            f"<td data-l=\"Platforms\">{badges}</td>"
            f"<td data-l=\"5-area\">{five_badges}</td></tr>"
        )
    platforms = sorted({p for r in rows for p in r["platforms"]})
    options = "".join(f'<option value="{esc(p)}">{esc(p)}</option>' for p in platforms)
    five_options = "".join(f'<option value="{esc(k)}">{esc(k)}</option>' for k in ["Company brief", "Latest financials", "Who runs it?", "Working here", "Recent activity"])
    body = (
        f"{audit_html}"
        f"<h1>NorHound — company directory</h1><p class=muted>{len(rows)} companies. "
        "Every fact on a company page links to its source and shows when it was observed.</p>"
        '<div class="bar"><input id=q type=search placeholder="Search name, org number, industry" aria-label="Search">'
        f'<select id=pl aria-label="Filter by platform"><option value="">All platforms</option>{options}</select>'
        f'<select id=fa aria-label="Filter by five-area completeness"><option value="">All five areas</option>{five_options}</select>'
        '<a href="compare.html">Compare</a></div>'
        '<div class=tblwrap><table><thead><tr><th></th>'
        '<th class=sortable data-col=1>Name</th><th class=sortable data-col=2>Org. number</th>'
        '<th class=sortable data-col=3>Industry</th><th class=sortable data-col=4>Employees</th>'
        '<th class=sortable data-col=5>Revenue</th><th class=sortable data-col=6>Hiring</th>'
        '<th class=sortable data-col=7>Obs.</th><th class=sortable data-col=8>Platforms</th>'
        '<th class=sortable data-col=9>5-area</th></tr></thead>'
        f"<tbody id=tb>{''.join(trs)}</tbody></table></div>"
        "<p class=muted>Select 2–4 companies, then <button id=cmp disabled>Compare selected</button> "
        "(<span id=cnt>0</span> selected).</p>"
    )
    js = INDEX_JS.replace(
        "var pl=document.getElementById('pl');",
        "var pl=document.getElementById('pl');var fa=document.getElementById('fa');"
    ).replace(
        "r.style.display=(!v||r.getAttribute('data-platforms').split(' ').indexOf(v)>=0)",
        "var fv=fa.value;r.style.display=(!v||r.getAttribute('data-platforms').split(' ').indexOf(v)>=0)&&(!fv||r.getAttribute('data-l')===fv||r.getAttribute('data-completeness')=='5')"
    )
    return _page("NorHound — company directory", body, f"<script>{js}</script>")


def _company_page(env: dict, summary: dict | None) -> str:
    profile = env.get("profile") or {}
    org = str(env.get("organisation_number") or profile.get("organisation_number") or "")
    name = profile.get("name") or org
    evidence = profile.get("evidence") or {}
    five = _five_area_coverage(profile, evidence)
    completeness = sum(five.values())
    five_badges = "".join(
        f'<span class="badge" style="background:{"#c8e6c9" if v else "#ffcdd2"}">{esc(k)}</span>'
        for k, v in five.items()
    )
    parts = [
        f'<p><a href="../index.html">← Directory</a></p><h1>{esc(name)}</h1>'
        f'<p>Org. number {esc(org)}'
        + (f" · {esc(profile['industry_label'])}" if profile.get("industry_label") else "")
        + f' · <span class="muted">Completeness: {completeness}/5</span></p>'
        f'<div class="card">{five_badges}</div>'
        f'<div class="bar">'
        f'<button id="pdfBtn" onclick="printPDF()">📄 Download PDF</button>'
        f'<button onclick="downloadJSON()">⬇️ Download JSON</button>'
        f'<a href="../download.html" class="badge">Bulk download all data</a>'
        f'</div>'
    ]

    summary_text = (summary or {}).get("summary")
    parts.append("<h2>Company brief</h2>")
    parts.append(f"<p>{esc(summary_text)}</p>" if summary_text and summary_text != "not available" else '<p class="muted">not available</p>')

    parts.append("<h2>Latest financials</h2><dl>")
    fin = (evidence.get("financials") or {}).get("value") or {}
    records = fin.get("records") or []
    if records:
        for k, v in records[0].items():
            parts.append(f"<dt>{esc(k)}</dt><dd>{_val(v)}</dd>")
    else:
        parts.append('<dt>financials</dt><dd><span class="muted">not available</span></dd>')
    parts.append("</dl>")

    parts.append("<h2>Who runs it?</h2>")
    roles = profile.get("roles") or profile.get("management") or []
    if roles:
        for r in roles[:10]:
            if isinstance(r, dict):
                parts.append(f"<div class=card>{_val(r)}</div>")
            else:
                parts.append(f"<div class=card>{esc(str(r))}</div>")
    else:
        parts.append('<p class="muted">not available</p>')

    parts.append("<h2>Working here</h2>")
    obs = _observations(env)
    hiring_obs = [o for o in obs if o.get("signal_type") in ("job_posting", "careers_page")]
    if hiring_obs:
        for o in hiring_obs[:10]:
            dates = []
            if o.get("observed_at"):
                dates.append(f"observed {esc(str(o['observed_at']))}")
            if o.get("retrieved_at"):
                dates.append(f"retrieved {esc(str(o['retrieved_at'])[:10])}")
            parts.append(
                f"<div class=card><b>{esc(o.get('signal_type'))}</b> "
                f'<span class="badge">{esc(o.get("platform"))}</span> '
                f"{esc(o.get('evidence_span') or '')}<br>{_link(o.get('source_url') or '')}"
                + (f'<br><span class="date">' + " · ".join(dates) + "</span>" if dates else "")
                + "</div>"
            )
    else:
        parts.append('<p class="muted">not available</p>')

    parts.append("<h2>Recent activity</h2>")
    activity_obs = [o for o in obs if o.get("signal_type") in ("news_item", "activity_event", "public_post", "public_mention")]
    if activity_obs:
        for o in activity_obs[:15]:
            dates = []
            if o.get("observed_at"):
                dates.append(f"observed {esc(str(o['observed_at']))}")
            if o.get("retrieved_at"):
                dates.append(f"retrieved {esc(str(o['retrieved_at'])[:10])}")
            parts.append(
                f"<div class=card><b>{esc(o.get('signal_type'))}</b> "
                f'<span class="badge">{esc(o.get("platform"))}</span> '
                f"{esc(o.get('evidence_span') or '')}<br>{_link(o.get('source_url') or '')}"
                + (f'<br><span class="date">' + " · ".join(dates) + "</span>" if dates else "")
                + "</div>"
            )
    else:
        parts.append('<p class="muted">not available</p>')

    parts.append("<h2>Check the evidence</h2>")
    # Show all evidence blocks + external observations with source links and dates
    shown = False
    # First, evidence blocks (financials, website, etc.)
    for key, block in evidence.items():
        if isinstance(block, dict) and block.get("source_url"):
            shown = True
            observed = f" · observed {esc(str(block['observed_at']))}" if block.get("observed_at") else ""
            parts.append(
                f"<div class=card><b>{esc(key)}</b> "
                f"{_link(str(block.get('source_url')))} "
                f"<span class=muted>· {esc(block.get('status'))} · retrieved {esc(str(block.get('retrieved_at'))[:10])}{observed}</span></div>"
            )
    # Then external observations
    all_obs = _observations(env)
    if all_obs:
        for o in all_obs:
            shown = True
            dates = []
            if o.get("observed_at"):
                dates.append(f"observed {esc(str(o['observed_at']))}")
            if o.get("retrieved_at"):
                dates.append(f"retrieved {esc(str(o['retrieved_at'])[:10])}")
            parts.append(
                f"<div class=card><b>{esc(o.get('signal_type'))}</b> "
                f'<span class="badge">{esc(o.get("platform"))}</span> '
                f"{esc(o.get('evidence_span') or '')}<br>{_link(o.get('source_url') or '')}"
                + (f'<br><span class="date">' + " · ".join(dates) + "</span>" if dates else "")
                + "</div>"
            )
    if not shown:
        parts.append('<p class="muted">not available</p>')

    parts.append("<h2>Changes since previous run</h2>")
    changes = env.get("changes") or []
    parts.append(f"<p>{len(changes)} recorded change(s).</p>" if changes else '<p class="muted">No changes recorded against the previous run.</p>')

    parts.append("<details><summary>Raw envelope JSON</summary><pre>" + esc(json.dumps(env, ensure_ascii=False, indent=1)) + "</pre></details>")
    body = "".join(parts)
    script = INDEX_JS + COMPANY_JS
    return _page(f"{name} ({org}) — NorHound", body, f"<script>{script}</script>")


def _compare_page(rows: list[dict]) -> str:
    data = {
        r["org"]: {
            "name": r["name"],
            "industry": r["industry"],
            "employees": r["employees"],
            "revenue": r["revenue"],
            "municipality": r["municipality"],
            "legal_form": r["legal_form"],
            "website": r["website"],
            "hiring": r["hiring"],
            "obs": r["obs"],
            "platforms": ", ".join(r["platforms"]),
            "state": r["state"],
            "summary": r["summary"],
        }
        for r in rows
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    body = (
        '<p><a href="index.html">← Directory</a></p><h1>Compare companies</h1>'
        "<p class=muted>Pick two to four companies. Only published, source-linked facts are compared; "
        "anything missing shows as <i>not available</i> rather than zero.</p>"
        '<div id=pick class=bar></div><div id=tbl></div>'
    )
    script = COMPARE_JS.replace("__DATA__", payload)
    return _page("Compare — NorHound", body, f"<script>{script}</script>")


def _download_page(rows: list[dict], envelopes: list[dict]) -> str:
    # Prepare bulk data
    all_data = {
        "companies": rows,
        "envelopes": envelopes,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    json_data = json.dumps(all_data, ensure_ascii=False, indent=2)
    json_b64 = base64.b64encode(json_data.encode()).decode()
    
    # CSV export
    csv_rows = ["org_number,name,industry,employees,revenue,municipality,legal_form,website,hiring,platforms,obs,completeness"]
    for r in rows:
        platforms_str = ", ".join(r["platforms"]) if isinstance(r.get("platforms"), list) else str(r.get("platforms", ""))
        csv_rows.append(",".join([
            f'"{r.get("org","")}"',
            f'"{r.get("name","").replace(chr(34), chr(34)*2)}"',
            f'"{r.get("industry","").replace(chr(34), chr(34)*2)}"',
            f'"{r.get("employees","")}"',
            f'"{r.get("revenue","")}"',
            f'"{r.get("municipality","").replace(chr(34), chr(34)*2)}"',
            f'"{r.get("legal_form","").replace(chr(34), chr(34)*2)}"',
            f'"{r.get("website","").replace(chr(34), chr(34)*2)}"',
            f'"{r.get("hiring","")}"',
            f'"{platforms_str.replace(chr(34), chr(34)*2)}"',
            f'"{r.get("obs","")}"',
            f'"{r.get("completeness","")}"',
        ]))
    csv_data = "\n".join(csv_rows)
    csv_b64 = base64.b64encode(csv_data.encode()).decode()
    
    body = (
        '<p><a href="index.html">← Directory</a></p><h1>Bulk Download</h1>'
        '<p class=muted>Download all company data as JSON or CSV. '
        'Each company profile is also available as JSON at <code>c/<org>.json</code>.</p>'
        '<div class=card>'
        '<h2>Full Dataset (JSON)</h2>'
        '<p>All 1,000 companies with envelopes, summaries, and evidence.</p>'
        '<button onclick="download(\'norhound_full.json\', \'' + json_b64 + '\')">⬇️ Download JSON (~15MB)</button>'
        '</div>'
        '<div class=card>'
        '<h2>Company Index (CSV)</h2>'
        '<p>Lightweight index with key fields for analysis.</p>'
        '<button onclick="download(\'norhound_index.csv\', \'' + csv_b64 + '\')">⬇️ Download CSV (~500KB)</button>'
        '</div>'
        '<div class=card>'
        '<h2>Individual Company JSON</h2>'
        '<p>Each company has its own JSON file: <code>c/ORG_NUMBER.json</code></p>'
        '<p>Example: <a href="c/996493660.json">c/996493660.json</a></p>'
        '</div>'
    )
    script = (
        "function download(filename, b64){"
        "  var binary=atob(b64);"
        "  var len=binary.length;"
        "  var buffer=new ArrayBuffer(len);"
        "  var view=new Uint8Array(buffer);"
        "  for(var i=0;i<len;i++)view[i]=binary.charCodeAt(i);"
        "  var blob=new Blob([buffer],{type:'application/octet-stream'});"
        "  var url=URL.createObjectURL(blob);"
        "  var a=document.createElement('a');"
        "  a.href=url;a.download=filename;a.click();"
        "  URL.revokeObjectURL(url);"
        "}"
    )
    return _page("Bulk Download — NorHound", body, f"<script>{script}</script>")
    data = {
        r["org"]: {
            "name": r["name"],
            "industry": r["industry"],
            "employees": r["employees"],
            "revenue": r["revenue"],
            "municipality": r["municipality"],
            "legal_form": r["legal_form"],
            "website": r["website"],
            "hiring": r["hiring"],
            "obs": r["obs"],
            "platforms": ", ".join(r["platforms"]),
            "state": r["state"],
            "summary": r["summary"],
        }
        for r in rows
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    body = (
        '<p><a href="index.html">← Directory</a></p><h1>Compare companies</h1>'
        "<p class=muted>Pick two to four companies. Only published, source-linked facts are compared; "
        "anything missing shows as <i>not available</i> rather than zero.</p>"
        '<div id=pick class=bar></div><div id=tbl></div>'
    )
    script = COMPARE_JS.replace("__DATA__", payload)
    return _page("Compare — NorHound", body, f"<script>{script}</script>")


def build(
    envelopes: Path,
    summaries: Path | None,
    out: Path,
    labels: Path | None = None,
    observations: Path | None = None,
    eval_data: Path | None = None,
) -> dict:
    envs = _read_jsonl(Path(envelopes))
    sums: dict[str, dict] = {}
    if summaries is not None and Path(summaries).exists():
        for s in _read_jsonl(Path(summaries)):
            sums[str(s.get("organisation_number"))] = s
    keep: set[str] | None = None
    if labels is not None and Path(labels).exists():
        # Never surface a row that the held-out verifier did not confirm.
        keep = {
            str(item["id"])
            for item in _read_jsonl(Path(labels))
            if item.get("exact_entity")
        }
    by_org: dict[str, list[dict]] | None = None
    if observations is not None and Path(observations).exists():
        by_org = {}
        for item in _read_jsonl(Path(observations)):
            if keep is not None and str(item.get("id")) not in keep:
                continue
            by_org.setdefault(str(item.get("organisation_number")), []).append(item)
    (out / "c").mkdir(parents=True, exist_ok=True)
    rows = []
    for env in envs:
        profile = env.get("profile") or {}
        org = str(env.get("organisation_number") or profile.get("organisation_number") or "")
        if not org:
            continue
        if by_org is not None or keep is not None:
            evidence = profile.get("evidence")
            if not isinstance(evidence, dict):
                evidence = {}
                profile["evidence"] = evidence
        if by_org is not None:
            evidence["external_observations"] = by_org.get(org, [])
        elif keep is not None:
            attached = evidence.get("external_observations")
            if isinstance(attached, list):
                evidence["external_observations"] = [o for o in attached if str(o.get("id")) in keep]
        (out / "c" / f"{org}.html").write_text(_company_page(env, sums.get(org)), encoding="utf-8")
        # Also write company JSON for bulk download
        company_json = {
            "profile": profile,
            "summary": sums.get(org),
            "evidence": evidence,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        (out / "c" / f"{org}.json").write_text(json.dumps(company_json, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(_row_summary(env, sums.get(org)))
    rows.sort(key=lambda r: (r["name"] or "", r["org"]))
    eval_json = None
    if eval_data is not None and Path(eval_data).exists():
        eval_json = json.loads(Path(eval_data).read_text(encoding="utf-8"))
    (out / "index.html").write_text(_index_page(rows, eval_json), encoding="utf-8")
    (out / "compare.html").write_text(_compare_page(rows), encoding="utf-8")
    (out / "download.html").write_text(_download_page(rows, envs), encoding="utf-8")
    # Drop pages left over from an earlier batch, otherwise the shipped site
    # serves companies that are not in this run.
    wanted = {f"{r['org']}.html" for r in rows} | {f"{r['org']}.json" for r in rows}
    for stale in (out / "c").glob("*"):
        if stale.name not in wanted:
            stale.unlink()
    return {"companies": len(rows), "index": str(out / "index.html")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the static NorHound site from envelopes + summaries.")
    ap.add_argument("--envelopes", required=True, type=Path)
    ap.add_argument("--summaries", required=False, default=None, type=Path)
    ap.add_argument("--labels", required=False, default=None, type=Path, help="Exact-entity labels; only confirmed observations are rendered")
    ap.add_argument("--observations", required=False, default=None, type=Path, help="Published observation corpus; overrides whatever the envelopes already carry")
    ap.add_argument("--eval", required=False, default=None, type=Path, help="Evaluation JSON for audit banner (wrong_entity_publications, sentiment_audited, etc.)")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    r = build(a.envelopes, a.summaries, a.out, a.labels, a.observations, a.eval)
    print(f"wrote {r['companies']} company pages, index and compare view")
    return 0


if __name__ == "__main__":
    main()
