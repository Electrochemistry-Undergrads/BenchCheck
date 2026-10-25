"""Unit handling. Internally BenchCheck works in V, A (or A/cm^2), s and V/s."""

from __future__ import annotations

import math

import numpy as np

POTENTIAL_UNITS = {"V": 1.0, "mV": 1e-3}
CURRENT_UNITS = {"A": 1.0, "mA": 1e-3, "uA": 1e-6, "nA": 1e-9, "pA": 1e-12}
CURRENT_DENSITY_UNITS = {"A/cm2": 1.0, "mA/cm2": 1e-3, "uA/cm2": 1e-6}
TIME_UNITS = {"s": 1.0, "ms": 1e-3, "min": 60.0, "h": 3600.0}
SCAN_RATE_UNITS = {"V/s": 1.0, "mV/s": 1e-3}

# Pretty labels used in the UI and reports.
LABELS = {
    "uA": "µA",
    "uA/cm2": "µA cm⁻²",
    "mA/cm2": "mA cm⁻²",
    "A/cm2": "A cm⁻²",
    "V/s": "V s⁻¹",
    "mV/s": "mV s⁻¹",
}


class UnitError(ValueError):
    pass


def normalize_unit(unit: str) -> str:
    """Map user/header spellings ('µA', 'μA', 'mA cm-2', 'mv/s') to canonical keys."""
    u = (unit or "").strip()
    u = u.replace("µ", "u").replace("μ", "u").replace("²", "2").replace("⁻", "-")
    compact = u.replace(" ", "").replace("^", "")
    lowered = compact.lower()
    aliases = {
        "v": "V", "mv": "mV",
        "a": "A", "ma": "mA", "ua": "uA", "na": "nA", "pa": "pA",
        "a/cm2": "A/cm2", "acm-2": "A/cm2",
        "ma/cm2": "mA/cm2", "macm-2": "mA/cm2",
        "ua/cm2": "uA/cm2", "uacm-2": "uA/cm2",
        "s": "s", "sec": "s", "ms": "ms", "min": "min", "h": "h", "hr": "h",
        "v/s": "V/s", "vs-1": "V/s", "mv/s": "mV/s", "mvs-1": "mV/s",
    }
    if lowered in aliases:
        return aliases[lowered]
    raise UnitError(f"Unrecognized unit: {unit!r}")


def label(unit: str) -> str:
    return LABELS.get(unit, unit)


def is_current_density(unit: str) -> bool:
    return unit in CURRENT_DENSITY_UNITS


def factor(unit: str, kind: str) -> float:
    """Multiplicative factor converting `unit` to the SI-like base for `kind`."""
    tables = {
        "potential": POTENTIAL_UNITS,
        "current": {**CURRENT_UNITS, **CURRENT_DENSITY_UNITS},
        "time": TIME_UNITS,
        "scan_rate": SCAN_RATE_UNITS,
    }
    table = tables[kind]
    canonical = normalize_unit(unit)
    if canonical not in table:
        raise UnitError(f"Unit {unit!r} is not a valid {kind} unit")
    return table[canonical]


def to_base(values: np.ndarray, unit: str, kind: str) -> np.ndarray:
    return np.asarray(values, dtype=float) * factor(unit, kind)


def display_current_unit(max_abs: float, density: bool) -> tuple[str, float]:
    """Choose a readable display unit for currents given the largest |i| in base units.

    Returns (unit key, scale) where display value = base value * scale.
    """
    if density:
        options = [("uA/cm2", 1e6), ("mA/cm2", 1e3), ("A/cm2", 1.0)]
        thresholds = [1e-3, 1.0]
    else:
        options = [("nA", 1e9), ("uA", 1e6), ("mA", 1e3), ("A", 1.0)]
        thresholds = [1e-6, 1e-3, 1.0]
    if not math.isfinite(max_abs) or max_abs <= 0:
        return options[-2] if not density else options[1]
    for (unit, scale), limit in zip(options, thresholds):
        if max_abs < limit:
            return unit, scale
    return options[-1]


def display_charge_unit(max_abs_coulomb: float) -> tuple[str, float]:
    if max_abs_coulomb < 1e-6:
        return "nC", 1e9
    if max_abs_coulomb < 1e-3:
        return "µC", 1e6
    if max_abs_coulomb < 1.0:
        return "mC", 1e3
    return "C", 1.0


def fmt_sig(value: float | None, sig: int = 3) -> str:
    """Format with `sig` significant figures, without scientific notation for common ranges."""
    if value is None or not math.isfinite(value):
        return "n/a"
    if value == 0:
        return "0"
    digits = sig - int(math.floor(math.log10(abs(value)))) - 1
    digits = max(0, min(digits, 8))
    return f"{value:.{digits}f}"


def fmt_current(value_base: float | None, unit: str, scale: float, signed: bool = True) -> str:
    if value_base is None or not math.isfinite(value_base):
        return "n/a"
    text = fmt_sig(value_base * scale)
    if signed and value_base > 0:
        text = "+" + text
    return f"{text} {label(unit)}"


def fmt_potential(value_v: float | None) -> str:
    if value_v is None or not math.isfinite(value_v):
        return "n/a"
    return f"{value_v:.3f} V"


def fmt_mv(value_v: float | None) -> str:
    if value_v is None or not math.isfinite(value_v):
        return "n/a"
    return f"{value_v * 1e3:.0f} mV"


def fmt_scan_rate(value_v_per_s: float | None) -> str:
    if value_v_per_s is None or not math.isfinite(value_v_per_s):
        return "n/a"
    if value_v_per_s < 0.1:
        return f"{fmt_sig(value_v_per_s * 1e3)} mV s⁻¹"
    return f"{fmt_sig(value_v_per_s)} V s⁻¹"
