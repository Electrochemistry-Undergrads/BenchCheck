"""Integration tests of the numerical analysis, including validation against theory."""

import io
import math

import numpy as np
import pytest

from benchcheck.cv.analysis import AnalysisError, analyze
from benchcheck.cv.parsing import parse_table
from benchcheck.models import AnalysisConfig, Quantity, ReferenceConversion
from benchcheck.synth.diffusion import simulate_reversible
from benchcheck.synth.thinfilm import F, R, Site, ThinFilmParams, simulate
from tests.conftest import example_config

RT_F = R * 298.15 / F


def csv_bytes(t, E, i, i_scale=1.0, e_scale=1.0, header="time/s,E/V,I/A"):
    buf = io.StringIO()
    buf.write(header + "\n")
    for a, b, c in zip(t, E, i):
        buf.write(f"{a:.6f},{b * e_scale:.7f},{c * i_scale:.9e}\n")
    return buf.getvalue().encode()


def base_config(**kw):
    cfg = {"mapping": {"potential": "E/V", "current": "I/A", "time": "time/s"},
           "units": {"potential": "V", "current": "A", "time": "s"}}
    cfg.update(kw)
    return AnalysisConfig(**cfg)


def pair_of(result, k=0):
    return result["selected"]["pairs"][k]


# ---------------------------------------------------------------- theory validation


def test_reversible_diffusion_matches_randles_sevcik_and_criteria():
    sim = simulate_reversible(e0=0.25, e_start=-0.05, e_vertex=0.55, scan_rate=0.1)
    raw = csv_bytes(sim["time_s"], sim["potential_v"], sim["current_a"])
    meta = {"process_type": "dissolved_species", "scan_rate": {"value": 100, "unit": "mV/s"}}
    res = analyze(parse_table(raw), base_config(metadata=meta))
    sel = res["selected"]
    a1 = sel["forward"]["peaks"][0]
    assert a1["height"] == pytest.approx(sim["randles_sevcik_a"], rel=0.02)
    pair = pair_of(res)
    assert 0.055 <= pair["delta_ep"] <= 0.062  # reversible: ≈ 2.22 RT/F = 57 mV
    assert pair["e_mid"] == pytest.approx(0.25, abs=0.004)  # E1/2 = E0 for equal D
    assert pair["nicholson_ratio"] == pytest.approx(1.0, abs=0.05)


def test_reversible_thin_layer_matches_surface_theory():
    q = 1e-4
    p = ThinFilmParams(sites=[Site(0.5, q, k0=1e4)], e_low=0.2, e_high=0.8, e_start=0.2, scan_rate=0.01, n_cycles=2)
    sim = simulate(p)
    raw = csv_bytes(sim["time_s"], sim["potential_v"], sim["current_a"])
    res = analyze(parse_table(raw), base_config(metadata={"process_type": "electrode_material"}))
    sel = res["selected"]
    a = sel["forward"]["peaks"][0]
    theory_ip = F * p.scan_rate * q / (4 * R * 298.15)  # n^2 F^2 v A Γ / 4RT with Q = F A Γ
    assert a["height"] == pytest.approx(theory_ip, rel=0.01)
    assert a["width_v"] == pytest.approx(3.5255 * RT_F, rel=0.02)  # 90.6 mV
    assert abs(pair_of(res)["delta_ep"]) < 0.004
    assert sel["charge_ratio"] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------- the demo examples


def test_clear_example_features(clear_example):
    raw, cfg = clear_example
    res = analyze(parse_table(raw), cfg)
    sel = res["selected"]
    assert sel["number"] == 2
    assert [p["label"] for p in sel["forward"]["peaks"]] and len(sel["pairs"]) == 2
    for pair in sel["pairs"]:
        assert 0.9 <= pair["height_ratio"] <= 1.1
        assert 0.04 <= pair["delta_ep"] <= 0.09
    assert sel["charge_ratio"] > 0.95
    assert not sel["forward"]["vertex"]["rising"]
    assert abs(res["trends"]["height_change_pct"]) < 10
    assert not [q for q in res["quality"] if q["severity"] == "high"]


def test_weak_example_features(weak_example):
    raw, cfg = weak_example
    res = analyze(parse_table(raw), cfg)
    sel = res["selected"]
    ratios = [p["height_ratio"] for p in sel["pairs"]]
    assert len(ratios) == 2 and max(ratios) < 0.7
    assert sel["charge_ratio"] < 0.6
    assert sel["forward"]["vertex"]["rising"]
    assert res["trends"]["height_change_pct"] < -10


def test_weak_example_bias_against_ground_truth(weak_example):
    """Known limitation: the side-current tail biases the flat return baseline. Keep it bounded."""
    import json
    from tests.conftest import EXAMPLES

    raw, cfg = weak_example
    truth = json.loads((EXAMPLES / "synthetic_lmo_weak_return.meta.json").read_text())["ground_truth"]["per_cycle"][1]
    sel = analyze(parse_table(raw), cfg)["selected"]
    by_pair = {p["return"]: p["height_ratio"] for p in sel["pairs"]}
    assert by_pair["C1"] == pytest.approx(truth["faradaic_ratio_C1_A1"], rel=0.15)
    assert by_pair["C2"] == pytest.approx(truth["faradaic_ratio_C2_A2"], rel=0.15)


# ---------------------------------------------------------------- invariances and explicit handling


def test_units_do_not_change_features(clear_example):
    raw, cfg = clear_example
    ref = analyze(parse_table(raw), cfg)["selected"]
    text = raw.decode().splitlines()
    rows = [ln for ln in text if ln and not ln.startswith("#")][1:]
    converted = ["t_s,E_mV,I_uA"] + [
        f"{a},{float(b) * 1000:.3f},{float(c) * 1000:.4f}" for a, b, c in (r.split(",") for r in rows)
    ]
    cfg2 = cfg.model_copy(update={"mapping": cfg.mapping.model_copy(update={"potential": "E_mV", "current": "I_uA", "time": "t_s"}),
                                  "units": cfg.units.model_copy(update={"potential": "mV", "current": "µA"})})
    other = analyze(parse_table("\n".join(converted).encode()), cfg2)["selected"]
    for a, b in zip(ref["forward"]["peaks"], other["forward"]["peaks"]):
        assert a["potential"] == pytest.approx(b["potential"], abs=1e-6)
        assert a["height"] == pytest.approx(b["height"], rel=1e-6)


def test_cathodic_positive_convention_is_inverted(clear_example):
    raw, cfg = clear_example
    ref = analyze(parse_table(raw), cfg)["selected"]
    lines = raw.decode().splitlines()
    flipped = []
    for ln in lines:
        if ln.startswith("#") or ln.startswith("time"):
            flipped.append(ln)
        else:
            a, b, c = ln.split(",")
            flipped.append(f"{a},{b},{-float(c):.6f}")
    cfg2 = cfg.model_copy(update={"current_convention": "cathodic_positive"})
    res = analyze(parse_table("\n".join(flipped).encode()), cfg2)
    assert res["selected"]["pairs"][0]["height_ratio"] == pytest.approx(ref["pairs"][0]["height_ratio"], rel=1e-9)
    assert any("sign" in p["step"].lower() for p in res["processing"])


def test_wrong_sign_convention_is_hinted(clear_example):
    raw, cfg = clear_example
    lines = raw.decode().splitlines()
    flipped = [ln if (ln.startswith("#") or ln.startswith("time")) else
               ",".join([*ln.split(",")[:2], f"{-float(ln.split(',')[2]):.6f}"]) for ln in lines]
    res = analyze(parse_table("\n".join(flipped).encode()), cfg)
    assert "sign_convention_hint" in [q["code"] for q in res["quality"]]


def test_reference_conversion_requires_confirmation(clear_example):
    raw, cfg = clear_example
    table = parse_table(raw)
    base = analyze(table, cfg)["selected"]["forward"]["peaks"][0]["potential"]
    unconfirmed = analyze(table, cfg.model_copy(update={"reference_conversion": ReferenceConversion(target="SHE", confirmed=False)}))
    assert unconfirmed["selected"]["forward"]["peaks"][0]["potential"] == pytest.approx(base)
    assert any("confirmation" in n for n in unconfirmed["notices"])
    confirmed = analyze(table, cfg.model_copy(update={"reference_conversion": ReferenceConversion(target="SHE", confirmed=True)}))
    assert confirmed["selected"]["forward"]["peaks"][0]["potential"] == pytest.approx(base + 0.210)
    assert confirmed["potential_scale"]["label"] == "V vs SHE"


def test_area_normalization_requires_confirmation(clear_example):
    raw, cfg = clear_example
    table = parse_table(raw)
    meta = cfg.metadata.model_copy(update={"electrode_area_cm2": 2.0})
    base = analyze(table, cfg.model_copy(update={"metadata": meta}))
    h0 = base["selected"]["forward"]["peaks"][0]["height"]
    pending = analyze(table, cfg.model_copy(update={"metadata": meta, "normalize_by_area": True}))
    assert pending["selected"]["forward"]["peaks"][0]["height"] == pytest.approx(h0)
    done = analyze(table, cfg.model_copy(update={"metadata": meta, "normalize_by_area": True,
                                                 "normalize_by_area_confirmed": True}))
    assert done["selected"]["forward"]["peaks"][0]["height"] == pytest.approx(h0 / 2.0)
    assert done["display"]["density"] is True


def test_scan_rate_mismatch_flagged(clear_example):
    raw, cfg = clear_example
    meta = cfg.metadata.model_copy(update={"scan_rate": Quantity(value=5, unit="mV/s")})
    res = analyze(parse_table(raw), cfg.model_copy(update={"metadata": meta}))
    assert "scan_rate_mismatch" in [q["code"] for q in res["quality"]]


def test_clipping_flagged():
    E = np.concatenate([np.arange(0, 1, 0.001), np.arange(1, 0, -0.001)])
    i = 1e-3 * np.sin(np.linspace(0, 2 * math.pi, E.size)) + 2e-3 * np.exp(-((E - 0.5) / 0.05) ** 2) * (np.arange(E.size) < 1000)
    i = np.minimum(i, 1.5e-3)
    t = np.arange(E.size) * 0.01
    res = analyze(parse_table(csv_bytes(t, E, i)), base_config())
    assert "clipping" in [q["code"] for q in res["quality"]]


def test_missing_metadata_reported(clear_example):
    raw, cfg = clear_example
    res = analyze(parse_table(raw), cfg)
    missing = {r["field"] for r in res["metadata_status"] if r["status"] == "missing"}
    assert {"electrode_area", "ph"} <= missing
    assert "electrode_material" not in missing


def test_constant_potential_rejected():
    t = np.arange(100.0)
    raw = csv_bytes(t, np.full(100, 0.5), np.zeros(100))
    with pytest.raises(AnalysisError):
        analyze(parse_table(raw), base_config())


def test_single_sweep_is_not_treated_as_missing_return_peak():
    E = np.arange(0, 1, 0.001)
    i = 1e-4 * np.exp(-((E - 0.5) / 0.05) ** 2)
    t = np.arange(E.size) * 0.01
    res = analyze(parse_table(csv_bytes(t, E, i)), base_config())
    assert res["selected"]["unpaired_forward"] == []
    assert "no_return_sweep" in [q["code"] for q in res["quality"]]
    from benchcheck.reasoning.hypotheses import evaluate
    from benchcheck.reasoning.report import build_report

    assert "irreversible_loss" not in [h["id"] for h in evaluate(res) if h["triggered"]]
    report = build_report({k: v for k, v in res.items() if k != "data"}, {})
    assert report["next_check"]["id"] == "quality_no_return_sweep"


def test_reduction_first_us_convention():
    sim = simulate_reversible(e0=0.25, e_start=-0.05, e_vertex=0.55, scan_rate=0.1)
    # Mirror an oxidation-first CV of R into a reduction-first CV of O (equal D): E' = 2E0 - E, i' = -i.
    E = 0.5 - sim["potential_v"]
    i_iupac = -sim["current_a"]
    raw = csv_bytes(sim["time_s"], E, -i_iupac)  # exported with cathodic currents positive
    meta = {"process_type": "dissolved_species", "scan_rate": {"value": 100, "unit": "mV/s"}}
    res = analyze(parse_table(raw), base_config(metadata=meta, current_convention="cathodic_positive"))
    assert res["forward_direction"] == -1
    pair = res["selected"]["pairs"][0]
    assert res["selected"]["forward"]["peaks"][0]["kind"] == "cathodic"
    assert 0.055 <= pair["delta_ep"] <= 0.062
    assert pair["nicholson_ratio"] == pytest.approx(1.0, abs=0.05)
    assert res["selected"]["forward"]["peaks"][0]["height"] == pytest.approx(sim["randles_sevcik_a"], rel=0.02)
