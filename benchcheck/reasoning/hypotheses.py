"""Hypothesis rules.

Each rule is triggered only by measured features (with the threshold shown to
the user), states its assumptions explicitly, names the checks that would
distinguish it, and lists the terms used to retrieve and match literature.
Rules never assign a peak to a mechanism: they propose hypotheses to test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..cv.reference import FARADAY, GAS_CONSTANT
from ..cv.units import display_current_unit, fmt_current, fmt_mv, fmt_potential, fmt_scan_rate
from ..evidence.conditions import material_by_key, parse_electrolyte, user_material_profile

THRESHOLDS = {
    "ratio_low": 0.70,
    "charge_ratio_low": 0.85,
    "charge_recovered": 0.90,
    "delta_ep_dissolved_v": 0.080,
    "delta_ep_material_v": 0.100,
    "fade_pct": -10.0,
    "mid_drift_v": 0.020,
    "width_ratio_high": 1.3,
    "rs_low": 0.75,
    "rs_high": 1.33,
}

# Canonical search tokens for dictionary materials (what Google Scholar indexes well).
SEARCH_TOKENS = {
    "lmo": "LiMn2O4", "lambda_mno2": "λ-MnO2", "mn_ion_sieve": "H1.6Mn1.6O4", "lnmo": "LiNi0.5Mn1.5O4",
    "mno2": "MnO2", "lfp": "LiFePO4", "lco": "LiCoO2", "nmc": "NMC cathode", "lto": "Li4Ti5O12",
    "pba": "Prussian blue analogue", "ferricyanide": "ferricyanide", "ferrocene": "ferrocene",
    "graphite": "graphite", "glassy_carbon": "glassy carbon",
}
ELEMENT_NAMES = {"Mn": "manganese", "Ni": "nickel", "Co": "cobalt", "Fe": "iron", "Cu": "copper", "Zn": "zinc",
                 "Ti": "titanium", "V": "vanadium", "Cr": "chromium", "Mo": "molybdenum", "W": "tungsten", "Nb": "niobium"}


@dataclass
class Term:
    label: str
    pattern: str
    weight: float = 1.0
    case_sensitive: bool = False


@dataclass
class Rule:
    id: str
    title: str
    applies_to: tuple[str, ...]
    statement: str
    trigger_rule: str
    assumptions: list[str]
    checks: list[str]
    terms: list[Term] = field(default_factory=list)
    background: str | None = None


T = Term
RULES: dict[str, Rule] = {}


def _rule(r: Rule) -> None:
    RULES[r.id] = r


_rule(Rule(
    id="side_reaction_vertex",
    title="Side reaction near the forward vertex",
    applies_to=("electrode_material", "dissolved_species", "unknown"),
    statement=("A side reaction near the forward vertex (for example electrolyte or solvent oxidation/reduction) "
               "may pass extra charge on the forward sweep that is not recovered on the return sweep."),
    trigger_rule="Current magnitude still increasing over the last 30 mV before the forward vertex, by more than "
                 "15% of the largest forward peak height.",
    assumptions=[
        "The rising vertex current is Faradaic, not an instrument or capacitive artifact.",
        "In aqueous electrolytes, oxygen evolution (positive vertex) or hydrogen evolution (negative vertex) are "
        "common candidates; their onset depends on pH, electrode surface and temperature.",
    ],
    checks=["vertex_window", "blank_cv"],
    terms=[
        T("oxygen evolution", r"oxygen evolution|O2 evolution|evolution of oxygen", 2.0),
        T("OER", r"\bOER\b", 2.0, True),
        T("hydrogen evolution", r"hydrogen evolution|H2 evolution", 2.0),
        T("HER", r"\bHER\b", 1.5, True),
        T("side reaction", r"side[- ]reactions?|parasitic", 1.5),
        T("water oxidation/splitting", r"water (?:oxidation|splitting|decomposition|electrolysis)", 1.5),
        T("electrolyte decomposition", r"electrolyte (?:decomposition|oxidation)|decomposition of (?:the )?electrolyte", 1.5),
        T("gas evolution", r"gas evolution|bubbl", 1.0),
        T("stability window", r"(?:electrochemical )?stability window|potential window", 0.5),
    ],
))
_rule(Rule(
    id="irreversible_loss",
    title="Charge from the forward sweep is not recovered",
    applies_to=("electrode_material", "unknown"),
    statement=("Part of the material oxidized (or reduced) on the forward sweep may not return on the return sweep, "
               "for example through an irreversible chemical or structural change, or loss (dissolution) of the "
               "charged state."),
    trigger_rule="Return/forward charge ratio below 0.85, or return/forward peak-height ratio below 0.70, or a "
                 "forward peak without a return counterpart.",
    assumptions=[
        "Charge ratios use net sweep charge, which includes capacitive current and any side reaction.",
        "Peak heights depend on the disclosed baseline; a sloping background biases them.",
    ],
    checks=["vertex_window", "icp_electrolyte", "scan_rate_series"],
    terms=[
        T("dissolution", r"dissol(?:ution|ve|ved|ving)", 2.0),
        T("irreversible", r"irreversib", 1.5),
        T("capacity loss/fading", r"capacity (?:loss|fad|decay)", 1.5),
        T("coulombic efficiency", r"coulombic efficienc", 1.5),
        T("loss of active material", r"loss of (?:the )?active|active material loss", 1.5),
        T("disproportionation", r"disproportionat", 1.5),
        T("structural change", r"structural (?:change|degradation|transformation|instability)|phase transformation", 1.0),
        T("Mn2+", r"Mn2\+|Mn\(II\)|Mn²⁺", 1.0, True),
    ],
    background=("For a chemical step that follows electron transfer, the return/forward ratio typically increases "
                "toward 1 at faster scan rates (less time for the chemical step); textbook diagnostic criteria, "
                "e.g. Nicholson & Shain, Anal. Chem. 1964, 36, 706."),
))
_rule(Rule(
    id="ec_chemical_step",
    title="Chemical step consumes the forward-sweep product",
    applies_to=("dissolved_species",),
    statement=("A chemical reaction may consume the product formed on the forward sweep before it can react on the "
               "return sweep (EC-type behavior), or the product may precipitate or diffuse away."),
    trigger_rule="Nicholson return/forward ratio (or peak-height ratio if unavailable) below 0.70, or no return peak.",
    assumptions=[
        "The redox species is dissolved and its transport is diffusion-controlled (semi-infinite planar diffusion).",
        "Nicholson's empirical ratio assumes negligible charging current.",
    ],
    checks=["scan_rate_series"],
    terms=[
        T("follow-up chemical reaction", r"(?:follow(?:ing|-up)|coupled|subsequent) chemical (?:reaction|step)", 2.0),
        T("EC mechanism", r"\bEC\b mechanism|\bEC'?\b process|ECE", 1.5, True),
        T("irreversible", r"irreversib", 1.5),
        T("peak current ratio", r"peak current ratio|ratio of (?:the )?(?:anodic|cathodic|peak)", 1.5),
        T("decomposition", r"decompos", 1.0),
        T("dimerization/precipitation", r"dimeri[sz]|precipitat|polymeri[sz]", 1.0),
    ],
    background=("For an EC mechanism the ratio rises toward 1 as the scan rate increases (Nicholson & Shain, "
                "Anal. Chem. 1964, 36, 706; Nicholson, Anal. Chem. 1966, 38, 1406)."),
))
_rule(Rule(
    id="progressive_degradation",
    title="Electrochemically active material decreases over cycles",
    applies_to=("electrode_material", "unknown"),
    statement=("The amount of electrochemically active material may decrease from cycle to cycle, for example "
               "through dissolution, loss of electrical contact, or structural degradation."),
    trigger_rule="Height of the tracked forward peak decreases by more than 10% from the first to the last complete "
                 "cycle.",
    assumptions=["The tracked forward peak corresponds to the same process in every cycle."],
    checks=["icp_electrolyte", "vertex_window"],
    terms=[
        T("capacity fading", r"capacity (?:fad|retention|decay|loss)", 2.0),
        T("dissolution", r"dissol(?:ution|ve|ved|ving)", 2.0),
        T("degradation", r"degrad", 1.5),
        T("cycling stability", r"cycl(?:ing|e) (?:stability|performance|life)", 1.0),
        T("Jahn–Teller", r"Jahn[–-]Teller", 1.0),
        T("structural change", r"structural (?:change|degradation|transformation|instability)", 1.0),
    ],
))
_rule(Rule(
    id="electrode_fouling",
    title="Electrode surface fouling or analyte depletion",
    applies_to=("dissolved_species",),
    statement="The electrode surface may become progressively blocked (fouling or passivation), or the analyte may be "
              "depleted near the electrode, lowering peak currents over cycles.",
    trigger_rule="Height of the tracked forward peak decreases by more than 10% from the first to the last complete cycle.",
    assumptions=["The solution is not stirred between cycles and the bulk concentration is unchanged."],
    checks=["electrode_cleaning", "scan_rate_series"],
    terms=[
        T("fouling", r"foul", 2.0), T("passivation", r"passivat", 2.0), T("adsorption", r"adsorpt|adsorb", 1.0),
        T("film formation", r"film formation|polymer film|deposit", 1.0),
    ],
))
_rule(Rule(
    id="kinetic_limitation",
    title="Slow kinetics or uncompensated resistance",
    applies_to=("electrode_material", "dissolved_species", "unknown"),
    statement=("Slow electron or ion transfer, or uncompensated resistance (iR drop), may increase the separation "
               "between forward and return peaks."),
    trigger_rule="Peak separation ΔEp above 80 mV (dissolved species, n = 1 assumed) or above 100 mV (electrode "
                 "materials).",
    assumptions=[
        "For a reversible one-electron couple in solution ΔEp ≈ 57–59 mV at 25 °C; an ideal surface-confined "
        "couple has ΔEp ≈ 0.",
        "Insertion electrodes commonly show some peak separation even at slow rates.",
    ],
    checks=["ir_check", "scan_rate_series"],
    terms=[
        T("peak separation", r"peak (?:potential )?separation|ΔEp|potential (?:gap|separation)", 2.0),
        T("polarization", r"polari[sz]ation", 1.5),
        T("iR / ohmic drop", r"\biR\b|ohmic (?:drop|resistance)|uncompensated", 1.5, False),
        T("charge-transfer resistance", r"charge[- ]transfer resistance|\bRct\b", 1.5),
        T("kinetics", r"kinetic|sluggish|rate constant", 1.0),
        T("diffusion", r"diffusion (?:coefficient|limited|controlled)", 1.0),
    ],
))
_rule(Rule(
    id="asymmetric_return",
    title="Return process is broader or slower, but charge is recovered",
    applies_to=("electrode_material", "unknown"),
    statement=("The return process may be kinetically slower or spread over a wider potential range than the "
               "forward process, making the return peak lower even though most of the charge comes back."),
    trigger_rule="Return/forward peak-height ratio below 0.70 while the charge ratio is at least 0.90, or the return "
                 "peak is more than 1.3× wider than the forward peak.",
    assumptions=["Peak widths are measured at half height above the disclosed baseline."],
    checks=["scan_rate_series", "ir_check"],
    terms=[
        T("asymmetric", r"asymmetr", 2.0), T("hysteresis", r"hysteres", 1.5), T("kinetics", r"kinetic|sluggish", 1.0),
        T("polarization", r"polari[sz]ation", 1.0), T("phase transition", r"phase transition|two-phase", 1.0),
    ],
))
_rule(Rule(
    id="truncated_return",
    title="Return sweep ends before the return wave is complete",
    applies_to=("electrode_material", "dissolved_species", "unknown"),
    statement="The return sweep may end before the return wave is complete, so the return peak is truncated or "
              "not reached.",
    trigger_rule="No return peak for the main forward peak and the return-sweep current is still increasing at the "
                 "return vertex, or the return peak lies within one peak width of the vertex.",
    assumptions=["General CV practice; no literature retrieval is needed for this check."],
    checks=["extend_return_vertex"],
))
_rule(Rule(
    id="reference_uncertainty",
    title="Reference potential unknown or unstable",
    applies_to=("electrode_material", "dissolved_species", "unknown"),
    statement="An unknown, unstable or offset reference potential may shift peak positions, which limits comparison "
              "with literature values.",
    trigger_rule="Reference electrode not specified or a pseudo-reference used, or the midpoint potential drifts by "
                 "more than 20 mV across cycles.",
    assumptions=["Peak-potential comparisons need a common, verified reference scale."],
    checks=["reference_check"],
    terms=[
        T("reference electrode", r"reference electrode", 1.5), T("calibration", r"calibrat", 1.0),
        T("drift", r"\bdrift", 1.0), T("ferrocene", r"ferrocen", 1.0),
    ],
))
_rule(Rule(
    id="concentration_or_area",
    title="Concentration or electrode area differs from the assumed value",
    applies_to=("dissolved_species",),
    statement="The analyte concentration or electrode area may differ from the entered values (for example a dilution "
              "or preparation error), changing the peak current.",
    trigger_rule="Measured forward peak current outside 0.75–1.33× the Randles–Ševčík value computed from the entered "
                 "concentration, area, diffusion coefficient and n.",
    assumptions=[
        "Reversible, diffusion-controlled electron transfer (Randles–Ševčík); quasi-reversible kinetics lower the peak.",
        "The entered diffusion coefficient applies to this electrolyte and temperature.",
    ],
    checks=["concentration_check"],
    terms=[
        T("Randles–Ševčík", r"Randles", 2.0), T("diffusion coefficient", r"diffusion coefficient", 1.5),
        T("peak current", r"peak current", 1.0), T("concentration", r"concentration", 0.5),
    ],
))


def material_search_token(material_text: str | None) -> str | None:
    profile = user_material_profile(material_text)
    for key in profile["keys"]:
        if key in SEARCH_TOKENS:
            return SEARCH_TOKENS[key]
    if material_text:
        return material_text.split("(")[0].split(",")[0].strip().split(" ")[0] or None
    return None


def summarize(analysis: dict) -> dict:
    sel = analysis.get("selected") or {}
    meta = analysis.get("metadata") or {}
    pairs = sel.get("pairs") or []
    main = pairs[sel["main_pair"]] if sel.get("main_pair") is not None and sel["main_pair"] < len(pairs) else None
    ratios = [p["height_ratio"] for p in pairs if p.get("height_ratio") is not None]
    nich = [p["nicholson_ratio"] for p in pairs if p.get("nicholson_ratio") is not None]
    fwd, ret = sel.get("forward") or {}, sel.get("return") or {}
    display = analysis.get("display") or {}
    heights = [abs(p.get("height") or 0) for s in (fwd, ret) for p in s.get("peaks", [])]
    unit, scale = display_current_unit(max(heights) if heights else 1e-3, bool(display.get("density")))
    return {
        "process_type": meta.get("process_type") or "unknown",
        "solvent": meta.get("solvent") or "unknown",
        "forward_direction": analysis.get("forward_direction"),
        "pairs": pairs,
        "main_pair": main,
        "min_ratio": min(ratios) if ratios else None,
        "min_nicholson": min(nich) if nich else None,
        "charge_ratio": sel.get("charge_ratio"),
        "forward": fwd,
        "return": ret,
        "unpaired_forward": sel.get("unpaired_forward") or [],
        "main_forward_peak": sel.get("main_forward_peak"),
        "trends": analysis.get("trends"),
        "quality_codes": [q["code"] for q in analysis.get("quality", [])],
        "metadata": meta,
        "scan_rate": analysis.get("scan_rate_measured") or analysis.get("scan_rate_entered"),
        "unit": unit,
        "scale": scale,
        "potential_label": display.get("potential_label", "V"),
        "density": bool(display.get("density")),
        "selected_cycle": sel.get("number"),
    }


def _cur(f: dict, x: float) -> str:
    return fmt_current(x, f["unit"], f["scale"], signed=False)


def _randles_sevcik(f: dict) -> dict | None:
    meta = f["metadata"]
    conc = meta.get("analyte_concentration") or {}
    area = meta.get("electrode_area_cm2")
    d = meta.get("diffusion_coefficient_cm2_s")
    v = f["scan_rate"]
    if not (conc.get("value") and area and d and v):
        return None
    unit = (conc.get("unit") or "mM").strip()
    molar = conc["value"] * {"M": 1., "mol/L": 1., "mM": 1e-3, "mmol/L": 1e-3, "uM": 1e-6, "µM": 1e-6, "μM": 1e-6, "nM": 1e-9}[unit]
    n = meta.get("electrons_n") or 1
    t_k = (meta.get("temperature_c") if meta.get("temperature_c") is not None else 25.0) + 273.15
    expected = 0.4463 * n * FARADAY * area * (molar * 1e-3) * math.sqrt(n * FARADAY * v * d / (GAS_CONSTANT * t_k))
    peak = next((p for p in f["forward"].get("peaks", []) if p["label"] == f["main_forward_peak"]), None)
    if not peak:
        return None
    measured = peak["height"] * (area if f["density"] else 1.0)
    return {"expected_a": expected, "measured_a": measured, "ratio": measured / expected, "n": n,
            "n_assumed": meta.get("electrons_n") is None}


def evaluate(analysis: dict) -> list[dict]:
    """Evaluate every applicable rule. Returns dicts with triggered flag, observations and reasons."""
    f = summarize(analysis)
    ptype = f["process_type"]
    th = THRESHOLDS
    out = []

    def emit(rule_id, triggered, observations, reason=None, extra=None):
        r = RULES[rule_id]
        if ptype not in r.applies_to:
            return
        d = {
            "id": r.id, "title": r.title, "statement": r.statement, "trigger_rule": r.trigger_rule,
            "assumptions": list(r.assumptions), "checks": list(r.checks), "background": r.background,
            "triggered": bool(triggered), "observations": observations if triggered else [],
            "not_triggered_reason": None if triggered else reason,
        }
        if extra:
            d.update(extra)
        out.append(d)

    fv = f["forward"].get("vertex") or {}
    rv = f["return"].get("vertex") or {}
    main = f["main_pair"]

    # Side reaction at the forward vertex
    obs = []
    if fv.get("rising"):
        obs.append(f"Forward-sweep current still rising at the vertex ({fmt_potential(fv['potential'])}): "
                   f"+{_cur(f, fv['rise'])} above the post-peak minimum ({fv['rise_fraction'] * 100:.0f}% of the "
                   "largest forward peak).")
        if f["charge_ratio"] is not None and f["charge_ratio"] < th["charge_recovered"]:
            obs.append(f"Return/forward charge ratio {f['charge_ratio']:.2f}.")
    gaps = []
    if f["solvent"] == "aqueous" and fv.get("rising") and f["metadata"].get("ph") is None:
        gaps.append("Electrolyte pH was not entered; the onset of water oxidation/reduction depends on it.")
    reason = ("Forward current does not keep rising at the vertex" +
              (f" (rise {fv['rise_fraction'] * 100:.0f}% of peak height < 15%)." if fv.get("rise_fraction") is not None else "."))
    emit("side_reaction_vertex", bool(fv.get("rising")), obs, reason, {"metadata_gaps": gaps})

    # Irreversible loss (electrode materials)
    obs, trig = [], False
    if f["charge_ratio"] is not None and f["charge_ratio"] < th["charge_ratio_low"]:
        trig = True
        obs.append(f"Return/forward charge ratio {f['charge_ratio']:.2f} (< {th['charge_ratio_low']}).")
    if f["min_ratio"] is not None and f["min_ratio"] < th["ratio_low"]:
        trig = True
        weakest = min((p for p in f["pairs"] if p.get("height_ratio") is not None), key=lambda p: p["height_ratio"])
        obs.append(f"Return/forward peak-height ratio {weakest['height_ratio']:.2f} for pair "
                   f"{weakest['anodic']}/{weakest['cathodic']} (< {th['ratio_low']}).")
    if f["unpaired_forward"]:
        trig = True
        obs.append("No return peak detected for forward peak(s) " + ", ".join(f["unpaired_forward"]) + ".")
    charge_ok = f["charge_ratio"] is not None and f["charge_ratio"] >= th["charge_recovered"]
    if trig and charge_ok and not f["unpaired_forward"]:
        trig, obs = False, []  # low peak height with recovered charge is the asymmetric-return rule
    if trig and f["charge_ratio"] is None:
        obs.append("Charge ratio unavailable (no time column or scan rate), so a broader return peak with fully "
                   "recovered charge cannot be ruled out.")
    emit("irreversible_loss", trig, obs,
         "Charge and peak ratios are close to 1." if f["charge_ratio"] is not None else "Charge ratio not available "
         "(no time column or scan rate) and peak ratios are not low.")

    # EC step (dissolved species)
    obs, trig = [], False
    ratio = f["min_nicholson"] if f["min_nicholson"] is not None else f["min_ratio"]
    if ratio is not None and ratio < th["ratio_low"]:
        trig = True
        label = "Nicholson" if f["min_nicholson"] is not None else "peak-height"
        obs.append(f"Return/forward ratio ({label} estimate) {ratio:.2f} (< {th['ratio_low']}).")
    if f["unpaired_forward"]:
        trig = True
        obs.append("No return peak detected for forward peak(s) " + ", ".join(f["unpaired_forward"]) + ".")
    emit("ec_chemical_step", trig, obs, "Return/forward ratio close to 1.")

    # Progressive degradation / fouling
    tr = f["trends"] or {}
    change = tr.get("height_change_pct")
    trig = change is not None and change < th["fade_pct"]
    obs = [f"Tracked forward peak height changed by {change:+.0f}% from cycle {tr['first_cycle']} to "
           f"{tr['last_cycle']}."] if trig else []
    reason = ("Fewer than two complete cycles; trend not assessable." if change is None
              else f"Peak height change {change:+.0f}% is within ±10%.")
    emit("progressive_degradation", trig, obs, reason)
    emit("electrode_fouling", trig, obs, reason)

    # Kinetics / resistance
    limit = th["delta_ep_dissolved_v"] if ptype == "dissolved_species" else th["delta_ep_material_v"]
    seps = [p for p in f["pairs"] if p.get("delta_ep") is not None]
    big = [p for p in seps if p["delta_ep"] > limit]
    obs = [f"ΔEp = {fmt_mv(p['delta_ep'])} for {p['anodic']}/{p['cathodic']} (> {limit * 1e3:.0f} mV)." for p in big]
    emit("kinetic_limitation", bool(big), obs,
         f"All peak separations ≤ {limit * 1e3:.0f} mV." if seps else "No forward/return peak pair to measure.")

    # Asymmetric return
    obs, trig = [], False
    if f["min_ratio"] is not None and f["min_ratio"] < th["ratio_low"] and f["charge_ratio"] is not None \
            and f["charge_ratio"] >= th["charge_recovered"]:
        trig = True
        obs.append(f"Peak-height ratio {f['min_ratio']:.2f} but charge ratio {f['charge_ratio']:.2f}: the charge "
                   "comes back in a lower, broader peak.")
    wide = [p for p in f["pairs"] if p.get("width_ratio") and p["width_ratio"] > th["width_ratio_high"]]
    for p in wide:
        trig = True
        obs.append(f"Return peak {p['return']} is {p['width_ratio']:.1f}× wider than forward peak {p['forward']}.")
    emit("asymmetric_return", trig, obs, "Return peaks are not markedly lower/broader with recovered charge.")

    # Truncated return
    obs, trig = [], False
    if main is None and f["main_forward_peak"] and rv.get("rising"):
        trig = True
        obs.append(f"No return peak for {f['main_forward_peak']} and the return-sweep current is still increasing at "
                   f"the return vertex ({fmt_potential(rv['potential'])}).")
    for p in f["return"].get("peaks", []):
        if p.get("near_vertex"):
            trig = True
            obs.append(f"Return peak {p['label']} lies within one peak width of a vertex.")
    emit("truncated_return", trig, obs, "Return peaks are well inside the potential window.")

    # Reference
    meta = f["metadata"]
    obs, trig = [], False
    if not meta.get("reference_electrode"):
        trig = True
        obs.append("Reference electrode not specified.")
    elif meta.get("reference_electrode") == "pseudo":
        trig = True
        obs.append("A pseudo-reference electrode was used; its potential is not fixed.")
    if tr.get("e_mid_shift") is not None and abs(tr["e_mid_shift"]) > th["mid_drift_v"]:
        trig = True
        obs.append(f"Midpoint potential shifted {tr['e_mid_shift'] * 1e3:+.0f} mV across cycles.")
    emit("reference_uncertainty", trig, obs, "Reference electrode specified and midpoint potentials stable.")

    # Randles–Ševčík check (dissolved species)
    rs = _randles_sevcik(f) if ptype == "dissolved_species" else None
    if ptype == "dissolved_species":
        if rs is None:
            emit("concentration_or_area", False, [],
                 "Not evaluated: needs analyte concentration, electrode area, diffusion coefficient and scan rate.")
        else:
            trig = not (th["rs_low"] <= rs["ratio"] <= th["rs_high"])
            obs = [f"Measured forward peak {fmt_current(rs['measured_a'], *display_current_unit(rs['measured_a'], False), signed=False)} "
                   f"vs Randles–Ševčík {fmt_current(rs['expected_a'], *display_current_unit(rs['expected_a'], False), signed=False)} "
                   f"(ratio {rs['ratio']:.2f}" + (", n = 1 assumed" if rs["n_assumed"] else "") + ")."]
            emit("concentration_or_area", trig, obs,
                 f"Measured/expected peak current {rs['ratio']:.2f} is within 0.75–1.33.", {"randles_sevcik": rs})
    return out


# --------------------------------------------------------------------------------------
# Evidence plan: which Google Scholar queries to run for this analysis
# --------------------------------------------------------------------------------------

QUERY_PRIORITY = [
    "side_reaction_vertex", "irreversible_loss", "ec_chemical_step", "progressive_degradation", "electrode_fouling",
    "kinetic_limitation", "asymmetric_return", "concentration_or_area", "reference_uncertainty",
]


def _query_for(rule_id: str, f: dict, ctx: dict) -> str | None:
    m, salt, solv = ctx["material"], ctx["salt"], ctx["solvent_q"]
    analyte = ctx["analyte"] or m
    if not (m or analyte):
        return None
    if rule_id == "side_reaction_vertex":
        positive = f["forward_direction"] == 1
        if f["solvent"] == "aqueous":
            side = "oxygen evolution" if positive else "hydrogen evolution"
            return " ".join(x for x in (m, "aqueous", salt, side, "side reaction") if x)
        return " ".join(x for x in (m, "electrolyte", "oxidation" if positive else "reduction", "side reaction",
                                    "cyclic voltammetry") if x)
    if rule_id == "irreversible_loss":
        elements = ctx["elements"]
        diss = f"{ELEMENT_NAMES[elements[0]]} dissolution" if elements else "dissolution"
        return " ".join(x for x in (m, solv, salt, diss) if x)
    if rule_id == "progressive_degradation":
        return " ".join(x for x in (m, solv, salt, "capacity fading cycling") if x)
    if rule_id == "ec_chemical_step":
        return f"{analyte} cyclic voltammetry irreversible follow-up chemical reaction"
    if rule_id == "electrode_fouling":
        return f"{analyte} electrode fouling cyclic voltammetry"
    if rule_id == "kinetic_limitation":
        return " ".join(x for x in (m or analyte, "cyclic voltammetry peak separation scan rate kinetics") if x)
    if rule_id == "asymmetric_return":
        return " ".join(x for x in (m, solv, "asymmetric redox peaks cyclic voltammetry kinetics") if x)
    if rule_id == "concentration_or_area":
        return f"{analyte} cyclic voltammetry diffusion coefficient Randles-Sevcik"
    if rule_id == "reference_uncertainty":
        return None  # general practice; no retrieval needed for the MVP
    return None


def evidence_plan(analysis: dict, hypotheses: list[dict], max_queries: int) -> list[dict]:
    f = summarize(analysis)
    meta = f["metadata"]
    electrolyte = parse_electrolyte(meta.get("electrolyte") or "")
    profile = user_material_profile(meta.get("electrode_material"))
    ctx = {
        "material": material_search_token(meta.get("electrode_material")),
        "salt": electrolyte["salts"][0] if electrolyte["salts"] else None,
        "solvent_q": {"aqueous": "aqueous", "non-aqueous": "non-aqueous"}.get(f["solvent"]),
        "analyte": meta.get("analyte"),
        "elements": [e for e in profile["elements"] if e in ELEMENT_NAMES],
    }
    triggered = [h["id"] for h in hypotheses if h["triggered"]]
    plan = []
    subject = ctx["material"] if f["process_type"] != "dissolved_species" else (ctx["analyte"] or ctx["material"])
    if subject:
        context_q = " ".join(x for x in (subject, ctx["salt"], ctx["solvent_q"], "cyclic voltammetry") if x)
        plan.append({"id": "q_context", "query": context_q, "purpose": "Studies with matching conditions",
                     "hypotheses": triggered})
    seen = {p["query"] for p in plan}
    for rid in QUERY_PRIORITY:
        if rid not in triggered:
            continue
        q = _query_for(rid, f, ctx)
        if q and q not in seen:
            seen.add(q)
            plan.append({"id": f"q_{rid}", "query": q, "purpose": f"Evidence for: {RULES[rid].title}",
                         "hypotheses": [rid]})
    if not triggered and subject:
        q = " ".join(x for x in (subject, ctx["solvent_q"], "cyclic voltammetry scan rate diffusion") if x)
        if q not in seen:
            plan.append({"id": "q_rate", "query": q, "purpose": "Rate behavior (characterization)", "hypotheses": []})
    return plan[:max_queries]


def material_label(key: str) -> str:
    mat = material_by_key(key)
    return mat.label if mat else key


def scan_rate_text(v: float | None) -> str:
    return fmt_scan_rate(v)
