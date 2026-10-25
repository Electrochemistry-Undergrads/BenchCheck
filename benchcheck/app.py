"""BenchCheck web application (FastAPI).

Run:  uvicorn benchcheck.app:app --reload     (or: python -m benchcheck)
"""

from __future__ import annotations

import json
import re
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .http_hygiene import HTTPHygiene
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import __version__, sessions
from .cv.plot_data import decimate
from .cv.analysis import AnalysisError, analyze
from .cv.parsing import MAX_BYTES, ParseError, parse_table, suggest_mapping
from .cv.reference import REFERENCE_ELECTRODES, plan_conversion
from .evidence.serpapi import SerpApiClient
from .evidence.sources import extract_record, extraction_url, merge_sources, select_for_extraction, snippet_record
from .models import (
    AnalysisConfig,
    ConversionPreviewRequest,
    ExtractRequest,
    ReportRequest,
    SearchRequest,
    SelectRequest,
)
from .reasoning.hypotheses import THRESHOLDS, evaluate, evidence_plan
from .reasoning.report import build_report
from .settings import PROJECT_ROOT, get_settings

WEB_DIR = PROJECT_ROOT / "web"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
_EXAMPLE_FILE = re.compile(r"^[a-z0-9_]+\.(csv|meta\.json)$")

app = FastAPI(title="BenchCheck", version=__version__, docs_url="/api/docs", redoc_url=None)
app.add_middleware(HTTPHygiene)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.environ.get("BENCHCHECK_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1],testserver").split(","))
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _client() -> SerpApiClient:
    return SerpApiClient(get_settings())


def _read_upload(file: UploadFile) -> bytes:
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    return raw


def _examples() -> list[dict]:
    out = []
    for path in sorted(EXAMPLES_DIR.glob("*.meta.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta.pop("ground_truth", None)
        out.append(meta)
    return out


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/examples/{name}", include_in_schema=False)
def example_file(name: str):
    if not _EXAMPLE_FILE.match(name) or not (EXAMPLES_DIR / name).is_file():
        raise HTTPException(404, "Example not found.")
    return FileResponse(EXAMPLES_DIR / name)


@app.get("/api/status")
def status():
    s = get_settings()
    client = SerpApiClient(s)
    return {
        "version": __version__,
        "serpapi_configured": bool(s.serpapi_key),
        "evidence_mode": s.describe_mode(),
        "configured_mode": s.evidence_mode,
        "cache_entries": client.cache.count(),
        "max_queries": s.max_queries,
        "max_extracts": s.max_extracts,
        "thresholds": THRESHOLDS,
        "reference_electrodes": {k: {"label": v["label"], "vs_she": v["vs_she"]} for k, v in REFERENCE_ELECTRODES.items()},
    }


@app.get("/api/examples")
def examples():
    return _examples()


@app.post("/api/inspect")
async def inspect(request: Request, file: UploadFile = File(...)):
    if len((await request.form()).getlist("file")) != 1:
        raise HTTPException(422, "Provide exactly one file part.")
    raw = _read_upload(file)
    try:
        table = parse_table(raw, file.filename or "upload")
    except ParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"table": table.summary(), **suggest_mapping(table)}


@app.post("/api/conversion-preview")
def conversion_preview(req: ConversionPreviewRequest):
    """Describe (without applying) a reference conversion so the user can confirm it."""
    return plan_conversion(req.from_, req.target, req.ph, req.temperature_c, req.offset_v, req.description)


@app.post("/api/analyze")
async def analyze_endpoint(request: Request, file: UploadFile = File(...), config: str = Form(...), full_resolution: bool = False):
    if len((await request.form()).getlist("file")) != 1:
        raise HTTPException(422, "Provide exactly one file part.")
    raw = _read_upload(file)
    try:
        cfg = AnalysisConfig.model_validate_json(config)
    except ValidationError as exc:
        raise HTTPException(422, [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]) from exc
    try:
        table = parse_table(raw, file.filename or "upload")
        result = analyze(table, cfg)
    except (ParseError, AnalysisError) as exc:
        raise HTTPException(422, str(exc)) from exc
    hyps = evaluate(result)
    result["hypotheses"] = hyps
    result["evidence_plan"] = evidence_plan(result, hyps, get_settings().max_queries)
    result["thresholds"] = THRESHOLDS
    sessions.create(result, cfg.model_dump(exclude={"selected_cycle"}))
    return result if full_resolution else decimate(result)


@app.post("/api/evidence/search")
def evidence_search(req: SearchRequest):
    session = sessions.get(req.analysis_id)
    client = _client()
    sessions.consume(session, "queries", get_settings().max_queries, client.settings.live_enabled)
    ctx = session.context()
    res = client.scholar(req.query, prefer_cache=req.prefer_cache)
    entry = res.log_entry(query_id=req.query_id, purpose=req.purpose, kind="scholar_search")
    sources = []
    if res.ok and res.data:
        organic = res.data.get("organic_results") or []
        entry["results_count"] = len(organic)
        entry["total_results"] = (res.data.get("search_information") or {}).get("total_results")
        for r in organic:
            rec = snippet_record(r, ctx, req.query_id)
            rec["cached"] = res.cached
            rec["retrieved_at"] = res.retrieved_at
            sources.append(rec)
    with sessions.LOCK:
        for source in sources:
            prior = session.sources.get(source["source_id"])
            session.sources[source["source_id"]] = merge_sources([prior, source])[0] if prior else source
        session.logs.append(entry)
    return {"log": entry, "sources": sources}


@app.post("/api/evidence/select")
def evidence_select(req: SelectRequest):
    session = sessions.get(req.analysis_id)
    merged = merge_sources([sessions.source(session, s.source_id) for s in req.sources])
    budget = get_settings().max_extracts
    return {"sources": merged, "extract": select_for_extraction(merged, budget), "budget": budget}


@app.post("/api/evidence/extract")
def evidence_extract(req: ExtractRequest):
    session = sessions.get(req.analysis_id)
    source = sessions.source(session, req.source.source_id)
    selected = select_for_extraction(list(session.sources.values()), get_settings().max_extracts)
    if source["source_id"] not in {s["source_id"] for s in selected}:
        raise HTTPException(422, "source_id was not selected for extraction.")
    client = _client()
    sessions.consume(session, "extracts", get_settings().max_extracts, client.settings.live_enabled)
    url = extraction_url(source)
    if not url:
        raise HTTPException(422, "This source has no retrievable link.")
    res = client.extract(url, prefer_cache=req.prefer_cache)
    call_meta = {"via": "SerpApi Extract API", "url": url, "cached": res.cached, "retrieved_at": res.retrieved_at,
                 "error": res.error, "fallback_note": res.fallback_note}
    updated = extract_record(source, res.data if res.ok else None, session.context(), call_meta)
    if updated.get("doi"):
        from .evidence.bibliography import lookup
        updated.update(lookup(updated["doi"]))
    if res.ok:
        updated["cached"] = updated.get("cached", False) or res.cached
    entry = res.log_entry(kind="extract", source_id=source["source_id"],
                          classification=(updated.get("content") or {}).get("status"))
    if updated["content"]["status"] in ("no usable content", "retrieval failed"):
        entry["ok"] = False
        entry["status"] = "error"
        entry["error"] = updated["content"]["reason"]
    with sessions.LOCK:
        session.sources[source["source_id"]] = updated
        session.logs.append(entry)
    return {"log": entry, "source": updated}


@app.post("/api/report")
def report(req: ReportRequest):
    try:
        session = sessions.get(req.analysis_id or req.analysis.get("analysis_id"))
        logs = list(session.logs)
        good = [e for e in logs if e.get("ok")]
        statuses = {"cached" if e.get("cached") else e["status"] for e in good}
        mode = "live + cached" if {"live", "cached"} <= statuses else "live" if "live" in statuses else "cached" if "cached" in statuses else "unavailable" if logs else "not run"
        evidence = {"sources": list(session.sources.values()), "log": logs, "mode": mode}
        return build_report(session.analysis, evidence)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError) as exc:
        raise HTTPException(422, f"The analysis or evidence payload is incomplete ({type(exc).__name__}).") from exc


@app.exception_handler(ValueError)
def value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": "Invalid experiment settings or data; check the entered fields and units."})


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_request, exc):
    return JSONResponse(status_code=422, content={"detail": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]})
