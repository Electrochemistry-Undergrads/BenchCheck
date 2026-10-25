"""Experiment metadata: completeness checks and why each field matters."""

from __future__ import annotations

from ..evidence.conditions import parse_electrolyte
from ..models import ExperimentMetadata
from .reference import reference_label
from .units import fmt_scan_rate


def scan_rate_v_s(meta: ExperimentMetadata) -> float | None:
    if meta.scan_rate is None or meta.scan_rate.value is None:
        return None
    unit = (meta.scan_rate.unit or "mV/s").replace(" ", "").lower()
    factor = {"mv/s": 1e-3, "v/s": 1.0}.get(unit)
    if factor is None or meta.scan_rate.value <= 0:
        return None
    return meta.scan_rate.value * factor


def metadata_status(meta: ExperimentMetadata, measured_scan_rate: float | None) -> list[dict]:
    """One row per field: provided / missing / measured / assumed / not applicable."""
    rows: list[dict] = []
    dissolved = meta.process_type == "dissolved_species"
    material = meta.process_type == "electrode_material"

    def add(field, label, value, status, why, importance="recommended"):
        rows.append(
            {"field": field, "label": label, "value": value, "status": status, "why": why, "importance": importance}
        )

    add(
        "electrode_material", "Working electrode material", meta.electrode_material,
        "provided" if meta.electrode_material else "missing",
        "Used to find literature on the same material and to judge how well each paper applies.",
        "required",
    )
    add(
        "process_type", "Where the redox-active species is",
        {"electrode_material": "in the electrode (film, insertion or adsorbed)",
         "dissolved_species": "dissolved in the electrolyte"}.get(meta.process_type),
        "missing" if meta.process_type == "unknown" else "provided",
        "Decides which analyses apply: thin-film charge balance vs. diffusion-controlled criteria "
        "(Nicholson ratio, Randles–Ševčík).",
        "required",
    )
    if dissolved:
        add(
            "analyte", "Redox-active analyte", meta.analyte,
            "provided" if meta.analyte else "missing",
            "Needed to search for studies of the same redox couple.", "required",
        )
    electrolyte = parse_electrolyte(meta.electrolyte or "")
    add(
        "electrolyte", "Electrolyte (salt and concentration)", meta.electrolyte,
        "provided" if meta.electrolyte else "missing",
        "Side reactions, the usable potential window and literature comparability depend on it.",
        "required",
    )
    if meta.electrolyte and not electrolyte["concentrations"]:
        add(
            "electrolyte_concentration", "Electrolyte concentration", None, "missing",
            "Ion concentration shifts insertion potentials and affects conductivity; "
            "write it as e.g. '1 M LiCl'.",
        )
    add(
        "solvent", "Solvent", None if meta.solvent == "unknown" else meta.solvent,
        "missing" if meta.solvent == "unknown" else "provided",
        "Aqueous and non-aqueous electrolytes have different stability windows and side reactions.",
        "required",
    )
    add(
        "reference_electrode", "Reference electrode",
        reference_label(meta.reference_electrode, meta.reference_detail) if meta.reference_electrode else None,
        "provided" if meta.reference_electrode else "missing",
        "Peak potentials can only be compared with literature on the same reference scale.",
        "required",
    )
    entered = scan_rate_v_s(meta)
    if entered is not None:
        status, value = "provided", fmt_scan_rate(entered)
        if measured_scan_rate is not None:
            value += f" (time column: {fmt_scan_rate(measured_scan_rate)})"
    elif measured_scan_rate is not None:
        status, value = "measured", f"{fmt_scan_rate(measured_scan_rate)} (from time column)"
    else:
        status, value = "missing", None
    add(
        "scan_rate", "Scan rate", value, status,
        "Peak currents, peak separations and current ratios all depend on scan rate; "
        "it is also needed to integrate charge when no time column is mapped.",
        "required",
    )
    if dissolved:
        conc = meta.analyte_concentration
        add(
            "analyte_concentration", "Analyte concentration",
            f"{conc.value:g} {conc.unit}" if conc and conc.value is not None else None,
            "provided" if conc and conc.value is not None else "missing",
            "Needed for the Randles–Ševčík peak-current check (catches dilution or preparation errors).",
        )
        add(
            "diffusion_coefficient", "Diffusion coefficient (optional)",
            f"{meta.diffusion_coefficient_cm2_s:g} cm² s⁻¹" if meta.diffusion_coefficient_cm2_s else None,
            "provided" if meta.diffusion_coefficient_cm2_s else "missing",
            "Enables the Randles–Ševčík comparison; BenchCheck does not assume a value.",
            "optional",
        )
    if material:
        add(
            "active_mass", "Active-material mass",
            f"{meta.active_mass_mg:g} mg" if meta.active_mass_mg else None,
            "provided" if meta.active_mass_mg else "missing",
            "Needed to compare specific currents/capacities with literature.",
        )
    add(
        "electrode_area", "Electrode area",
        f"{meta.electrode_area_cm2:g} cm²" if meta.electrode_area_cm2 else None,
        "provided" if meta.electrode_area_cm2 else "missing",
        "Needed for current density and for the Randles–Ševčík check.",
    )
    add(
        "temperature", "Temperature",
        f"{meta.temperature_c:g} °C" if meta.temperature_c is not None else "25 °C (assumed)",
        "provided" if meta.temperature_c is not None else "assumed",
        "Nernstian slopes and reaction rates depend on temperature.",
    )
    if meta.solvent != "non-aqueous":
        add(
            "ph", "pH", f"{meta.ph:g}" if meta.ph is not None else None,
            "provided" if meta.ph is not None else "missing",
            "Water oxidation/reduction potentials shift by about 59 mV per pH unit at 25 °C; "
            "needed for RHE conversion.",
        )
    add(
        "counter_electrode", "Counter electrode", meta.counter_electrode,
        "provided" if meta.counter_electrode else "missing",
        "Counter-electrode products can diffuse to the working electrode in undivided cells.",
        "optional",
    )
    add(
        "ir_compensation", "iR compensation", meta.ir_compensation,
        "provided" if meta.ir_compensation else "missing",
        "Uncompensated resistance shifts and broadens peaks.",
        "optional",
    )
    return rows
