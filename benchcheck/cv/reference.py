"""Reference electrodes and (user-confirmed) potential-scale conversions.

BenchCheck never converts potentials silently. A conversion is applied only when
the request carries `confirmed: true`, and the offset, its basis and caveats are
recorded in the processing log of every result.
"""

from __future__ import annotations

import math

FARADAY = 96485.33212  # C/mol
GAS_CONSTANT = 8.314462618  # J/(mol K)

# Approximate potentials vs SHE at 25 °C as commonly tabulated in electrochemistry
# references and electrode datasheets. They differ by a few mV between sources and
# with temperature; users should prefer their own electrode's specification.
REFERENCE_ELECTRODES: dict[str, dict] = {
    "ag_agcl_3m_kcl": {"label": "Ag/AgCl (3 M KCl)", "family": "ag_agcl", "vs_she": 0.210},
    "ag_agcl_3_5m_kcl": {"label": "Ag/AgCl (3.5 M KCl)", "family": "ag_agcl", "vs_she": 0.205},
    "ag_agcl_sat_kcl": {"label": "Ag/AgCl (saturated KCl)", "family": "ag_agcl", "vs_she": 0.197},
    "ag_agcl_other": {"label": "Ag/AgCl (other or unknown filling)", "family": "ag_agcl", "vs_she": None},
    "sce": {"label": "SCE (saturated KCl)", "family": "sce", "vs_she": 0.241},
    "she": {"label": "SHE / NHE", "family": "she", "vs_she": 0.0},
    "rhe": {"label": "RHE", "family": "rhe", "vs_she": None},
    "hg_hgo": {"label": "Hg/HgO", "family": "hg_hgo", "vs_she": None},
    "hg_hg2so4": {"label": "Hg/Hg₂SO₄ (MSE)", "family": "mse", "vs_she": None},
    "li": {"label": "Li/Li⁺", "family": "li", "vs_she": None},
    "na": {"label": "Na/Na⁺", "family": "na", "vs_she": None},
    "ag_ag_plus": {"label": "Ag/Ag⁺ (non-aqueous)", "family": "ag_ag_plus", "vs_she": None},
    "pseudo": {"label": "Pseudo-reference (e.g., Ag or Pt wire)", "family": "pseudo", "vs_she": None},
    "other": {"label": "Other (describe)", "family": "other", "vs_she": None},
}

TABULATED_NOTE = (
    "Approximate tabulated value at 25 °C; published values differ by a few mV and the "
    "offset depends on filling solution and temperature. Prefer your electrode's datasheet."
)


def reference_info(key: str | None) -> dict | None:
    if not key:
        return None
    return REFERENCE_ELECTRODES.get(key)


def reference_label(key: str | None, detail: str | None = None) -> str:
    info = reference_info(key)
    if info is None:
        return detail or (key or "unknown reference")
    if key == "other" and detail:
        return detail
    return info["label"]


def nernst_slope(temperature_c: float | None) -> float:
    """ln(10) RT/F in volts (0.05916 V at 25 °C)."""
    t_k = (temperature_c if temperature_c is not None else 25.0) + 273.15
    return math.log(10) * GAS_CONSTANT * t_k / FARADAY


def plan_conversion(
    from_key: str | None,
    target: str,
    ph: float | None = None,
    temperature_c: float | None = None,
    custom_offset_v: float | None = None,
    custom_description: str | None = None,
) -> dict:
    """Describe a potential-scale conversion without applying it.

    Returns {"possible": bool, "offset_v", "to_label", "explanation", "caveats"}.
    E_converted = E_recorded + offset_v.
    """
    info = reference_info(from_key)
    from_label = reference_label(from_key)
    if target == "custom":
        if custom_offset_v is None or not math.isfinite(custom_offset_v):
            return {"possible": False, "reason": "Enter the offset (in V) to add to the recorded potentials."}
        return {
            "possible": True,
            "offset_v": float(custom_offset_v),
            "to_label": custom_description or f"custom scale ({from_label} {custom_offset_v:+.3f} V)",
            "explanation": f"E_new = E({from_label}) {custom_offset_v:+.3f} V (user-supplied offset).",
            "caveats": [custom_description or "Offset supplied by the user; BenchCheck cannot verify it."],
        }
    if info is None:
        return {"possible": False, "reason": "Select the reference electrode used before converting."}
    slope = nernst_slope(temperature_c)
    if target == "SHE":
        if from_key == "rhe":
            if ph is None:
                return {"possible": False, "reason": "Converting from RHE to SHE requires the electrolyte pH."}
            off = -slope * ph
            return {
                "possible": True, "offset_v": off, "to_label": "SHE",
                "explanation": f"E(SHE) = E(RHE) − {slope * 1e3:.2f} mV × pH ({ph:g}).",
                "caveats": ["Assumes the stated pH and temperature."],
            }
        if info["vs_she"] is None:
            return {"possible": False, "reason": f"No reliable tabulated offset for {from_label}; use a custom offset."}
        return {
            "possible": True, "offset_v": info["vs_she"], "to_label": "SHE",
            "explanation": f"E(SHE) = E({from_label}) + {info['vs_she']:.3f} V.",
            "caveats": [TABULATED_NOTE],
        }
    if target == "RHE":
        if ph is None:
            return {"possible": False, "reason": "Converting to RHE requires the electrolyte pH."}
        if from_key == "rhe":
            return {"possible": False, "reason": "Potentials are already on the RHE scale."}
        if info["vs_she"] is None:
            return {"possible": False, "reason": f"No reliable tabulated offset for {from_label}; use a custom offset."}
        off = info["vs_she"] + slope * ph
        return {
            "possible": True, "offset_v": off, "to_label": "RHE",
            "explanation": (
                f"E(RHE) = E({from_label}) + {info['vs_she']:.3f} V + {slope * 1e3:.2f} mV × pH ({ph:g})."
            ),
            "caveats": [TABULATED_NOTE, "Assumes the stated pH and temperature."],
        }
    return {"possible": False, "reason": f"Unknown target scale {target!r}."}
