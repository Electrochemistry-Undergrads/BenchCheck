"""Synthetic CVs for an insertion/thin-film electrode (used for the labeled demo examples).

Model (all parameters are explicit and written next to each generated example):

* Each redox site j (n = 1) holds a fixed charge Q_j split between a reduced
  amount R_j and an oxidized amount O_j, with Butler–Volmer kinetics:
  k_f = k0 exp((1 - α) f η), k_b = k0 exp(-α f η), η = E - E0_j, f = F/RT.
  Faradaic current i_j = F (k_f R_j - k_b O_j), anodic positive.
* Optional potential-dependent irreversible loss of the oxidized state,
  k_loss(E) = k_loss0 exp((E - E_loss) / b_loss): O_j -> inactive (no current).
* Optional irreversible anodic side current (Tafel form),
  i_side = i0_side exp((E - E_side) / b_side), e.g. a stand-in for solvent oxidation.
* Double-layer current C_dl dE/dt, relaxing with time constant tau_dl at vertices.
* Gaussian noise with a fixed seed.

The potential is a staircase (step dE, duration dE / v); within a step E is
constant, so the linear kinetics are integrated exactly with a matrix exponential.
The reported current is the step-averaged current. This is an illustration, not
a model fitted to any real material.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.linalg import expm

F = 96485.33212
R = 8.314462618


@dataclass
class Site:
    e0: float  # V
    charge_c: float  # C
    k0: float  # 1/s
    alpha: float = 0.5


@dataclass
class ThinFilmParams:
    sites: list[Site]
    e_low: float
    e_high: float
    e_start: float
    scan_rate: float  # V/s
    n_cycles: int
    step_v: float = 0.001
    temperature_c: float = 25.0
    c_dl: float = 0.0  # F
    tau_dl: float = 2.0  # s
    i0_side: float = 0.0  # A
    e_side: float = 1.2  # V
    b_side: float = 0.05  # V
    k_loss0: float = 0.0  # 1/s
    e_loss: float = 1.2  # V
    b_loss: float = 0.04  # V
    noise_a: float = 0.0  # A (standard deviation)
    seed: int = 7
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def staircase(e_start: float, e_low: float, e_high: float, n_cycles: int, step: float) -> np.ndarray:
    """Start at e_start, sweep positive to e_high, down to e_low, back up to e_start; repeat."""
    pieces = []
    for c in range(n_cycles):
        up = np.arange(e_start if c == 0 else e_start, e_high, step)
        down = np.arange(e_high, e_low, -step)
        back = np.arange(e_low, e_start, step)
        pieces.extend([up, down, back])
    pieces.append(np.array([e_start]))
    return np.round(np.concatenate(pieces), 6)


def simulate(params: ThinFilmParams) -> dict:
    f = F / (R * (params.temperature_c + 273.15))
    E = staircase(params.e_start, params.e_low, params.e_high, params.n_cycles, params.step_v)
    dt = params.step_v / params.scan_rate
    n = E.size
    t = np.arange(n) * dt
    reduced = np.array([s.charge_c / F for s in params.sites])
    oxidized = np.zeros(len(params.sites))
    i_far = np.zeros(n)
    lost_c = np.zeros(n)
    for k in range(n):
        e = E[k]
        k_loss = params.k_loss0 * np.exp((e - params.e_loss) / params.b_loss) if params.k_loss0 else 0.0
        total = 0.0
        for j, s in enumerate(params.sites):
            eta = e - s.e0
            kf = s.k0 * np.exp(min((1 - s.alpha) * f * eta, 300.0))
            kb = s.k0 * np.exp(min(-s.alpha * f * eta, 300.0))
            M = np.array([[-kf, kb], [kf, -(kb + k_loss)]])
            x0 = np.array([reduced[j], oxidized[j]])
            x1 = expm(M * dt) @ x0
            # Electrons transferred this step = decrease of the reduced amount.
            total += F * (x0[0] - x1[0]) / dt
            reduced[j], oxidized[j] = x1
        i_far[k] = total
        lost_c[k] = sum(s.charge_c for s in params.sites) - F * (reduced.sum() + oxidized.sum())

    dEdt = np.gradient(E, t)
    dEdt = np.sign(dEdt) * params.scan_rate
    i_dl = np.zeros(n)
    target = params.c_dl * dEdt
    if params.c_dl:
        decay = np.exp(-dt / params.tau_dl) if params.tau_dl > 0 else 0.0
        i_dl[0] = target[0]
        for k in range(1, n):
            i_dl[k] = target[k] + (i_dl[k - 1] - target[k]) * decay
    i_side = params.i0_side * np.exp((E - params.e_side) / params.b_side) if params.i0_side else np.zeros(n)
    rng = np.random.default_rng(params.seed)
    noise = rng.normal(0.0, params.noise_a, n) if params.noise_a else np.zeros(n)
    current = i_far + i_dl + i_side + noise
    return {
        "time_s": t,
        "potential_v": E,
        "current_a": current,
        "components": {"faradaic": i_far, "double_layer": i_dl, "side": i_side, "noise": noise},
        "lost_charge_c": lost_c,
    }


def write_csv(path, sim: dict, header_note: list[str]) -> None:
    lines = [f"# {line}" for line in header_note]
    lines.append("time/s,Ewe/V,<I>/mA")
    for t, e, i in zip(sim["time_s"], sim["potential_v"], sim["current_a"]):
        lines.append(f"{t:.1f},{e:.4f},{i * 1e3:.6f}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
