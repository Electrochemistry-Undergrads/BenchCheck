"""BenchCheck web application (FastAPI).

Run:  uvicorn benchcheck.app:app --reload     (or: python -m benchcheck)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import __version__
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
def inspect(file: UploadFile = File(...)):
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
def analyze_endpoint(file: UploadFile = File(...), config: str = Form(...)):
    raw = _read_upload(file)
    try:
        cfg = AnalysisConfig.model_validate_json(config)
    except ValidationError as exc:
        raise HTTPException(422, f"Invalid analysis settings: {exc.errors()[0].get('msg')}") from exc
    try:
        table = parse_table(raw, file.filename or "upload")
        result = analyze(table, cfg)
    except (ParseError, AnalysisError) as exc:
        raise HTTPException(422, str(exc)) from exc
    hyps = evaluate(result)
    result["hypotheses"] = hyps
    result["evidence_plan"] = evidence_plan(result, hyps, get_settings().max_queries)
    result["thresholds"] = THRESHOLDS
    return result


@app.post("/api/evidence/search")
def evidence_search(req: SearchRequest):
    res = _client().scholar(req.query, prefer_cache=req.prefer_cache)
    entry = res.log_entry(query_id=req.query_id, purpose=req.purpose, kind="scholar_search")
    sources = []
    if res.ok and res.data:
        organic = res.data.get("organic_results") or []
        entry["results_count"] = len(organic)
        entry["total_results"] = (res.data.get("search_information") or {}).get("total_results")
        for r in organic:
            rec = snippet_record(r, req.context, req.query_id)
            rec["cached"] = res.cached
            rec["retrieved_at"] = res.retrieved_at
            sources.append(rec)
    return {"log": entry, "sources": sources}


@app.post("/api/evidence/select")
def evidence_select(req: SelectRequest):
    merged = merge_sources(req.sources)
    budget = get_settings().max_extracts
    return {"sources": merged, "extract": select_for_extraction(merged, budget), "budget": budget}


@app.post("/api/evidence/extract")
def evidence_extract(req: ExtractRequest):
    url = extraction_url(req.source)
    if not url:
        raise HTTPException(422, "This source has no retrievable link.")
    res = _client().extract(url, prefer_cache=req.prefer_cache)
    call_meta = {"via": "SerpApi Extract API", "url": url, "cached": res.cached, "retrieved_at": res.retrieved_at,
                 "error": res.error, "fallback_note": res.fallback_note}
    updated = extract_record(req.source, res.data if res.ok else None, req.context, call_meta)
    if res.ok:
        updated["cached"] = updated.get("cached", False) or res.cached
    entry = res.log_entry(kind="extract", source_id=req.source.get("source_id"),
                          classification=(updated.get("content") or {}).get("status"))
    return {"log": entry, "source": updated}


@app.post("/api/report")
def report(req: ReportRequest):
    try:
        return build_report(req.analysis, req.evidence)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError) as exc:
        raise HTTPException(422, f"The analysis or evidence payload is incomplete ({type(exc).__name__}).") from exc


@app.exception_handler(ValueError)
def value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})
