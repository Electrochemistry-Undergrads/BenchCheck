import numpy as np
import pytest

from benchcheck.cv import peaks as pk


def gaussian(E, center, height, fwhm):
    sigma = fwhm / 2.3548
    return height * np.exp(-0.5 * ((E - center) / sigma) ** 2)


def test_single_peak_on_flat_baseline():
    E = np.arange(0.0, 1.0, 0.001)
    i = 2e-5 + gaussian(E, 0.55, 1e-3, 0.09)
    cands = pk.detect_sweep_peaks(E, i, 1, threshold=1e-5)
    assert len(cands) == 1
    p = cands[0]["local_index"]
    base = pk.prewave_baseline(E, i, i, 1, p, "flat_prewave")
    assert base.method == "flat_prewave"
    assert base.e_to < 0.55 - 0.1  # window ends well before the wave
    peak = pk.build_peaks(E, i, i, 1, cands, base, "forward", 0, 0, tolerance=1e-6)[0]
    assert peak.potential == pytest.approx(0.55, abs=1e-3)
    assert peak.height == pytest.approx(1e-3, rel=1e-3)
    assert peak.width_v == pytest.approx(0.09, rel=0.02)


def test_linear_baseline_recovers_height_on_sloped_background():
    E = np.arange(0.0, 1.0, 0.001)
    background = 1e-4 + 2e-4 * E
    i = background + gaussian(E, 0.6, 1e-3, 0.09)
    cands = pk.detect_sweep_peaks(E, i, 1, threshold=1e-5)
    p = cands[0]["local_index"]
    base = pk.prewave_baseline(E, i, i, 1, p, "linear_prewave")
    peak = pk.build_peaks(E, i, i, 1, cands, base, "forward", 0, 0, tolerance=1e-6)[0]
    assert peak.height == pytest.approx(1e-3, rel=0.01)
    flat = pk.prewave_baseline(E, i, i, 1, p, "flat_prewave")
    flat_peak = pk.build_peaks(E, i, i, 1, cands, flat, "forward", 0, 0, tolerance=1e-6)[0]
    # The flat baseline cannot follow the slope: documented limitation, error bounded here.
    assert abs(flat_peak.height - 1e-3) / 1e-3 < 0.06


def test_negative_going_sweep_finds_cathodic_peak():
    E = np.arange(1.0, 0.0, -0.001)
    i = -3e-5 - gaussian(E, 0.4, 5e-4, 0.1)
    cands = pk.detect_sweep_peaks(E, i, -1, threshold=1e-5)
    p = cands[0]["local_index"]
    base = pk.prewave_baseline(E, i, i, -1, p)
    peak = pk.build_peaks(E, i, i, -1, cands, base, "return", 1, 0, tolerance=1e-6)[0]
    assert peak.kind == "cathodic"
    assert peak.potential == pytest.approx(0.4, abs=1e-3)
    assert peak.height == pytest.approx(5e-4, rel=1e-3)


def test_overlapping_peaks_both_found_and_width_flagged():
    E = np.arange(0.0, 1.2, 0.001)
    i = gaussian(E, 0.6, 1e-3, 0.12) + gaussian(E, 0.75, 0.8e-3, 0.12)
    cands = pk.detect_sweep_peaks(E, i, 1, threshold=1e-5)
    assert len(cands) == 2
    first = min(cands, key=lambda c: c["local_index"])["local_index"]
    base = pk.prewave_baseline(E, i, i, 1, first)
    found = pk.build_peaks(E, i, i, 1, cands, base, "forward", 0, 0, tolerance=1e-6)
    assert sorted(round(p.potential, 2) for p in found) == [0.6, 0.75]
    assert any(p.width_v is None for p in found)  # half height not reached between the peaks


def test_peak_near_edge_is_not_reported_from_vertex_current():
    E = np.arange(0.0, 1.0, 0.001)
    i = 1e-5 * np.exp((E - 0.9) / 0.05)  # monotonically rising toward the vertex, no peak
    assert pk.detect_sweep_peaks(E, i, 1, threshold=1e-6) == []
    v = pk.vertex_behavior(E, i, 1, [], reference_height=1e-4, rise_fraction_threshold=0.15)
    assert v["rising"] is True


def test_order_preserving_pairing_beats_greedy():
    def P(label, e):
        return pk.Peak(label, "x", "x", 0, 0, e, 0, 0, 0, 1, 1, None, False)

    forward = [P("A1", 0.85), P("A2", 1.00)]
    ret = [P("C1", 0.65), P("C2", 0.80)]
    pairs, uf, ur = pk.pair_peaks(forward, ret)
    assert [(a.label, b.label) for a, b in pairs] == [("A1", "C1"), ("A2", "C2")]
    assert uf == [] and ur == []


def test_pairing_leaves_unmatched_peaks():
    def P(label, e):
        return pk.Peak(label, "x", "x", 0, 0, e, 0, 0, 0, 1, 1, None, False)

    pairs, uf, ur = pk.pair_peaks([P("A1", 0.5), P("A2", 1.4)], [P("C1", 0.45)])
    assert [(a.label, b.label) for a, b in pairs] == [("A1", "C1")]
    assert [p.label for p in uf] == ["A2"]


def test_nicholson_ratio_formula():
    # (i_pr)0/i_pf + 0.485 (i_sp)0/i_pf + 0.086
    assert pk.nicholson_ratio(1.0, 0.5, 0.6) == pytest.approx(0.5 + 0.485 * 0.6 + 0.086)
    assert pk.nicholson_ratio(0.0, 0.5, 0.6) is None


def test_sweep_charge_constant_current():
    E = np.linspace(0, 1, 101)
    i = np.full(101, 2e-3)
    q_time, basis = pk.sweep_charge(i, np.linspace(0, 10, 101), E, None)
    assert q_time == pytest.approx(2e-2) and basis == "time column"
    q_rate, basis = pk.sweep_charge(i, None, E, 0.1)  # 1 V at 0.1 V/s = 10 s
    assert q_rate == pytest.approx(2e-2) and "scan rate" in basis
    assert pk.sweep_charge(i, None, E, None) == (None, None)


def test_smoothing_window_sizes():
    assert pk.smoothing_window(0.001, 0.010, 1000) == 11
    assert pk.smoothing_window(0.001, 0.0, 1000) == 1
    assert pk.smoothing_window(0.005, 0.010, 1000) == 5
    assert pk.smoothing_window(0.001, 0.010, 20) == 5
