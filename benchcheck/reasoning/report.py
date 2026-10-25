"""Troubleshooting report: Observed / Possible explanations / Next check.

Hypotheses are recomputed here from the numerical analysis (never taken from the
client), then linked to retrieved passages. Every explanation carries the
observed features that triggered it, its stated assumptions, and the cited
passages with their evidence level and condition match.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from .. import __version__
from .checks import metadata_checks, rank_checks
from .hypotheses import RULES, evaluate

LEVEL_RANK = {"full text": 0, "abstract": 1, "search snippet": 2}
APPLICABILITY_RANK = {"condition-matched": 0, "partially matched": 1, "conditions not stated": 2, "different conditions": 3}
MAX_PASSAGES_PER_HYPOTHESIS = 3

DISCLAIMER = (
    "BenchCheck reports measured features and literature passages. It does not assign peaks to mechanisms; every "
    "explanation is a hypothesis to test. Literature passages are verbatim excerpts of retrieved text, labeled by how "
    "much of the source was available (full text, abstract, or search snippet)."
)


def _link_evidence(hyp: dict, sources: list[dict]) -> dict:
    cands = []
    for src in sources:
        best = None
        for p in src.get("passages", []):
            if p.get("hypothesis_id") != hyp["id"]:
                continue
            key = (LEVEL_RANK.get(p.get("level"), 3), -p.get("score", 0))
            if best is None or key < best[0]:
                best = (key, p)
        if best:
            app = (src.get("applicability") or {}).get("level", "different conditions")
            cands.append(((APPLICABILITY_RANK.get(app, 3),) + best[0], src, best[1]))
    cands.sort(key=lambda c: c[0])
    cited = []
    for _, src, p in cands[:MAX_PASSAGES_PER_HYPOTHESIS]:
        app = src.get("applicability") or {}
        cited.append({
            "source_id": src.get("source_id"), "title": src.get("title"), "link": src.get("link"),
            "year": src.get("year"), "venue": src.get("venue"), "passage": p.get("text"), "level": p.get("level"),
            "location": p.get("location"), "matched_terms": p.get("matched_terms", []),
            "applicability": app.get("level"), "differences": app.get("differences", []),
            "not_stated": app.get("not_stated", []), "cached": src.get("cached", False),
        })
    if any(c["applicability"] == "condition-matched" for c in cited):
        status = "condition-matched"
    elif cited:
        status = "related"
    else:
        status = "none"
    limits = []
    seen = set()
    for c in cited:
        for d in c["differences"]:
            msg = f"{c['title'][:80]}: {d['note']}"
            if msg not in seen:
                seen.add(msg)
                limits.append(msg)
    if cited and all(c["level"] == "search snippet" for c in cited):
        limits.append("Only search snippets were available for these sources; they are not full-paper evidence.")
    return {"evidence": cited, "evidence_status": status, "evidence_limits": limits}


def build_report(analysis: dict, evidence: dict | None) -> dict:
    evidence = evidence or {}
    sources = evidence.get("sources") or []
    hypotheses = evaluate(analysis)
    triggered = [h for h in hypotheses if h["triggered"]]
    status_by_h = {}
    mode = evidence.get("mode", "not run")
    for h in triggered:
        h.update(_link_evidence(h, sources))
        if not RULES[h["id"]].terms:
            h["evidence_status"] = "not needed"
        elif not sources and mode in ("not run", "unavailable"):
            h["evidence_status"] = mode  # nothing was searched, so "no passage found" would be misleading
        status_by_h[h["id"]] = h["evidence_status"]
    checks = rank_checks(analysis, hypotheses, status_by_h if sources else {})
    sel = analysis.get("selected") or {}
    prov = analysis.get("provenance") or {}
    synthetic = bool(analysis.get("example_id"))
    levels = {}
    for s in sources:
        levels[s.get("evidence_level", "search snippet")] = levels.get(s.get("evidence_level", "search snippet"), 0) + 1
    report = {
        "title": "BenchCheck troubleshooting report",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "version": __version__,
        "synthetic": synthetic,
        "example_id": analysis.get("example_id"),
        "file": {"name": prov.get("filename"), "sha256": prov.get("sha256"), "rows": analysis.get("rows_used")},
        "cycle": sel.get("number"),
        "potential_scale": (analysis.get("display") or {}).get("potential_label"),
        "metadata_rows": analysis.get("metadata_status") or [],
        "observed": [o["text"] for o in analysis.get("observations", [])],
        "quality": analysis.get("quality", []),
        "processing": analysis.get("processing", []),
        "notices": analysis.get("notices", []),
        "explanations": triggered,
        "considered": [{"id": h["id"], "title": h["title"], "reason": h["not_triggered_reason"],
                        "trigger_rule": h["trigger_rule"]} for h in hypotheses if not h["triggered"]],
        "next_check": checks[0] if checks else None,
        "other_checks": checks[1:5],
        "metadata_checks": metadata_checks(analysis),
        "evidence_summary": {
            "mode": evidence.get("mode", "not run"),
            "queries": evidence.get("queries", []),
            "log": evidence.get("log", []),
            "n_sources": len(sources),
            "levels": levels,
            "message": evidence.get("message"),
        },
        "sources": [{k: s.get(k) for k in ("source_id", "title", "link", "year", "venue", "evidence_level", "cached",
                                           "retrieved_at")} for s in sources],
        "disclaimer": DISCLAIMER,
    }
    report["markdown"] = render_markdown(report)
    report["html"] = render_html(report)
    return report


# --------------------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------------------


def _md_escape(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def render_markdown(r: dict) -> str:
    out = [f"# {r['title']}", ""]
    if r["synthetic"]:
        out += ["> **SYNTHETIC EXAMPLE DATA.** Generated by BenchCheck for demonstration; not a measurement.", ""]
    f = r["file"]
    out += [
        f"- Generated: {r['generated_at']} (BenchCheck {r['version']})",
        f"- Data file: `{f['name']}` · {f['rows']} rows · SHA-256 `{(f['sha256'] or '')[:16]}…`",
        f"- Cycle analyzed: {r['cycle']} · Potential scale: {r['potential_scale']}",
        f"- Evidence: {r['evidence_summary']['mode']} · {r['evidence_summary']['n_sources']} source(s)",
        "",
        "## Experiment metadata",
        "",
        "| Field | Value | Status |",
        "|---|---|---|",
    ]
    for m in r["metadata_rows"]:
        out.append(f"| {_md_escape(m['label'])} | {_md_escape(str(m['value']) if m['value'] is not None else '—')} | {m['status']} |")
    out += ["", "## 1. Observed (calculated from the uploaded data)", ""]
    out += [f"- {_md_escape(o)}" for o in r["observed"]] or ["- No features calculated."]
    if r["quality"]:
        out += ["", "**Data-quality flags**", ""]
        out += [f"- [{q['severity']}] {_md_escape(q['message'])}" for q in r["quality"]]
    out += ["", "**Processing disclosed**", ""]
    out += [f"- {_md_escape(p['step'])}: {_md_escape(p['detail'])}" for p in r["processing"]]
    for n in r["notices"]:
        out.append(f"- Notice: {_md_escape(n)}")
    out += ["", "## 2. Possible explanations (hypotheses, not conclusions)", ""]
    if not r["explanations"]:
        out.append("No troubleshooting rule was triggered by the measured features.")
    for k, h in enumerate(r["explanations"], start=1):
        out += [f"### H{k}. {h['title']}", "", h["statement"], "", "**Connected to observed features:**", ""]
        out += [f"- {_md_escape(o)}" for o in h["observations"]]
        out += [f"- Missing metadata: {_md_escape(g)}" for g in h.get("metadata_gaps", [])]
        out += ["", f"*Rule:* {_md_escape(h['trigger_rule'])}", "", "**Evidence:**", ""]
        if h.get("evidence"):
            for e in h["evidence"]:
                year = f" ({e['year']})" if e.get("year") else ""
                cached = " · cached" if e.get("cached") else ""
                out.append(f"- [{_md_escape(e['title'])}]({e['link']}){year} — *{e['level']}*, {e['applicability']}{cached}")
                out.append(f"  > {_md_escape(e['passage'])}")
        else:
            reason = {"not needed": "Assumption-based check; no literature needed.",
                      "none": "No supporting passage retrieved.",
                      "unavailable": "Literature evidence unavailable (SerpApi not reachable or not configured).",
                      "not run": "Literature search not run."}.get(h.get("evidence_status"), "Evidence not retrieved.")
            out.append(f"- {reason}")
        if h.get("evidence_limits"):
            out += ["", "**Limits of the evidence:**", ""]
            out += [f"- {_md_escape(x)}" for x in h["evidence_limits"]]
        out += ["", "**Assumptions:**", ""]
        out += [f"- {_md_escape(a)}" for a in h["assumptions"]]
        if h.get("background"):
            out += [f"- Background: {_md_escape(h['background'])}"]
        out.append("")
    if r["considered"]:
        out += ["**Also considered, not indicated by the data:**", ""]
        out += [f"- {c['title']}: {_md_escape(c['reason'])}" for c in r["considered"]]
        out.append("")
    out += ["## 3. Next check", ""]
    nc = r["next_check"]
    if nc:
        out += [f"**{nc['title']}**", "", nc["procedure"], "", "Why this check:", ""]
        out += [f"- {_md_escape(x)}" for x in nc["reasons"]]
        if nc["tests"]:
            out += ["", "What each outcome would mean:", ""]
            out += [f"- *{t['title']}*: {_md_escape(t['outcome'])}" for t in nc["tests"]]
    if r["other_checks"]:
        out += ["", "Other useful checks:", ""]
        out += [f"{c['rank']}. {c['title']} — {_md_escape(c['procedure'])}" for c in r["other_checks"]]
    if r["metadata_checks"]:
        out += ["", "Metadata to record:", ""]
        out += [f"- {m['label']}: {_md_escape(m['why'])}" for m in r["metadata_checks"]]
    es = r["evidence_summary"]
    out += ["", "## Evidence log (SerpApi)", ""]
    if es.get("message"):
        out += [f"_{_md_escape(es['message'])}_", ""]
    for entry in es["log"]:
        target = entry.get("query") or entry.get("url")
        when = entry.get("retrieved_at") or "—"
        cache = " · cached" if entry.get("cached") else ""
        out.append(f"- `{entry.get('engine')}` {_md_escape(target)} — {entry.get('status')} · {when}{cache}")
    out += ["", "---", "", r["disclaimer"], ""]
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# HTML (self-contained, printable)
# --------------------------------------------------------------------------------------

_CSS = """
body{font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1d2433;max-width:860px;
margin:32px auto;padding:0 20px;background:#fff}
h1{font-size:24px;margin:0 0 8px}h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid #e3e7ef;padding-bottom:4px}
h3{font-size:16px;margin:18px 0 6px}.meta{color:#5b6475;font-size:13px}
.synthetic{background:#fff4e5;border:1px solid #f0b46c;color:#7a4b00;padding:8px 12px;border-radius:6px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #e3e7ef;padding:4px 8px;text-align:left}
.missing{color:#b42318;font-weight:600}blockquote{margin:6px 0 10px;padding:6px 12px;border-left:3px solid #8ea4d2;
background:#f5f7fb;color:#2c3445}.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:9px;
border:1px solid #cdd5e3;margin-right:4px}.next{border:2px solid #2f6fdb;border-radius:8px;padding:12px 16px;background:#f3f7ff}
.small{font-size:12px;color:#5b6475}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _safe_url(url: str | None) -> str | None:
    if url and (url.startswith("https://") or url.startswith("http://")):
        return url
    return None


def render_html(r: dict) -> str:
    p = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{_e(r['title'])}</title>",
         f"<meta name='viewport' content='width=device-width,initial-scale=1'><style>{_CSS}</style></head><body>",
         f"<h1>{_e(r['title'])}</h1>"]
    if r["synthetic"]:
        p.append("<p class='synthetic'>SYNTHETIC EXAMPLE DATA — generated by BenchCheck for demonstration; not a measurement.</p>")
    f = r["file"]
    p.append(f"<p class='meta'>Generated {_e(r['generated_at'])} · BenchCheck {_e(r['version'])}<br>"
             f"Data file <code>{_e(f['name'])}</code> · {_e(f['rows'])} rows · SHA-256 <code>{_e((f['sha256'] or '')[:16])}…</code><br>"
             f"Cycle {_e(r['cycle'])} · {_e(r['potential_scale'])} · Evidence: {_e(r['evidence_summary']['mode'])}, "
             f"{_e(r['evidence_summary']['n_sources'])} source(s)</p>")
    p.append("<h2>Experiment metadata</h2><table><tr><th>Field</th><th>Value</th><th>Status</th></tr>")
    for m in r["metadata_rows"]:
        cls = " class='missing'" if m["status"] == "missing" else ""
        p.append(f"<tr><td>{_e(m['label'])}</td><td>{_e(m['value'] if m['value'] is not None else '—')}</td>"
                 f"<td{cls}>{_e(m['status'])}</td></tr>")
    p.append("</table><h2>1. Observed <span class='small'>(calculated from the uploaded data)</span></h2><ul>")
    p += [f"<li>{_e(o)}</li>" for o in r["observed"]]
    p.append("</ul>")
    if r["quality"]:
        p.append("<p><strong>Data-quality flags</strong></p><ul>")
        p += [f"<li><span class='badge'>{_e(q['severity'])}</span>{_e(q['message'])}</li>" for q in r["quality"]]
        p.append("</ul>")
    p.append("<details><summary>Processing disclosed</summary><ul>")
    p += [f"<li><strong>{_e(x['step'])}:</strong> {_e(x['detail'])}</li>" for x in r["processing"]]
    p += [f"<li>Notice: {_e(n)}</li>" for n in r["notices"]]
    p.append("</ul></details><h2>2. Possible explanations <span class='small'>(hypotheses, not conclusions)</span></h2>")
    if not r["explanations"]:
        p.append("<p>No troubleshooting rule was triggered by the measured features.</p>")
    for k, h in enumerate(r["explanations"], start=1):
        p.append(f"<h3>H{k}. {_e(h['title'])}</h3><p>{_e(h['statement'])}</p><p><strong>Connected to observed features</strong></p><ul>")
        p += [f"<li>{_e(o)}</li>" for o in h["observations"]]
        p += [f"<li class='missing'>Missing metadata: {_e(g)}</li>" for g in h.get("metadata_gaps", [])]
        p.append(f"</ul><p class='small'>Rule: {_e(h['trigger_rule'])}</p><p><strong>Evidence</strong></p>")
        if h.get("evidence"):
            for e in h["evidence"]:
                url = _safe_url(e.get("link"))
                title = f"<a href='{_e(url)}' rel='noopener noreferrer'>{_e(e['title'])}</a>" if url else _e(e["title"])
                p.append(f"<p>{title}{' (' + _e(e['year']) + ')' if e.get('year') else ''} "
                         f"<span class='badge'>{_e(e['level'])}</span><span class='badge'>{_e(e['applicability'])}</span>"
                         f"{'<span class=badge>cached</span>' if e.get('cached') else ''}</p><blockquote>{_e(e['passage'])}</blockquote>")
        else:
            msg = {"unavailable": "Literature evidence unavailable (SerpApi not reachable or not configured).",
                   "not run": "Literature search not run.", "not needed": "Assumption-based check; no literature needed."}
            p.append(f"<p class='small'>{_e(msg.get(h.get('evidence_status'), 'No supporting passage retrieved.'))}</p>")
        if h.get("evidence_limits"):
            p.append("<p><strong>Limits of the evidence</strong></p><ul>")
            p += [f"<li>{_e(x)}</li>" for x in h["evidence_limits"]]
            p.append("</ul>")
        p.append("<p><strong>Assumptions</strong></p><ul>")
        p += [f"<li>{_e(a)}</li>" for a in h["assumptions"]]
        if h.get("background"):
            p.append(f"<li>Background: {_e(h['background'])}</li>")
        p.append("</ul>")
    if r["considered"]:
        p.append("<details><summary>Also considered, not indicated by the data</summary><ul>")
        p += [f"<li>{_e(c['title'])}: {_e(c['reason'])}</li>" for c in r["considered"]]
        p.append("</ul></details>")
    p.append("<h2>3. Next check</h2>")
    nc = r["next_check"]
    if nc:
        p.append(f"<div class='next'><h3>{_e(nc['title'])}</h3><p>{_e(nc['procedure'])}</p><p><strong>Why this check</strong></p><ul>")
        p += [f"<li>{_e(x)}</li>" for x in nc["reasons"]]
        p.append("</ul>")
        if nc["tests"]:
            p.append("<p><strong>What each outcome would mean</strong></p><ul>")
            p += [f"<li><em>{_e(t['title'])}</em>: {_e(t['outcome'])}</li>" for t in nc["tests"]]
            p.append("</ul>")
        p.append("</div>")
    if r["other_checks"]:
        p.append("<p><strong>Other useful checks</strong></p><ol start='2'>")
        p += [f"<li><strong>{_e(c['title'])}</strong> — {_e(c['procedure'])}</li>" for c in r["other_checks"]]
        p.append("</ol>")
    if r["metadata_checks"]:
        p.append("<p><strong>Metadata to record</strong></p><ul>")
        p += [f"<li>{_e(m['label'])}: {_e(m['why'])}</li>" for m in r["metadata_checks"]]
        p.append("</ul>")
    es = r["evidence_summary"]
    p.append("<h2>Evidence log (SerpApi)</h2>")
    if es.get("message"):
        p.append(f"<p class='small'>{_e(es['message'])}</p>")
    p.append("<table><tr><th>Engine</th><th>Query / URL</th><th>Status</th><th>Retrieved</th></tr>")
    for entry in es["log"]:
        p.append(f"<tr><td>{_e(entry.get('engine'))}</td><td>{_e(entry.get('query') or entry.get('url'))}</td>"
                 f"<td>{_e(entry.get('status'))}{' · cached' if entry.get('cached') else ''}</td>"
                 f"<td>{_e(entry.get('retrieved_at'))}</td></tr>")
    p.append(f"</table><p class='small'>{_e(r['disclaimer'])}</p></body></html>")
    return "".join(p)
