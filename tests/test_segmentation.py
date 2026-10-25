import numpy as np

from benchcheck.cv.segmentation import (
    assign_cycles,
    default_cycle,
    detect_forward_direction,
    find_turning_points,
    reversal_threshold,
    segment_scan,
)


def triangle_wave(e_low=0.0, e_high=1.0, cycles=3, step=0.001, start=None, first_up=True):
    start = e_low if start is None else start
    pieces = []
    if first_up:
        pieces.append(np.arange(start, e_high, step))
        for _ in range(cycles - 1):
            pieces += [np.arange(e_high, e_low, -step), np.arange(e_low, e_high, step)]
        pieces.append(np.arange(e_high, start - step / 2, -step))
    else:
        pieces.append(np.arange(start, e_low, -step))
        for _ in range(cycles - 1):
            pieces += [np.arange(e_low, e_high, step), np.arange(e_high, e_low, -step)]
        pieces.append(np.arange(e_low, start + step / 2, step))
    return np.concatenate(pieces)


def test_three_cycles_from_lower_vertex():
    E = triangle_wave(cycles=3)
    segs, seg_id = segment_scan(E)
    assert [s.direction for s in segs] == [1, -1, 1, -1, 1, -1]
    assert all(not s.partial for s in segs)
    cycles, leading = assign_cycles(segs, detect_forward_direction(segs))
    assert len(cycles) == 3 and all(c.complete for c in cycles)
    assert leading == []
    assert default_cycle(cycles) == 2
    assert seg_id[0] == 0 and seg_id[-1] == 5


def test_vertices_located_exactly():
    E = triangle_wave(e_low=0.2, e_high=1.1, cycles=2)
    v = find_turning_points(E, reversal_threshold(E))
    assert np.allclose(E[v], [1.099, 0.201, 1.099], atol=1.5e-3)


def test_start_mid_window_gives_partial_first_cycle():
    E = triangle_wave(e_low=0.0, e_high=1.0, cycles=3, start=0.5)
    segs, _ = segment_scan(E)
    assert segs[0].partial and segs[0].direction == 1
    fwd = detect_forward_direction(segs)
    assert fwd == 1  # first partial sweep records the actual initial scan direction
    cycles, leading = assign_cycles(segs, fwd)
    assert leading == []
    assert cycles[0].complete is False
    assert default_cycle(cycles) == 2


def test_forward_direction_negative_first():
    E = triangle_wave(cycles=2, start=1.0, first_up=False)
    segs, _ = segment_scan(E)
    assert segs[0].direction == -1
    assert detect_forward_direction(segs) == -1


def test_noise_does_not_create_vertices():
    rng = np.random.default_rng(0)
    E = triangle_wave(cycles=2) + rng.normal(0, 5e-4, 1)[0]
    E = E + rng.normal(0, 5e-4, E.size)  # 0.5 mV measurement noise
    segs, _ = segment_scan(E)
    assert len(segs) == 4


def test_staircase_plateaus_at_vertices():
    E = np.repeat(triangle_wave(cycles=2, step=0.005), 3)  # every potential held for 3 samples
    segs, _ = segment_scan(E)
    assert len(segs) == 4
    assert [s.direction for s in segs] == [1, -1, 1, -1]


def test_measured_scan_rate_from_time():
    E = triangle_wave(cycles=2, step=0.001)
    t = np.arange(E.size) * 0.02  # 0.001 V per 0.02 s = 50 mV/s
    segs, _ = segment_scan(E, t)
    for s in segs:
        assert abs(s.scan_rate_measured - 0.05) < 1e-4
        assert s.scan_rate_r2 > 0.9999
