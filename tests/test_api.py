"""End-to-end API tests. SerpApi is replaced by an httpx MockTransport serving the labeled test fixtures."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import benchcheck.app as app_module
from benchcheck.evidence.serpapi import SerpApiClient
from benchcheck.settings import Settings
from tests.conftest import EXAMPLES

FIX = Path(__file__).parent / "fixtures"


def fixture_transport(request: httpx.Request) -> httpx.Response:
    engine = request.url.params.get("engine")
    if engine == "google_scholar":
        return httpx.Response(200, json=json.loads((FIX / "scholar_fixture.json").read_text()))
    if engine == "extract":
        name = "extract_fulltext_fixture.json" if "paper-a" in request.url.params.get("url", "") else "extract_abstract_fixture.json"
        return httpx.Response(200, json=json.loads((FIX / name).read_text()))
    return httpx.Response(400, json={"error": "unknown engine"})


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(serpapi_key="fixture-key", evidence_mode="live", cache_dir=tmp_path, max_queries=3,
                        max_extracts=3, timeout_s=5)
    monkeypatch.setattr(app_module, "_client", lambda: SerpApiClient(settings, transport=httpx.MockTransport(fixture_transport)))
    return TestClient(app_module.app)


def example_payload(example_id):
    meta = json.loads((EXAMPLES / f"{example_id}.meta.json").read_text())
    cfg = {"mapping": meta["mapping"], "units": meta["units"], "metadata": meta["metadata"], "example_id": example_id}
    return (EXAMPLES / meta["file"]).read_bytes(), cfg


def test_index_and_static(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/examples/synthetic_lmo_weak_return.csv").status_code == 200
    assert client.get("/examples/../benchcheck/settings.py").status_code == 404


def test_status_never_exposes_key(client):
    body = client.get("/api/status").text
    assert "fixture-key" not in body


def test_inspect_suggests_mapping(client):
    raw, _ = example_payload("synthetic_lmo_weak_return")
    r = client.post("/api/inspect", files={"file": ("x.csv", raw, "text/csv")})
    assert r.status_code == 200
    s = r.json()["suggested"]
    assert s["potential"]["column"] == "Ewe/V" and s["current"]["column"] == "<I>/mA"


def test_inspect_rejects_garbage(client):
    r = client.post("/api/inspect", files={"file": ("x.csv", b"not,a\nvoltammogram,file\n", "text/csv")})
    assert r.status_code == 422


def test_full_pipeline_weak_example(client):
    raw, cfg = example_payload("synthetic_lmo_weak_return")
    r = client.post("/api/analyze", files={"file": ("w.csv", raw, "text/csv")}, data={"config": json.dumps(cfg)})
    assert r.status_code == 200, r.text
    analysis = r.json()
    triggered = [h["id"] for h in analysis["hypotheses"] if h["triggered"]]
    assert {"side_reaction_vertex", "irreversible_loss", "progressive_degradation"} <= set(triggered)
    plan = analysis["evidence_plan"]
    assert 1 <= len(plan) <= 3 and all("LiMn2O4" in q["query"] for q in plan)

    ctx = {"metadata": analysis["metadata"], "hypothesis_ids": triggered,
           "measured_scan_rate_v_s": analysis["scan_rate_measured"]}
    records, logs = [], []
    for q in plan:
        s = client.post("/api/evidence/search", json={"query_id": q["id"], "query": q["query"], "purpose": q["purpose"],
                                                      "hypothesis_ids": q["hypotheses"], "context": ctx}).json()
        assert s["log"]["status"] == "live" and s["log"]["credits"] == 1
        logs.append(s["log"])
        records += s["sources"]
    sel = client.post("/api/evidence/select", json={"sources": records, "context": ctx}).json()
    assert len(sel["sources"]) == 3  # deduplicated across the three queries
    sources = sel["sources"]
    for item in sel["extract"]:
        idx = next(k for k, s in enumerate(sources) if s["source_id"] == item["source_id"])
        out = client.post("/api/evidence/extract", json={"source": sources[idx], "context": ctx}).json()
        sources[idx] = out["source"]
        logs.append(out["log"])
    levels = {s["source_id"]: s["evidence_level"] for s in sources}
    assert levels["gs_fixtureA"] == "full text"
    assert levels["gs_fixtureB"] == "abstract"

    summary = {k: v for k, v in analysis.items() if k != "data"}
    rep = client.post("/api/report", json={"analysis": summary, "evidence": {"mode": "live", "log": logs, "sources": sources}}).json()
    side = next(h for h in rep["explanations"] if h["id"] == "side_reaction_vertex")
    assert side["evidence"] and side["evidence"][0]["level"] in ("full text", "abstract")
    # The carbonate-electrolyte fixture must carry its limitations into the report.
    deg = next(h for h in rep["explanations"] if h["id"] == "progressive_degradation")
    assert any("aqueous" in lim for lim in deg["evidence_limits"])
    assert rep["next_check"]["id"] == "vertex_window"
    assert "SYNTHETIC" in rep["markdown"] and "SYNTHETIC" in rep["html"]
    assert "<script" not in rep["html"]


def test_report_without_evidence_is_labeled(client):
    raw, cfg = example_payload("synthetic_lmo_weak_return")
    analysis = client.post("/api/analyze", files={"file": ("w.csv", raw, "text/csv")},
                           data={"config": json.dumps(cfg)}).json()
    summary = {k: v for k, v in analysis.items() if k != "data"}
    rep = client.post("/api/report", json={"analysis": summary, "evidence": {"mode": "unavailable"}}).json()
    assert all(h["evidence_status"] in ("unavailable", "not needed") for h in rep["explanations"])


def test_bad_config_is_422(client):
    raw, cfg = example_payload("synthetic_lmo_clear_return")
    cfg["mapping"]["potential"] = "does-not-exist"
    r = client.post("/api/analyze", files={"file": ("c.csv", raw, "text/csv")}, data={"config": json.dumps(cfg)})
    assert r.status_code == 422


def test_conversion_preview(client):
    r = client.post("/api/conversion-preview", json={"from": "ag_agcl_3m_kcl", "target": "SHE"}).json()
    assert r["possible"] and r["offset_v"] == pytest.approx(0.210)
    r = client.post("/api/conversion-preview", json={"from": "li", "target": "SHE"}).json()
    assert not r["possible"]
    r = client.post("/api/conversion-preview", json={"from": "sce", "target": "RHE", "ph": 7}).json()
    assert r["offset_v"] == pytest.approx(0.241 + 0.05916 * 7, abs=1e-4)


def test_conversion_preview_validates_input(client):
    assert client.post("/api/conversion-preview", json={"from": "sce", "target": "RHE", "ph": "seven"}).status_code == 422


@pytest.mark.parametrize("analysis", [
    {},
    {"selected": "not-a-dict"},
    {"selected": {"pairs": [{}], "main_pair": 0}},
    {"selected": {"forward": {"peaks": [{"label": "A1"}]}}, "metadata": None},
])
def test_report_never_500s_on_malformed_payload(client, analysis):
    assert client.post("/api/report", json={"analysis": analysis}).status_code in (200, 422)


@pytest.mark.parametrize("simulated", [True, False])
def test_uploaded_data_report_provenance(client, simulated):
    raw, cfg = example_payload("synthetic_lmo_weak_return")
    cfg["example_id"] = "uploaded_synthetic" if simulated else None
    analysis = client.post("/api/analyze", files={"file": ("upload.csv", raw, "text/csv")},
                           data={"config": json.dumps(cfg)}).json()
    summary = {k: v for k, v in analysis.items() if k != "data"}
    response = client.post("/api/report", json={"analysis": summary, "evidence": {"mode": "not run"}})
    assert response.status_code == 200
    report = response.json()
    assert report["synthetic"] is simulated
    for export in ("markdown", "html"):
        assert ("SIMULATED DATA" in report[export]) is simulated
        assert "Generated by BenchCheck for demonstration" not in report[export]
        assert "generated by BenchCheck for demonstration" not in report[export]
