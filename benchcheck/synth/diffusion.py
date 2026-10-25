"""Finite-difference CV simulation for a dissolved, reversible (Nernstian) redox couple.

Used only to validate BenchCheck's peak measurements against textbook theory
(Randles–Ševčík peak current, ~57 mV peak separation, peak-current ratio of 1).

Planar semi-infinite diffusion, R -> O + e- (oxidation first), equal diffusion
coefficients so C_O + C_R = C* everywhere. Dimensionless form:
  dc/dτ = d²c/dξ²,  c(0, τ) = 1 / (1 + exp(θ(τ))),  θ = f (E - E0)
with τ = f v t and ξ = x / sqrt(D / (f v)). Current: i = F A C* sqrt(D f v) dc/dξ|_0.
Crank–Nicolson time stepping on a uniform grid.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import solve_banded

F = 96485.33212
R = 8.314462618


def simulate_reversible(
    e0: float = 0.25,
    e_start: float = -0.05,
    e_vertex: float = 0.55,
    scan_rate: float = 0.1,
    diffusion_cm2_s: float = 7.0e-6,
    conc_mM: float = 5.0,
    area_cm2: float = 0.0707,
    temperature_c: float = 25.0,
    step_v: float = 0.001,
    d_xi: float = 0.02,
    substeps: int = 4,
) -> dict:
    f = F / (R * (temperature_c + 273.15))
    up = np.arange(e_start, e_vertex, step_v)
    down = np.arange(e_vertex, e_start - step_v / 2, -step_v)
    E = np.concatenate([up, down])
    theta = f * (E - e0)
    d_tau = f * step_v / substeps
    tau_total = f * step_v * E.size
    xi_max = 6.0 * np.sqrt(tau_total) + 6.0
    n = int(xi_max / d_xi) + 1
    lam = d_tau / d_xi**2
    c = np.ones(n)
    # Interior unknowns c[1..n-2]; boundaries c[0] (Nernst) and c[n-1] = 1 (bulk).
    m = n - 2
    ab = np.zeros((3, m))
    ab[0, 1:] = -lam / 2
    ab[1, :] = 1 + lam
    ab[2, :-1] = -lam / 2
    chi = np.zeros(E.size)
    th_prev = theta[0]
    c[0] = 1.0 / (1.0 + np.exp(th_prev))
    for k in range(E.size):
        for s in range(substeps):
            frac = (s + 1) / substeps
            th_prev_k = theta[k - 1] if k > 0 else theta[0]
            th_new = th_prev_k + (theta[k] - th_prev_k) * frac
            c0_new = 1.0 / (1.0 + np.exp(th_new))
            rhs = (lam / 2) * c[:-2] + (1 - lam) * c[1:-1] + (lam / 2) * c[2:]
            rhs[0] += (lam / 2) * c0_new
            rhs[-1] += (lam / 2) * 1.0
            c[1:-1] = solve_banded((1, 1), ab, rhs)
            c[0] = c0_new
            c[-1] = 1.0
        chi[k] = (-3 * c[0] + 4 * c[1] - c[2]) / (2 * d_xi)
    scale = F * area_cm2 * (conc_mM * 1e-6) * np.sqrt(diffusion_cm2_s * f * scan_rate)
    current = chi * scale
    t = np.arange(E.size) * step_v / scan_rate
    return {
        "time_s": t,
        "potential_v": np.round(E, 6),
        "current_a": current,
        "chi": chi,
        "randles_sevcik_a": 0.4463 * F * area_cm2 * (conc_mM * 1e-6) * np.sqrt(f * scan_rate * diffusion_cm2_s),
        "params": {
            "e0": e0, "e_start": e_start, "e_vertex": e_vertex, "scan_rate": scan_rate,
            "diffusion_cm2_s": diffusion_cm2_s, "conc_mM": conc_mM, "area_cm2": area_cm2,
            "temperature_c": temperature_c,
        },
    }
