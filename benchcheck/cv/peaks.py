"""Peak detection, baselines and peak pairing on individual sweeps.

Peaks are *located* on a Savitzky–Golay-smoothed copy of the current; the raw
data are never modified and the smoothing settings are disclosed with every
result. On each sweep BenchCheck looks only for peaks of the sign expected for
that sweep: anodic (positive, IUPAC convention) peaks on positive-going sweeps
and cathodic (negative) peaks on negative-going sweeps.

Peak heights are measured from a straight baseline fitted to the pre-wave part
of the same sweep (before the first peak) and extrapolated under the peaks. This
is a common approximation; for dissolved species on the return sweep the true
baseline is the decaying forward current, so BenchCheck additionally reports
Nicholson's (1966) vertex-current estimate of the peak current ratio.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.integrate import trapezoid
from scipy.signal import find_peaks, savgol_filter

PROMINENCE_NOISE_MULTIPLE = 6.0
PROMINENCE_SPAN_FRACTION = 0.03
MIN_PEAK_WIDTH_V = 0.005
SAVGOL_POLYORDER = 2
VERTEX_WINDOW_V = 0.030
PAIR_MAX_SEPARATION_V = 0.5
# Nicholson, Anal. Chem. 1966, 38, 1406: ratio = (i_pr)0/i_pf + 0.485 (i_sp)0/i_pf + 0.086
NICHOLSON_A = 0.485
NICHOLSON_B = 0.086


@dataclass
class Baseline:
    method: str  # "linear_prewave" or "zero"
    slope: float  # A per V
    intercept: float  # A
    e_from: float | None
    e_to: float | None
    n_points: int
    note: str | None = None
    onset_half_width_v: float | None = None
    half_width_source: str | None = None

    def at(self, e: float) -> float:
        return self.intercept + self.slope * e

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Peak:
    label: str
    kind: str  # "anodic" | "cathodic"
    sweep: str  # "forward" | "return"
    segment: int
    index: int  # index into the full data arrays
    potential: float  # V
    current: float  # smoothed current at the peak, A (signed, IUPAC)
    current_raw: float  # raw current at the same point
    baseline_current: float
    height: float  # (current - baseline) in the expected direction; > 0 for a real peak
    prominence: float
    width_v: float | None  # full width at half prominence
    near_vertex: bool

    def to_dict(self) -> dict:
        return asdict(self)


def median_step(E: np.ndarray) -> float:
    steps = np.abs(np.diff(E))
    steps = steps[steps > 0]
    return float(np.median(steps)) if steps.size else 0.0


def smoothing_window(step_v: float, smoothing_v: float, n_points: int) -> int:
    """Odd Savitzky–Golay window (points) spanning roughly `smoothing_v` volts; 1 = off."""
    if smoothing_v <= 0 or step_v <= 0 or n_points < 7:
        return 1
    w = int(round(smoothing_v / step_v))
    if w % 2 == 0:
        w += 1
    w = max(w, 5)
    cap = max(5, (n_points // 4) | 1)
    w = min(w, cap)
    return w if w >= 5 else 1


def smooth(i: np.ndarray, window: int) -> np.ndarray:
    if window < 5 or i.size < window:
        return i.copy()
    return savgol_filter(i, window, SAVGOL_POLYORDER, mode="interp")


def robust_noise(i: np.ndarray, i_smooth: np.ndarray) -> float:
    resid = i - i_smooth
    mad = float(np.median(np.abs(resid - np.median(resid))))
    return 1.4826 * mad


BASELINE_WINDOW_V = 0.050
LINEAR_FIT_MAX_V = 0.150
ONSET_SEARCH_V = 0.250
HALF_WIDTH_BOUNDS_V = (0.015, 0.100)


def leading_half_width(E: np.ndarray, y: np.ndarray, p: int, direction: int) -> float | None:
    """Distance (V) from the leading-edge half-height point to peak p.

    Half height is measured above the lowest point within 250 mV before the peak,
    which approximates the foot of the wave without assuming a baseline.
    """
    if p < 2:
        return None
    s = direction * (E - E[0])
    window = (s >= s[p] - ONSET_SEARCH_V) & (np.arange(E.size) < p)
    if window.sum() < 2:
        return None
    base = float(np.min(y[window]))
    target = base + 0.5 * (y[p] - base)
    k = p
    while k > 0 and y[k] > target:
        k -= 1
    if y[k] > target or y[k + 1] == y[k]:
        return None
    frac = (target - y[k]) / (y[k + 1] - y[k])
    e_cross = E[k] + frac * (E[k + 1] - E[k])
    return float(abs(E[p] - e_cross))


def prewave_baseline(
    E: np.ndarray,
    i_raw: np.ndarray,
    i_s: np.ndarray,
    direction: int,
    first_peak: int | None,
    method: str = "flat_prewave",
    half_width_hint: float | None = None,
) -> Baseline:
    """Baseline for peak heights on one sweep, from the region just before its first wave.

    The wave is assumed not to have started three leading half-widths before the
    first peak. The half-width comes from `half_width_hint` (BenchCheck passes the
    forward sweep's value to the return sweep, whose foot is often distorted by
    the decaying forward or side current) or is measured on this sweep, and is
    clamped to 15-100 mV. `flat_prewave` uses the mean current over the 50 mV
    before that point; `linear_prewave` fits a straight line over up to 150 mV
    before it and extrapolates under the peaks. The first 10 mV (and 3 % of the
    points) of the sweep are skipped to avoid the reversal transient.
    """
    zero = Baseline("zero", 0.0, 0.0, None, None, 0)
    if method == "zero":
        zero.note = "Peak heights measured from zero current (no baseline subtraction)."
        return zero
    n = E.size
    if first_peak is None or n < 10:
        zero.note = "No peak on this sweep; no baseline fitted."
        return zero
    if half_width_hint is not None:
        half_width, source = half_width_hint, "forward sweep's first peak"
    else:
        half_width = leading_half_width(E, direction * i_s, first_peak, direction)
        source = "this sweep's first peak"
    if half_width is None:
        zero.note = "Could not locate the foot of the first wave; peak heights on this sweep are measured from zero current."
        return zero
    half_width = float(min(max(half_width, HALF_WIDTH_BOUNDS_V[0]), HALF_WIDTH_BOUNDS_V[1]))
    s = direction * (E - E[0])
    s_stop = s[first_peak] - 3.0 * half_width
    span = BASELINE_WINDOW_V if method == "flat_prewave" else LINEAR_FIT_MAX_V
    valid = (s >= 0.010) & (np.arange(n) >= max(1, int(0.03 * n))) & (np.arange(n) < first_peak)
    mask = valid & (s <= s_stop) & (s >= s_stop - span)
    pts = np.flatnonzero(mask)
    if pts.size < 5:
        zero.note = (
            "Pre-wave region too short (the first wave starts close to the start of the sweep); "
            "peak heights on this sweep are measured from zero current."
        )
        return zero
    e_from, e_to = float(E[pts[0]]), float(E[pts[-1]])
    if method == "linear_prewave":
        if abs(e_to - e_from) < 0.015:
            zero.note = "Pre-wave region too short for a linear fit; peak heights measured from zero current."
            return zero
        slope, intercept = np.polyfit(E[pts], i_raw[pts], 1)
        return Baseline("linear_prewave", float(slope), float(intercept), e_from, e_to, int(pts.size),
                        onset_half_width_v=half_width, half_width_source=source)
    return Baseline("flat_prewave", 0.0, float(np.mean(i_raw[pts])), e_from, e_to, int(pts.size),
                    onset_half_width_v=half_width, half_width_source=source)


def fwhm_above_baseline(E: np.ndarray, y_corr: np.ndarray, p: int, tolerance: float) -> tuple[float | None, bool]:
    """Full width at half height above the baseline. Returns (width, resolved).

    If the curve turns upward again (a valley deeper than `tolerance`) before reaching
    half height on either side, the peak overlaps a neighbour and the width is
    reported as unresolved (None).
    """
    h = y_corr[p]
    if h <= 0:
        return None, False
    half = 0.5 * h
    edges = []
    for step in (-1, 1):
        k = p
        running_min = h
        edge = None
        while 0 <= k + step < y_corr.size:
            nxt = k + step
            if y_corr[nxt] <= half:
                frac = (y_corr[k] - half) / (y_corr[k] - y_corr[nxt]) if y_corr[k] != y_corr[nxt] else 0.0
                edge = E[k] + frac * (E[nxt] - E[k])
                break
            running_min = min(running_min, y_corr[nxt])
            if y_corr[nxt] > running_min + tolerance:
                break  # rising toward a neighbouring peak before half height: overlap
            k = nxt
        edges.append(edge)
    if edges[0] is None or edges[1] is None:
        return None, False
    return float(abs(edges[1] - edges[0])), True


def detect_sweep_peaks(
    E: np.ndarray,
    i_s: np.ndarray,
    direction: int,
    threshold: float,
) -> list[dict]:
    """Candidate peaks on one sweep (local indices), strongest first."""
    n = E.size
    if n < 7:
        return []
    y = direction * i_s
    step = median_step(E)
    min_width_pts = max(2.0, MIN_PEAK_WIDTH_V / step) if step > 0 else 2.0
    idx, props = find_peaks(y, prominence=threshold, width=min_width_pts, rel_height=0.5)
    found = []
    grid = np.arange(n, dtype=float)
    for k, p in enumerate(idx):
        if p < 2 or p > n - 3:
            continue
        e_left = float(np.interp(props["left_ips"][k], grid, E))
        e_right = float(np.interp(props["right_ips"][k], grid, E))
        found.append(
            {
                "local_index": int(p),
                "prominence": float(props["prominences"][k]),
                "width_v": abs(e_right - e_left),
            }
        )
    found.sort(key=lambda d: d["prominence"], reverse=True)
    return found


def build_peaks(
    E: np.ndarray,
    i_raw: np.ndarray,
    i_s: np.ndarray,
    direction: int,
    candidates: list[dict],
    baseline: Baseline,
    sweep: str,
    segment: int,
    offset: int,
    tolerance: float,
) -> list[Peak]:
    peaks = []
    e_lo, e_hi = float(min(E[0], E[-1])), float(max(E[0], E[-1]))
    y_corr = direction * (i_s - (baseline.intercept + baseline.slope * E))
    for c in candidates:
        p = c["local_index"]
        e_p = float(E[p])
        base = baseline.at(e_p)
        width, _resolved = fwhm_above_baseline(E, y_corr, p, tolerance)
        margin = max(width or 0.0, 0.02)
        peaks.append(
            Peak(
                label="",
                kind="anodic" if direction > 0 else "cathodic",
                sweep=sweep,
                segment=segment,
                index=offset + p,
                potential=e_p,
                current=float(i_s[p]),
                current_raw=float(i_raw[p]),
                baseline_current=float(base),
                height=float(direction * (i_s[p] - base)),
                prominence=c["prominence"],
                width_v=width,
                near_vertex=(e_p - e_lo) < margin or (e_hi - e_p) < margin,
            )
        )
    return peaks


def vertex_behavior(
    E: np.ndarray,
    i_s: np.ndarray,
    direction: int,
    peak_local_indices: list[int],
    reference_height: float,
    rise_fraction_threshold: float,
) -> dict | None:
    """How the current behaves over the last 30 mV before the sweep's end vertex.

    `rise` is the increase of the current magnitude (in the sweep's expected
    direction) from its minimum after the last peak to the vertex.
    """
    n = E.size
    s = direction * (E - E[0])
    tail = s >= s[-1] - VERTEX_WINDOW_V
    if tail.sum() < 3 or n < 7:
        return None
    y = direction * i_s
    slope = float(np.polyfit(s[tail], y[tail], 1)[0])  # A per V along the sweep
    start = max(peak_local_indices) if peak_local_indices else 0
    y_min = float(np.min(y[start:]))
    rise = float(y[-1] - y_min)
    frac = rise / reference_height if reference_height > 0 else None
    rising = bool(slope > 0 and frac is not None and frac > rise_fraction_threshold)
    return {
        "potential": float(E[-1]),
        "current": float(i_s[-1]),
        "slope_per_10mV": slope * 0.010,
        "rise": rise,
        "rise_fraction": frac,
        "rising": rising,
        "window_v": VERTEX_WINDOW_V,
    }


def sweep_charge(i: np.ndarray, t: np.ndarray | None, E: np.ndarray, scan_rate: float | None) -> tuple[float | None, str | None]:
    """Net charge passed during a sweep (C, or C/cm^2 for current density)."""
    if t is not None and np.all(np.isfinite(t)) and float(np.ptp(t)) > 0:
        return float(trapezoid(i, t)), "time column"
    if scan_rate and scan_rate > 0:
        tt = np.concatenate([[0.0], np.cumsum(np.abs(np.diff(E)) / scan_rate)])
        return float(trapezoid(i, tt)), "entered scan rate (constant-rate assumption)"
    return None, None


def pair_peaks(forward: list[Peak], ret: list[Peak], max_sep: float = PAIR_MAX_SEPARATION_V):
    """Order-preserving pairing of forward and return peaks.

    Maximizes the number of pairs, then minimizes the total potential separation,
    without letting pairs cross (A1 pairs with a lower-potential return peak than A2).
    This is a geometric pairing, not a mechanistic assignment.
    """
    F = sorted(forward, key=lambda p: p.potential)
    R = sorted(ret, key=lambda p: p.potential)
    m, k = len(F), len(R)
    score = [[(0, 0.0)] * (k + 1) for _ in range(m + 1)]
    back: list[list[str | None]] = [[None] * (k + 1) for _ in range(m + 1)]
    for a in range(m + 1):
        for b in range(k + 1):
            if a == 0 and b == 0:
                continue
            best, choice = None, None
            if a > 0:
                best, choice = score[a - 1][b], "skip_f"
            if b > 0 and (best is None or score[a][b - 1] > best):
                best, choice = score[a][b - 1], "skip_r"
            if a > 0 and b > 0:
                sep = abs(F[a - 1].potential - R[b - 1].potential)
                if sep <= max_sep:
                    prev = score[a - 1][b - 1]
                    cand = (prev[0] + 1, prev[1] - sep)
                    if best is None or cand > best:
                        best, choice = cand, "match"
            score[a][b] = best
            back[a][b] = choice
    pairs = []
    a, b = m, k
    while a > 0 or b > 0:
        choice = back[a][b]
        if choice == "match":
            pairs.append((F[a - 1], R[b - 1]))
            a, b = a - 1, b - 1
        elif choice == "skip_f":
            a -= 1
        else:
            b -= 1
    pairs.reverse()
    paired_f = {id(p[0]) for p in pairs}
    paired_r = {id(p[1]) for p in pairs}
    return pairs, [p for p in F if id(p) not in paired_f], [p for p in R if id(p) not in paired_r]


def nicholson_ratio(i_forward_peak: float, i_return_peak_zero: float, i_switch_zero: float) -> float | None:
    """Nicholson's empirical return/forward peak-current ratio (diffusion-controlled systems).

    All arguments are magnitudes in the direction of the respective process:
    the forward peak current measured from its baseline, the return peak current
    measured from zero current, and the forward-direction current at the switching
    potential measured from zero current.
    """
    if i_forward_peak <= 0:
        return None
    return i_return_peak_zero / i_forward_peak + NICHOLSON_A * i_switch_zero / i_forward_peak + NICHOLSON_B
