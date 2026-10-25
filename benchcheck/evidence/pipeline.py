"""Server-side evidence run, mirroring the browser's orchestration (search → select → extract).

Used by scripts/refresh_demo_cache.py (to record real responses for the offline
demo) and scripts/evaluate.py (to audit cited passages).
"""

from __future__ import annotations

from ..models import EvidenceContext, ExperimentMetadata
from .serpapi import SerpApiClient
from .sources import extract_record, extraction_url, merge_sources, select_for_extraction, snippet_record


def run_evidence(analysis: dict, client: SerpApiClient, max_extracts: int, prefer_cache: bool = False) -> dict:
    hypotheses = analysis.get("hypotheses") or []
    triggered = [h["id"] for h in hypotheses if h["triggered"]]
    ctx = EvidenceContext(
        metadata=ExperimentMetadata(**analysis["metadata"]),
        hypothesis_ids=triggered,
        measured_scan_rate_v_s=analysis.get("scan_rate_measured"),
    )
    log, records, queries = [], [], []
    for q in analysis.get("evidence_plan") or []:
        res = client.scholar(q["query"], prefer_cache=prefer_cache)
        entry = res.log_entry(query_id=q["id"], purpose=q["purpose"], kind="scholar_search")
        if res.ok and res.data:
            organic = res.data.get("organic_results") or []
            entry["results_count"] = len(organic)
            for r in organic:
                rec = snippet_record(r, ctx, q["id"])
                rec["cached"], rec["retrieved_at"] = res.cached, res.retrieved_at
                records.append(rec)
        log.append(entry)
        queries.append({**q, "status": res.status})
    sources = merge_sources(records)
    for item in select_for_extraction(sources, max_extracts):
        idx = next(k for k, s in enumerate(sources) if s["source_id"] == item["source_id"])
        url = extraction_url(sources[idx])
        res = client.extract(url, prefer_cache=prefer_cache)
        meta = {"via": "SerpApi Extract API", "url": url, "cached": res.cached, "retrieved_at": res.retrieved_at,
                "error": res.error, "fallback_note": res.fallback_note}
        sources[idx] = extract_record(sources[idx], res.data if res.ok else None, ctx, meta)
        log.append(res.log_entry(kind="extract", source_id=item["source_id"],
                                 classification=(sources[idx].get("content") or {}).get("status")))
    ok = [e for e in log if e["ok"]]
    live = any(e["status"] == "live" for e in ok)
    cached = any(e["status"] == "cached" for e in ok)
    mode = "live + cached" if live and cached else "live" if live else "cached" if cached else "unavailable"
    message = None
    if not ok:
        message = next((e["error"] for e in log if e.get("error")), "No evidence retrieved.")
    return {"mode": mode, "queries": queries, "log": log, "sources": sources, "message": message}
