"""Scan segmentation: find potential reversals (vertices), sweeps and cycles.

Definitions used throughout BenchCheck (shown to the user in the UI):

* A *sweep* (segment) is a run of points between two scan reversals in which the
  potential moves in one direction: positive-going (anodic sweep) or
  negative-going (cathodic sweep).
* A *cycle* is one sweep in the forward direction followed by the next sweep in
  the opposite (return) direction. The forward direction is the direction of the
  first full-range sweep unless the user overrides it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

FULL_RANGE_FRACTION = 0.9
TRIVIAL_SPAN_FRACTION = 0.02


@dataclass
class Segment:
    index: int
    start: int  # inclusive index into the data arrays
    end: int  # inclusive; the vertex point is shared with the next segment
    direction: int  # +1 positive-going, -1 negative-going
    e_start: float
    e_end: float
    span_fraction: float
    partial: bool
    trivial: bool
    n_points: int
    scan_rate_measured: float | None = None  # V/s, from the time column
    scan_rate_r2: float | None = None

    @property
    def direction_label(self) -> str:
        return "positive-going" if self.direction > 0 else "negative-going"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction_label"] = self.direction_label
        return d


@dataclass
class Cycle:
    number: int
    forward: int | None
    reverse: int | None
    complete: bool

    def to_dict(self) -> dict:
        return asdict(self)


def reversal_threshold(E: np.ndarray) -> float:
    span = float(np.nanmax(E) - np.nanmin(E))
    steps = np.abs(np.diff(E))
    steps = steps[steps > 0]
    step = float(np.median(steps)) if steps.size else 0.0
    return max(0.05 * span, 5.0 * step)


def find_turning_points(E: np.ndarray, threshold: float) -> list[int]:
    """Indices of scan reversals using a hysteresis ("zigzag") rule.

    A reversal is confirmed only after the potential has moved back by more than
    `threshold` from the running extreme, so measurement noise and staircase
    plateaus do not create spurious vertices. The vertex is the first point that
    reached the extreme.
    """
    n = int(E.size)
    vertices: list[int] = []
    if n < 3 or threshold <= 0:
        return vertices
    direction = 0
    hi_idx = lo_idx = ext_idx = 0
    for k in range(1, n):
        x = E[k]
        if direction == 0:
            if x > E[hi_idx]:
                hi_idx = k
            if x < E[lo_idx]:
                lo_idx = k
            if E[hi_idx] - E[lo_idx] >= threshold:
                direction, ext_idx = (1, hi_idx) if hi_idx > lo_idx else (-1, lo_idx)
            continue
        if direction == 1:
            if x > E[ext_idx]:
                ext_idx = k
            elif E[ext_idx] - x >= threshold:
                vertices.append(ext_idx)
                direction = -1
                ext_idx = ext_idx + int(np.argmin(E[ext_idx : k + 1]))
        else:
            if x < E[ext_idx]:
                ext_idx = k
            elif x - E[ext_idx] >= threshold:
                vertices.append(ext_idx)
                direction = 1
                ext_idx = ext_idx + int(np.argmax(E[ext_idx : k + 1]))
    return vertices


def count_reversals(values: np.ndarray) -> int:
    v = values[np.isfinite(values)]
    if v.size < 5 or float(v.max() - v.min()) <= 0:
        return 0
    return len(find_turning_points(v, reversal_threshold(v)))


def _fit_scan_rate(E: np.ndarray, t: np.ndarray) -> tuple[float | None, float | None]:
    n = E.size
    lo, hi = int(0.05 * n), int(0.95 * n)
    e, tt = E[lo:hi], t[lo:hi]
    mask = np.isfinite(e) & np.isfinite(tt)
    e, tt = e[mask], tt[mask]
    if e.size < 5 or float(np.ptp(tt)) <= 0:
        return None, None
    slope, intercept = np.polyfit(tt, e, 1)
    resid = e - (slope * tt + intercept)
    ss_tot = float(np.sum((e - e.mean()) ** 2))
    r2 = 1.0 - float(np.sum(resid**2)) / ss_tot if ss_tot > 0 else None
    return abs(float(slope)), r2


def segment_scan(E: np.ndarray, t: np.ndarray | None = None) -> tuple[list[Segment], np.ndarray]:
    """Split a potential trace into sweeps. Returns segments and a per-point segment id."""
    n = int(E.size)
    if n < 10:
        raise ValueError("At least 10 data points are needed to analyze a voltammogram.")
    span = float(np.max(E) - np.min(E))
    if span <= 1e-6:
        raise ValueError("The potential column does not vary; check the column mapping.")
    vertices = find_turning_points(E, reversal_threshold(E))
    bounds = [0] + vertices + [n - 1]
    segments: list[Segment] = []
    seg_id = np.zeros(n, dtype=int)
    for k in range(len(bounds) - 1):
        a, b = bounds[k], bounds[k + 1]
        if b <= a:
            continue
        e0, e1 = float(E[a]), float(E[b])
        frac = abs(e1 - e0) / span
        direction = 1 if e1 >= e0 else -1
        seg = Segment(
            index=len(segments),
            start=a,
            end=b,
            direction=direction,
            e_start=e0,
            e_end=e1,
            span_fraction=frac,
            partial=frac < FULL_RANGE_FRACTION,
            trivial=frac < TRIVIAL_SPAN_FRACTION or (b - a + 1) < 5,
            n_points=b - a + 1,
        )
        if t is not None:
            seg.scan_rate_measured, seg.scan_rate_r2 = _fit_scan_rate(E[a : b + 1], t[a : b + 1])
        seg_id[a:b] = seg.index
        segments.append(seg)
    seg_id[n - 1] = segments[-1].index
    return segments, seg_id


def detect_forward_direction(segments: list[Segment]) -> int:
    for seg in segments:
        if not seg.trivial and not seg.partial:
            return seg.direction
    for seg in segments:
        if not seg.trivial:
            return seg.direction
    return segments[0].direction


def assign_cycles(segments: list[Segment], forward_direction: int) -> tuple[list[Cycle], list[int]]:
    """Pair forward and return sweeps into cycles. Returns (cycles, leading segment ids)."""
    cycles: list[Cycle] = []
    leading: list[int] = []
    current: Cycle | None = None
    for seg in segments:
        if seg.trivial:
            continue
        if seg.direction == forward_direction:
            current = Cycle(number=len(cycles) + 1, forward=seg.index, reverse=None, complete=False)
            cycles.append(current)
        elif current is not None and current.reverse is None:
            current.reverse = seg.index
        else:
            leading.append(seg.index)
    for cyc in cycles:
        fwd = segments[cyc.forward] if cyc.forward is not None else None
        rev = segments[cyc.reverse] if cyc.reverse is not None else None
        cyc.complete = bool(fwd and rev and not fwd.partial and not rev.partial)
    return cycles, leading


def default_cycle(cycles: list[Cycle]) -> int | None:
    """Cycle 2 if it is complete (cycle 1 often reflects conditioning), else the first complete cycle."""
    complete = [c.number for c in cycles if c.complete]
    if 2 in complete:
        return 2
    if complete:
        return complete[0]
    with_both = [c.number for c in cycles if c.forward is not None and c.reverse is not None]
    if with_both:
        return with_both[0]
    return cycles[0].number if cycles else None
