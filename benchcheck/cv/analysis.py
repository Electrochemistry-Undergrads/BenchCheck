"""End-to-end numerical analysis of one cyclic voltammogram.

Everything here is deterministic numerical code. Each processing step that
changes numbers (unit conversion, sign convention, normalization, reference
conversion, smoothing, baseline) is recorded in `processing` so it can be
disclosed next to the results. The uploaded values themselves are preserved
and returned for plotting.
"""

from __future__ import annotations

import math

import numpy as np

from ..models import AnalysisConfig
from . import peaks as pk
from .metadata import metadata_status, scan_rate_v_s
from .parsing import ParsedTable
from .reference import plan_conversion, reference_label
from .segmentation import Segment, assign_cycles, default_cycle, detect_forward_direction, segment_scan
from .units import (
    display_charge_unit,
    display_current_unit,
    fmt_current,
    fmt_mv,
    fmt_potential,
    fmt_scan_rate,
    fmt_sig,
    is_current_density,
    label,
    normalize_unit,
    to_base,
)

SCAN_RATE_TOLERANCE = 0.10  # relative mismatch between entered and measured scan rate
VERTEX_RISE_FRACTION = 0.15  # vertex rise (fraction of the largest peak height) counted as "rising"
CLIPPING_RUN = 5
COARSE_STEP_V = 0.005
NOISE_FRACTION_WARN = 0.05
TREND_MATCH_V = 0.05


class AnalysisError(ValueError):
    pass


def _clean(obj):
    """Make results JSON-safe: numpy scalars to Python, NaN/inf to None."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_clean(v) for v in obj.tolist()]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _prepare(table: ParsedTable, config: AnalysisConfig, processing: list[dict], notices: list[str]):
    m = config.mapping
    try:
        e_unit = normalize_unit(config.units.potential)
        i_unit = normalize_unit(config.units.current)
        t_unit = normalize_unit(config.units.time) if m.time else None
    except ValueError as exc:
        raise AnalysisError(str(exc)) from exc
    E_col = table.column(m.potential)
    i_col = table.column(m.current)
    t_col = table.column(m.time) if m.time else None

    mask = np.isfinite(E_col) & np.isfinite(i_col)
    if t_col is not None:
        mask &= np.isfinite(t_col)
    dropped = int(mask.size - mask.sum())
    if mask.sum() < 10:
        raise AnalysisError("Fewer than 10 rows contain numeric potential and current values.")

    E = to_base(E_col[mask], e_unit, "potential")
    i = to_base(i_col[mask], i_unit, "current")
    t = to_base(t_col[mask], t_unit, "time") if t_col is not None else None
    density = is_current_density(i_unit)

    cols = f"potential = '{m.potential}' ({label(e_unit)}), current = '{m.current}' ({label(i_unit)})"
    if m.time:
        cols += f", time = '{m.time}' ({label(t_unit)})"
    processing.append({"step": "Column mapping (user-confirmed)", "detail": cols + "."})
    processing.append({
        "step": "Unit conversion",
        "detail": f"Potential ×{1.0 if e_unit == 'V' else 1e-3:g} → V; current converted from "
                  f"{label(i_unit)} to {'A cm⁻²' if density else 'A'}"
                  + (f"; time from {label(t_unit)} to s." if m.time else "."),
    })
    if dropped:
        processing.append({"step": "Rows excluded", "detail": f"{dropped} row(s) without numeric values in the mapped columns."})
    if t is not None and np.any(np.diff(t) < 0):
        notices.append("The time column is not monotonic (concatenated files?). Measured scan rates may be unreliable.")

    if config.current_convention == "cathodic_positive":
        i = -i
        processing.append({
            "step": "Current sign convention (user-selected)",
            "detail": "Data recorded with cathodic currents positive (US/polarographic convention); "
                      "signs inverted so anodic currents are positive (IUPAC).",
        })

    meta = config.metadata
    if config.normalize_by_area:
        area = meta.electrode_area_cm2
        if density:
            notices.append("Current is already a current density; area normalization not applied.")
        elif not area or area <= 0:
            notices.append("Area normalization requested but no electrode area was entered; not applied.")
        elif not config.normalize_by_area_confirmed:
            notices.append("Area normalization requires confirmation; not applied.")
        else:
            i = i / area
            density = True
            processing.append({
                "step": "Normalization by electrode area (user-confirmed)",
                "detail": f"Currents divided by {area:g} cm² (user-entered). For porous or composite electrodes the "
                          "electrochemically active area can differ from this value.",
            })

    ref_label = reference_label(meta.reference_electrode, meta.reference_detail) if meta.reference_electrode else None
    scale = {"label": f"V vs {ref_label}" if ref_label else "V vs (reference not specified)", "converted": False}
    rc = config.reference_conversion
    if rc is not None:
        plan = plan_conversion(meta.reference_electrode, rc.target, meta.ph, meta.temperature_c, rc.offset_v, rc.description)
        if not plan.get("possible"):
            notices.append(f"Reference conversion not applied: {plan.get('reason')}")
        elif not rc.confirmed:
            notices.append("Reference conversion requires confirmation; potentials are shown as recorded.")
        else:
            E = E + plan["offset_v"]
            scale = {"label": f"V vs {plan['to_label']}", "converted": True, "offset_v": plan["offset_v"],
                     "from": ref_label, "explanation": plan["explanation"], "caveats": plan["caveats"]}
            processing.append({
                "step": "Reference-scale conversion (user-confirmed)",
                "detail": f"{plan['explanation']} {' '.join(plan['caveats'])}",
            })
    return E, i, t, density, scale, dropped


def _sweep_info(seg: Segment) -> dict:
    return {
        "segment": seg.index,
        "direction": seg.direction,
        "direction_label": seg.direction_label,
        "e_start": seg.e_start,
        "e_end": seg.e_end,
        "start_index": seg.start,
        "end_index": seg.end,
        "partial": seg.partial,
        "scan_rate_measured": seg.scan_rate_measured,
    }


def _analyze_sweep(seg, role, E, i, i_s, t, scan_rate, threshold, baseline_method, noise, half_width_hint=None):
    a, b = seg.start, seg.end + 1
    Es, Is, Ss = E[a:b], i[a:b], i_s[a:b]
    candidates = pk.detect_sweep_peaks(Es, Ss, seg.direction, threshold)
    first = min(candidates, key=lambda c: c["local_index"]) if candidates else None
    baseline = pk.prewave_baseline(
        Es, Is, Ss, seg.direction, first["local_index"] if first else None, baseline_method, half_width_hint
    )
    tolerance = max(3.0 * noise, 0.02 * max((c["prominence"] for c in candidates), default=0.0))
    found = pk.build_peaks(Es, Is, Ss, seg.direction, candidates, baseline, role, seg.index, a, tolerance)
    heights = [p.height for p in found if p.height > 0]
    ref_height = max(heights) if heights else float(np.ptp(Ss))
    vertex = pk.vertex_behavior(Es, Ss, seg.direction, [p.index - a for p in found], ref_height, VERTEX_RISE_FRACTION)
    t_seg = t[a:b] if t is not None else None
    charge, basis = pk.sweep_charge(Is, t_seg, Es, scan_rate)
    info = _sweep_info(seg)
    info.update({"baseline": baseline.to_dict(), "peaks": found, "vertex": vertex, "charge": charge, "charge_basis": basis})
    return info


def _label_peaks(sweeps: list[dict]) -> None:
    for kind, prefix in (("anodic", "A"), ("cathodic", "C")):
        allp = [p for s in sweeps for p in s["peaks"] if p.kind == kind]
        for n, p in enumerate(sorted(allp, key=lambda p: p.potential), start=1):
            p.label = f"{prefix}{n}"


def _cycle_features(cycle, segments, E, i, i_s, t, scan_rate, noise, process_type, baseline_method):
    seg_f = segments[cycle.forward] if cycle.forward is not None else None
    seg_r = segments[cycle.reverse] if cycle.reverse is not None else None
    idx = [s for s in (seg_f, seg_r) if s is not None]
    lo, hi = min(s.start for s in idx), max(s.end for s in idx) + 1
    span = float(np.ptp(i_s[lo:hi])) if hi - lo > 1 else 0.0
    threshold = max(pk.PROMINENCE_NOISE_MULTIPLE * noise, pk.PROMINENCE_SPAN_FRACTION * span, 1e-15)

    fwd = _analyze_sweep(seg_f, "forward", E, i, i_s, t, scan_rate, threshold, baseline_method, noise) if seg_f else None
    hint = fwd["baseline"].get("onset_half_width_v") if fwd else None
    ret = (
        _analyze_sweep(seg_r, "return", E, i, i_s, t, scan_rate, threshold, baseline_method, noise, hint)
        if seg_r else None
    )
    _label_peaks([s for s in (fwd, ret) if s])

    pairs, unpaired_f, unpaired_r = ([], fwd["peaks"] if fwd else [], ret["peaks"] if ret else [])
    if fwd and ret:
        pairs, unpaired_f, unpaired_r = pk.pair_peaks(fwd["peaks"], ret["peaks"])
    pair_rows = []
    for pf, pr in pairs:
        anodic, cathodic = (pf, pr) if pf.kind == "anodic" else (pr, pf)
        row = {
            "forward": pf.label,
            "return": pr.label,
            "anodic": anodic.label,
            "cathodic": cathodic.label,
            "delta_ep": anodic.potential - cathodic.potential,
            "e_mid": 0.5 * (anodic.potential + cathodic.potential),
            "height_ratio": pr.height / pf.height if pf.height > 0 else None,
            "width_ratio": (pr.width_v / pf.width_v) if pf.width_v and pr.width_v else None,
            "nicholson_ratio": None,
        }
        if process_type == "dissolved_species" and pf.height > 0:
            i_r0 = seg_r.direction * i_s[pr.index]
            i_sp0 = seg_f.direction * i_s[seg_f.end]
            row["nicholson_ratio"] = pk.nicholson_ratio(pf.height, float(i_r0), float(i_sp0))
            row["nicholson_inputs"] = {"i_forward": pf.height, "i_return_from_zero": float(i_r0), "i_switch_from_zero": float(i_sp0)}
        pair_rows.append(row)

    charge_ratio = None
    if fwd and ret and fwd["charge"] and ret["charge"] is not None and fwd["charge"] != 0:
        charge_ratio = -ret["charge"] / fwd["charge"]

    main_f = None
    if fwd and fwd["peaks"]:
        main_f = max(fwd["peaks"], key=lambda p: (p.height if p.height > 0 else 0.0, p.prominence))
    main_pair = next((k for k, r in enumerate(pair_rows) if main_f and r["forward"] == main_f.label), None)

    def sweep_out(s):
        if s is None:
            return None
        out = dict(s)
        out["peaks"] = [p.to_dict() for p in s["peaks"]]
        return out

    return {
        "number": cycle.number,
        "complete": cycle.complete,
        "forward": sweep_out(fwd),
        "return": sweep_out(ret),
        "pairs": pair_rows,
        "unpaired_forward": [p.label for p in unpaired_f],
        "unpaired_return": [p.label for p in unpaired_r],
        "charge_ratio": charge_ratio,
        "main_forward_peak": main_f.label if main_f else None,
        "main_pair": main_pair,
        "threshold": threshold,
        "current_span": span,
    }


def _trends(cycle_feats: list[dict], selected: dict | None) -> dict | None:
    usable = [c for c in cycle_feats if c["complete"] and c["forward"] and c["forward"]["peaks"]]
    if len(usable) < 2 or selected is None or not selected.get("main_forward_peak"):
        return None
    ref = next(p for p in selected["forward"]["peaks"] if p["label"] == selected["main_forward_peak"])
    rows = []
    for c in usable:
        near = [p for p in c["forward"]["peaks"] if abs(p["potential"] - ref["potential"]) <= TREND_MATCH_V]
        if not near:
            rows.append({"number": c["number"], "found": False})
            continue
        p = min(near, key=lambda p: abs(p["potential"] - ref["potential"]))
        pair = next((r for r in c["pairs"] if r["forward"] == p["label"]), None)
        rows.append({
            "number": c["number"], "found": True, "label": p["label"], "potential": p["potential"], "height": p["height"],
            "height_ratio": pair["height_ratio"] if pair else None, "e_mid": pair["e_mid"] if pair else None,
            "charge_ratio": c["charge_ratio"],
        })
    found = [r for r in rows if r["found"] and r["height"] and r["height"] > 0]
    if len(found) < 2:
        return {"cycles": rows, "n_cycles": len(rows)}
    first, last = found[0], found[-1]
    change = (last["height"] - first["height"]) / first["height"] * 100.0
    mids = [r["e_mid"] for r in found if r["e_mid"] is not None]
    return {
        "cycles": rows,
        "n_cycles": len(found),
        "tracked_peak_potential": ref["potential"],
        "first_cycle": first["number"],
        "last_cycle": last["number"],
        "height_change_pct": change,
        "per_cycle_pct": change / (last["number"] - first["number"]) if last["number"] != first["number"] else None,
        "potential_shift": last["potential"] - first["potential"],
        "e_mid_shift": (mids[-1] - mids[0]) if len(mids) >= 2 else None,
    }


def _clipping(i: np.ndarray) -> dict | None:
    for sign in (1, -1):
        y = sign * i
        top = float(np.max(y))
        if top <= 0:
            continue
        at_top = np.isclose(y, top, rtol=1e-9, atol=0.0)
        run = best = 0
        for flag in at_top:
            run = run + 1 if flag else 0
            best = max(best, run)
        if best >= CLIPPING_RUN:
            return {"value": sign * top, "run_points": int(best)}
    return None


def _quality(E, i, i_s, t, segments, cycles, cycle_feats, selected, noise, meta_rate, measured_rate, density, scale):
    flags = []

    def add(code, severity, message):
        flags.append({"code": code, "severity": severity, "message": message})

    clip = _clipping(i)
    if clip:
        unit, sc = display_current_unit(abs(clip["value"]), density)
        add("clipping", "high",
            f"{clip['run_points']} consecutive points sit at exactly {fmt_current(clip['value'], unit, sc)}: "
            "the current may have hit the potentiostat's current-range limit (clipping). "
            "Peak heights near that value are unreliable.")
    if meta_rate is not None and measured_rate is not None:
        rel = abs(measured_rate - meta_rate) / meta_rate
        if rel > SCAN_RATE_TOLERANCE:
            add("scan_rate_mismatch", "high",
                f"The time column gives {fmt_scan_rate(measured_rate)}, but {fmt_scan_rate(meta_rate)} was entered "
                f"({rel * 100:.0f}% difference). Check the instrument setting and the metadata.")
    r2 = [s.scan_rate_r2 for s in segments if s.scan_rate_r2 is not None and not s.trivial]
    if r2 and min(r2) < 0.995:
        add("scan_rate_nonlinear", "warning",
            f"Potential vs time is not linear within at least one sweep (R² = {min(r2):.3f}); "
            "the scan rate may not have been constant.")
    step = pk.median_step(E)
    if step > COARSE_STEP_V:
        add("coarse_steps", "info", f"Potential step is {step * 1e3:.1f} mV; peak potentials are uncertain by about ±{step * 5e2:.1f} mV.")
    if selected and selected.get("forward"):
        heights = [p["height"] for p in selected["forward"]["peaks"] if p["height"] > 0]
        if heights and noise / max(heights) > NOISE_FRACTION_WARN:
            add("noisy", "warning",
                f"Noise (robust σ) is {noise / max(heights) * 100:.0f}% of the largest forward peak height; "
                "small features may not be resolvable.")
        if not selected["forward"]["peaks"]:
            add("no_forward_peak", "warning", "No peak was detected on the forward sweep of the analyzed cycle.")
    complete = [c for c in cycles if c.complete]
    if len(complete) < 2:
        add("single_cycle", "info", "Fewer than two complete cycles: cycle-to-cycle stability cannot be assessed.")
    pos = [s for s in segments if s.direction > 0 and not s.trivial]
    neg = [s for s in segments if s.direction < 0 and not s.trivial]
    if pos and neg:
        mean_pos = float(np.mean(np.concatenate([i[s.start:s.end + 1] for s in pos])))
        mean_neg = float(np.mean(np.concatenate([i[s.start:s.end + 1] for s in neg])))
        spread = float(np.ptp(i)) or 1.0
        if mean_pos - mean_neg < -0.05 * spread:
            add("sign_convention_hint", "warning",
                "Currents on positive-going sweeps are on average lower than on negative-going sweeps. In the IUPAC "
                "convention (anodic positive) the opposite is expected, so the file may use the cathodic-positive "
                "convention. Check the current sign setting.")
    short = [s for s in segments if not s.trivial and s.n_points < 50]
    if short:
        add("few_points", "warning", f"{len(short)} sweep(s) have fewer than 50 points; peak positions are imprecise.")
    if scale.get("converted"):
        add("converted_scale", "info", f"Potentials shown on a converted scale ({scale['label']}).")
    return flags


def _observations(selected, trends, density, scale, scan_rate_entered, measured_rate, process_type):
    if selected is None:
        return []
    obs = []
    max_abs = 0.0
    for key in ("forward", "return"):
        s = selected.get(key)
        if s:
            for p in s["peaks"]:
                max_abs = max(max_abs, abs(p["current"]), abs(p["height"]))
    unit, sc = display_current_unit(max_abs or 1e-3, density)
    ref = scale["label"]

    def cur(x):
        return fmt_current(x, unit, sc, signed=False)

    fwd, ret = selected.get("forward"), selected.get("return")
    if fwd:
        desc = (f"Cycle {selected['number']}: forward sweep is {fwd['direction_label']} from "
                f"{fmt_potential(fwd['e_start'])} to {fmt_potential(fwd['e_end'])}")
        if ret:
            desc += f", return sweep back to {fmt_potential(ret['e_end'])}"
        obs.append({"id": "cycle", "text": desc + f"; potentials in {ref}."})
    for key, name in (("forward", "Forward"), ("return", "Return")):
        s = selected.get(key)
        if not s:
            continue
        if s["peaks"]:
            parts = [f"{p['label']} at {fmt_potential(p['potential'])} (height {cur(p['height'])} above baseline)" for p in
                     sorted(s["peaks"], key=lambda p: p["potential"])]
            kind = s["peaks"][0]["kind"]
            obs.append({"id": f"{key}_peaks", "text": f"{name} sweep: {len(parts)} {kind} peak(s) detected: " + "; ".join(parts) + "."})
        else:
            obs.append({"id": f"{key}_peaks", "text": f"{name} sweep: no peak above the detection threshold "
                                                       f"({cur(selected['threshold'])} prominence)."})
    for k, r in enumerate(selected["pairs"]):
        text = (f"Candidate pair {r['anodic']}/{r['cathodic']} (paired by potential, not a mechanistic assignment): "
                f"ΔEp = {fmt_mv(r['delta_ep'])}, midpoint {fmt_potential(r['e_mid'])}")
        if r["height_ratio"] is not None:
            text += f", return/forward peak-height ratio {r['height_ratio']:.2f}"
        if r.get("nicholson_ratio") is not None:
            text += f" (Nicholson estimate {r['nicholson_ratio']:.2f})"
        if r.get("width_ratio") is not None:
            text += f", return/forward peak-width ratio {r['width_ratio']:.2f}"
        obs.append({"id": f"pair_{k}", "text": text + "."})
    if selected["unpaired_forward"]:
        obs.append({"id": "unpaired_forward", "text": "No return peak detected for forward peak(s) "
                                                      + ", ".join(selected["unpaired_forward"]) + "."})
    if selected["charge_ratio"] is not None and fwd and ret:
        cu, csc = display_charge_unit(max(abs(fwd["charge"]), abs(ret["charge"])))
        dens = " cm⁻²" if density else ""
        obs.append({"id": "charge", "text": (
            f"Net charge: forward sweep {fmt_sig(fwd['charge'] * csc)} {cu}{dens}, return sweep "
            f"{fmt_sig(ret['charge'] * csc)} {cu}{dens}; return/forward charge ratio {selected['charge_ratio']:.2f} "
            f"(integrated using the {fwd['charge_basis']}).")})
    for key, name in (("forward", "forward"), ("return", "return")):
        s = selected.get(key)
        v = s.get("vertex") if s else None
        if v and v["rising"]:
            obs.append({"id": f"{key}_vertex_rising", "text": (
                f"At the end of the {name} sweep ({fmt_potential(v['potential'])}) the current magnitude is still "
                f"increasing: it rises {cur(v['rise'])} over the post-peak minimum "
                f"({v['rise_fraction'] * 100:.0f}% of the largest peak height on that sweep).")})
    if trends and trends.get("height_change_pct") is not None:
        obs.append({"id": "trend", "text": (
            f"Across complete cycles {trends['first_cycle']}–{trends['last_cycle']}, the forward peak near "
            f"{fmt_potential(trends['tracked_peak_potential'])} changed in height by {trends['height_change_pct']:+.0f}% "
            f"and shifted by {trends['potential_shift'] * 1e3:+.0f} mV.")})
    if measured_rate is not None:
        txt = f"Scan rate from the time column: {fmt_scan_rate(measured_rate)}"
        if scan_rate_entered is not None:
            txt += f" (entered: {fmt_scan_rate(scan_rate_entered)})"
        obs.append({"id": "scan_rate", "text": txt + "."})
    return obs


def analyze(table: ParsedTable, config: AnalysisConfig) -> dict:
    processing: list[dict] = []
    notices: list[str] = []
    meta = config.metadata
    E, i, t, density, scale, dropped = _prepare(table, config, processing, notices)

    try:
        segments, seg_id = segment_scan(E, t)
    except ValueError as exc:
        raise AnalysisError(str(exc)) from exc
    if config.forward_direction == "positive":
        forward_dir, fwd_basis = 1, "user-selected"
    elif config.forward_direction == "negative":
        forward_dir, fwd_basis = -1, "user-selected"
    else:
        forward_dir, fwd_basis = detect_forward_direction(segments), "auto-detected from the first full-range sweep"
    cycles, leading = assign_cycles(segments, forward_dir)
    if not cycles:
        raise AnalysisError("No sweep in the forward direction was found; check the potential column.")
    processing.append({
        "step": "Scan segmentation",
        "detail": f"{len([s for s in segments if not s.trivial])} sweep(s) found from scan reversals; forward direction "
                  f"{'positive-going' if forward_dir > 0 else 'negative-going'} ({fwd_basis}). Cycle k = k-th forward "
                  "sweep + the following return sweep.",
    })

    step = pk.median_step(E)
    i_s = i.copy()
    windows = []
    for seg in segments:
        a, b = seg.start, seg.end + 1
        w = pk.smoothing_window(step, config.processing.smoothing_mv / 1000.0, b - a)
        windows.append(w)
        i_s[a:b] = pk.smooth(i[a:b], w)
    noise = pk.robust_noise(i, i_s)
    main_w = max(set(windows), key=windows.count) if windows else 1
    if main_w >= 5:
        processing.append({
            "step": "Smoothing (for peak location only)",
            "detail": f"Savitzky–Golay filter, {main_w}-point window (≈{main_w * step * 1e3:.0f} mV), polynomial order "
                      f"{pk.SAVGOL_POLYORDER}, applied within each sweep. Peak potentials and currents are read from the "
                      "smoothed curve; raw data are unchanged and plotted.",
        })
    else:
        processing.append({"step": "Smoothing", "detail": "None. Peak values are read from the raw data."})
    baseline_method = config.processing.baseline
    processing.append({
        "step": "Baseline for peak heights",
        "detail": {
            "flat_prewave": "Flat baseline per sweep: mean current over the 50 mV just before the first wave starts "
                            "(three leading half-widths before the first peak). Approximates the capacitive/background "
                            "current; all peaks on the sweep are measured from it.",
            "linear_prewave": "Straight line fitted to up to 150 mV of the pre-wave region of each sweep and extrapolated "
                              "under the peaks. Extrapolation errors grow with distance from the fit window.",
            "zero": "None: peak heights measured from zero current.",
        }[baseline_method],
    })

    scan_rate = scan_rate_v_s(meta)
    measured = [s.scan_rate_measured for s in segments if s.scan_rate_measured and not s.trivial]
    measured_rate = float(np.median(measured)) if measured else None
    rate_for_charge = measured_rate or scan_rate

    cycle_feats = [
        _cycle_features(c, segments, E, i, i_s, t, rate_for_charge, noise, meta.process_type, baseline_method)
        for c in cycles
    ]
    processing.append({
        "step": "Peak detection",
        "detail": f"Local extrema with prominence ≥ max({pk.PROMINENCE_NOISE_MULTIPLE:g}× noise σ, "
                  f"{pk.PROMINENCE_SPAN_FRACTION * 100:g}% of the cycle's current range) and width ≥ "
                  f"{pk.MIN_PEAK_WIDTH_V * 1e3:g} mV; only peaks of the sign expected for each sweep.",
    })

    selected_no = config.selected_cycle or default_cycle(cycles)
    if selected_no not in [c.number for c in cycles]:
        notices.append(f"Cycle {config.selected_cycle} does not exist; using cycle {default_cycle(cycles)}.")
        selected_no = default_cycle(cycles)
    selected = next((c for c in cycle_feats if c["number"] == selected_no), None)
    trends = _trends(cycle_feats, selected)
    quality = _quality(E, i, i_s, t, segments, cycles, cycle_feats, selected, noise, scan_rate, measured_rate, density, scale)
    observations = _observations(selected, trends, density, scale, scan_rate, measured_rate, meta.process_type)

    point_cycle = np.zeros(E.size, dtype=int)
    for c in cycles:
        for sid in (c.forward, c.reverse):
            if sid is not None:
                s = segments[sid]
                point_cycle[s.start:s.end + 1] = c.number

    max_abs = float(np.max(np.abs(i))) if i.size else 0.0
    unit, sc = display_current_unit(max_abs, density)
    result = {
        "provenance": table.summary(),
        "rows_used": int(E.size),
        "rows_excluded": dropped,
        "display": {
            "current_unit": unit,
            "current_label": label(unit),
            "current_scale": sc,
            "potential_label": scale["label"],
            "density": density,
        },
        "potential_scale": scale,
        "processing": processing,
        "notices": notices,
        "noise_sigma": noise,
        "potential_step": step,
        "data": {
            "E": E, "i": i, "i_smooth": i_s, "t": t if t is not None else None,
            "segment": seg_id, "cycle": point_cycle,
        },
        "segments": [s.to_dict() for s in segments],
        "forward_direction": forward_dir,
        "cycles": cycle_feats,
        "cycle_list": [c.to_dict() for c in cycles],
        "leading_segments": leading,
        "selected_cycle": selected_no,
        "selected": selected,
        "trends": trends,
        "quality": quality,
        "observations": observations,
        "metadata": meta.model_dump(),
        "metadata_status": metadata_status(meta, measured_rate),
        "scan_rate_entered": scan_rate,
        "scan_rate_measured": measured_rate,
        "example_id": config.example_id,
    }
    return _clean(result)
