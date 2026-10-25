"""Offline tests of the evidence pipeline using clearly labeled synthetic fixtures (tests/fixtures)."""

import json
from pathlib import Path

import httpx
import pytest

from benchcheck.evidence.conditions import compare, extract_conditions, find_scan_rates
from benchcheck.evidence.serpapi import SerpApiClient, cache_key
from benchcheck.evidence.sources import (
    extract_record,
    merge_sources,
    normalize_result,
    parse_extract,
    select_for_extraction,
    snippet_record,
)
from benchcheck.models import EvidenceContext, ExperimentMetadata, Quantity
from benchcheck.settings import Settings

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def ctx(hyps=("side_reaction_vertex", "irreversible_loss", "progressive_degradation")):
    meta = ExperimentMetadata(
        electrode_material="LiMn2O4 composite", process_type="electrode_material", electrolyte="1 M LiCl",
        solvent="aqueous", reference_electrode="ag_agcl_3m_kcl", scan_rate=Quantity(value=1, unit="mV/s"),
    )
    return EvidenceContext(metadata=meta, hypothesis_ids=list(hyps))


def settings(tmp_path, key="test-key-123", mode="auto"):
    return Settings(serpapi_key=key, evidence_mode=mode, cache_dir=tmp_path, max_queries=3, max_extracts=3, timeout_s=5)


# ---------------------------------------------------------------- Scholar results


def test_normalize_result_year_venue_and_links():
    r = normalize_result(load("scholar_fixture.json")["organic_results"][0])
    assert r["year"] == 2021
    assert r["venue"] == "Journal of Fixture Electrochemistry"
    assert r["link"] == "https://example.org/fixture/paper-a"
    assert r["resources"][0]["file_format"] == "PDF"
    book = normalize_result(load("scholar_fixture.json")["organic_results"][2])
    assert book["link"] is None  # Google Books links are not usable sources


def test_snippet_record_conditions_and_passages():
    res = load("scholar_fixture.json")["organic_results"]
    a = snippet_record(res[0], ctx(), "q1")
    assert a["evidence_level"] == "search snippet"
    status = {row["condition"]: row["status"] for row in a["conditions"]}
    assert status["Electrode material"] == "match"
    assert status["Electrolyte"] == "match"
    assert status["Reference electrode"] == "match"
    assert status["Scan rate"] == "match"
    side = [p for p in a["passages"] if p["hypothesis_id"] == "side_reaction_vertex"]
    assert side and side[0]["verbatim_verified"] and side[0]["level"] == "search snippet"
    assert side[0]["text"] in res[0]["snippet"]

    b = snippet_record(res[1], ctx(), "q2")
    status_b = {row["condition"]: row["status"] for row in b["conditions"]}
    assert status_b["Solvent"] == "differs"  # carbonate (non-aqueous) vs aqueous
    assert status_b["Reference electrode"] == "differs"  # Li/Li+ vs Ag/AgCl
    assert status_b["Scan rate"] == "differs"  # 0.1 vs 1 mV/s (10x)
    assert b["applicability"]["level"] != "condition-matched"
    notes = " ".join(d["note"] for d in b["applicability"]["differences"])
    assert "Li/Li⁺" in notes and "aqueous" in notes


def test_scan_rate_parsing_lists_and_ranges():
    vals, ranges, _ = find_scan_rates("at 0.1, 0.5 and 1 mV s−1, and from 5 to 100 mV/s")
    assert vals == pytest.approx([1e-4, 5e-4, 1e-3])
    assert ranges == [pytest.approx((0.005, 0.1))]


def test_unknown_user_material_uses_custom_pattern():
    meta = ExperimentMetadata(electrode_material="Fe2O3 nanorods", solvent="aqueous")
    c = EvidenceContext(metadata=meta)
    from benchcheck.evidence.sources import _user_context

    u = _user_context(c)
    rows = compare(extract_conditions([("title", "Fe2O3 photoanodes in KOH")], u["custom_material"]), u)
    assert rows[0]["status"] == "match"


# ---------------------------------------------------------------- Extract API content


def test_parse_extract_full_text_excludes_references():
    parsed = parse_extract(load("extract_fulltext_fixture.json"))
    assert parsed["level"] == "full text"
    assert {"introduction", "methods", "results", "conclusion"} <= set(parsed["sections"])
    assert "must not be quoted" not in parsed["body"]


def test_parse_extract_abstract_from_meta():
    parsed = parse_extract(load("extract_abstract_fixture.json"))
    assert parsed["level"] == "abstract"
    assert parsed["abstract_source"] == "page metadata (citation_abstract)"


def test_extract_record_upgrades_level_and_keeps_verbatim():
    res = load("scholar_fixture.json")["organic_results"][0]
    snip = snippet_record(res, ctx(), "q1")
    data = load("extract_fulltext_fixture.json")
    up = extract_record(snip, data, ctx(), {"via": "serpapi_extract", "cached": False})
    assert up["evidence_level"] == "full text"
    text = data["text_content"]["markdown"]
    for p in up["passages"]:
        if p["level"] != "search snippet":
            assert p["verbatim_verified"]
            assert " ".join(p["text"].split()) in " ".join(text.split())
            assert "must not be quoted" not in p["text"]
    diss = [p for p in up["passages"] if p["hypothesis_id"] == "progressive_degradation"]
    assert diss and "dissolution" in diss[0]["text"].lower()


def test_extract_failure_keeps_snippet():
    snip = snippet_record(load("scholar_fixture.json")["organic_results"][0], ctx(), "q1")
    out = extract_record(snip, None, ctx(), {"error": "SerpApi error: unsupported page"})
    assert out["evidence_level"] == "search snippet"
    assert out["content"]["status"] == "retrieval failed"


def test_merge_and_select():
    res = load("scholar_fixture.json")["organic_results"]
    recs = [snippet_record(res[0], ctx(), "q1"), snippet_record(res[1], ctx(), "q1"),
            snippet_record(res[0], ctx(), "q2"), snippet_record(res[2], ctx(), "q2")]
    merged = merge_sources(recs)
    assert len(merged) == 3
    a = next(m for m in merged if m["source_id"] == "gs_fixtureA")
    assert a["found_by"] == ["q1", "q2"]
    chosen = select_for_extraction(merged, budget=5)
    assert chosen[0]["source_id"] == "gs_fixtureA"
    assert all("books.google" not in c["url"] for c in chosen)


# ---------------------------------------------------------------- SerpApi client and cache


def test_live_call_is_cached_without_key(tmp_path):
    seen = {}

    def handler(request: httpx.Request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=load("scholar_fixture.json"))

    client = SerpApiClient(settings(tmp_path), transport=httpx.MockTransport(handler))
    res = client.scholar("LiMn2O4 aqueous LiCl oxygen evolution side reaction")
    assert res.ok and res.status == "live" and not res.cached
    assert seen["params"]["engine"] == "google_scholar" and seen["params"]["api_key"] == "test-key-123"
    files = list((tmp_path / "live" / "google_scholar").glob("*.json"))
    assert len(files) == 1
    stored = files[0].read_text()
    assert "test-key-123" not in stored
    record = json.loads(stored)
    assert record["params"]["q"].startswith("LiMn2O4") and "api_key" not in record["params"]

    cache_only = SerpApiClient(settings(tmp_path, key=None))
    again = cache_only.scholar("LiMn2O4 aqueous LiCl oxygen evolution side reaction")
    assert again.ok and again.cached and again.status == "cached"
    assert again.retrieved_at == record["retrieved_at"]
    assert again.log_entry()["credits"] == 0


def test_error_is_redacted_and_not_cached(tmp_path):
    def handler(request):
        return httpx.Response(401, json={"error": "Invalid API key test-key-123"})

    client = SerpApiClient(settings(tmp_path), transport=httpx.MockTransport(handler))
    res = client.scholar("anything")
    assert not res.ok and res.status == "error"
    assert "test-key-123" not in res.error
    assert not (tmp_path / "live").exists()


def test_network_failure_falls_back_to_real_cache(tmp_path):
    def ok(request):
        return httpx.Response(200, json=load("scholar_fixture.json"))

    SerpApiClient(settings(tmp_path), transport=httpx.MockTransport(ok)).scholar("q")

    def down(request):
        raise httpx.ConnectError("offline")

    res = SerpApiClient(settings(tmp_path), transport=httpx.MockTransport(down)).scholar("q")
    assert res.ok and res.cached and "cached" in res.fallback_note


def test_unavailable_without_key_or_cache(tmp_path):
    res = SerpApiClient(settings(tmp_path, key=None)).scholar("never searched")
    assert not res.ok and res.status == "unavailable"
    assert "not configured" in res.error


def test_empty_scholar_results_are_not_errors(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"search_metadata": {"id": "x", "status": "Success"},
                                         "error": "Google hasn't returned any results for this query."})

    res = SerpApiClient(settings(tmp_path), transport=httpx.MockTransport(handler)).scholar("zzz")
    assert res.ok and res.status == "live"


def test_cache_key_ignores_api_key():
    assert cache_key({"engine": "e", "q": "x", "api_key": "a"}) == cache_key({"engine": "e", "q": "x"})
