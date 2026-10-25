"""Next-check catalog and a transparent ranking rule.

A check is ranked by (1) whether it addresses a data-quality problem that would
invalidate interpretation, (2) how many triggered hypotheses it can distinguish,
(3) how many of those have condition-matched literature evidence, and (4) effort.
The reasons are returned with every ranked check; there are no hidden scores.
"""

from __future__ import annotations

from ..cv.units import fmt_scan_rate, fmt_sig
from ..evidence.conditions import user_material_profile
from .hypotheses import ELEMENT_NAMES, RULES

EFFORT_RANK = {"quick": 0, "moderate": 1, "instrument": 2}
EFFORT_LABEL = {"quick": "quick (same cell)", "moderate": "moderate (new electrode or several runs)",
                "instrument": "needs another instrument"}

CHECKS: dict[str, dict] = {
    "vertex_window": {
        "title": "Repeat with the forward vertex pulled back",
        "procedure": ("Run one or two cycles at the same scan rate with the forward vertex moved 50–100 mV back "
                      "toward the last forward peak (keep it past the peak). Compare the return/forward peak and "
                      "charge ratios with this run."),
        "tests": {
            "side_reaction_vertex": "If the vertex current rise disappears and the charge ratio moves toward 1, extra "
                                    "charge at the vertex was the main cause.",
            "irreversible_loss": "If the return peaks also recover, the loss is driven by the high-potential excursion; "
                                 "if not, it happens elsewhere in the cycle.",
            "progressive_degradation": "If cycle-to-cycle fading slows, the degradation is linked to the vertex region.",
        },
        "effort": "quick",
    },
    "blank_cv": {
        "title": "Run a blank CV without the active material",
        "procedure": ("Cycle the bare substrate or a carbon/binder electrode without the active material in the same "
                      "electrolyte and potential window."),
        "tests": {"side_reaction_vertex": "A similar vertex current on the blank points to the electrolyte or "
                                          "substrate rather than the active material."},
        "effort": "moderate",
    },
    "scan_rate_series": {
        "title": "Scan-rate series",
        "procedure": ("Record CVs at 4–6 scan rates spanning at least 10× ({rates}) in random order over the same "
                      "window, then repeat the first rate to check for drift. Plot the return/forward ratio and ΔEp "
                      "against scan rate, and log(peak current) against log(scan rate)."),
        "tests": {
            "irreversible_loss": "A ratio that rises toward 1 at faster scans points to a time-dependent chemical "
                                 "step after electron transfer.",
            "ec_chemical_step": "A ratio that rises toward 1 at faster scans is the classic signature of a following "
                                "chemical reaction.",
            "kinetic_limitation": "ΔEp growing with scan rate indicates kinetic or resistive limitation; ΔEp that "
                                  "tracks peak current suggests iR drop.",
            "asymmetric_return": "A return peak that sharpens at slower scans indicates a slower return process.",
            "electrode_fouling": "Fouling usually progresses with time and cycling rather than with scan rate.",
        },
        "effort": "moderate",
    },
    "icp_electrolyte": {
        "title": "Measure dissolved electrode metals in the electrolyte",
        "procedure": ("After cycling, sample the electrolyte and measure dissolved {elements} by ICP-OES (or AAS) next "
                      "to a fresh-electrolyte blank. Record every dilution step (aliquot and final volumes) and "
                      "back-calculate; double-check the dilution-factor arithmetic before interpreting."),
        "tests": {
            "progressive_degradation": "Dissolved metal above the blank that grows with cycling supports dissolution.",
            "irreversible_loss": "No dissolved metal above the blank argues against dissolution as the cause of the "
                                 "missing return charge.",
        },
        "effort": "instrument",
        "requires_elements": True,
    },
    "ir_check": {
        "title": "Measure the uncompensated resistance",
        "procedure": ("Measure R_u (EIS high-frequency intercept or current interrupt), then repeat with iR "
                      "compensation, or recompute ΔEp after correcting the potential for i·R_u."),
        "tests": {
            "kinetic_limitation": "If correcting for i·R_u removes most of the extra ΔEp, resistance rather than "
                                  "kinetics dominates.",
            "asymmetric_return": "If correction makes the peaks symmetric, resistance caused the asymmetry.",
        },
        "effort": "quick",
    },
    "extend_return_vertex": {
        "title": "Extend the return vertex",
        "procedure": "Extend the return vertex by 100–200 mV (inside the electrolyte stability window) and repeat.",
        "tests": {"truncated_return": "A return peak appearing beyond the old vertex confirms truncation."},
        "effort": "quick",
    },
    "reference_check": {
        "title": "Check the reference electrode",
        "procedure": ("Measure the open-circuit potential between your reference and a fresh or master reference in "
                      "the same electrolyte, or record a known redox standard (e.g., ferri/ferrocyanide in water, "
                      "ferrocene in organic solvents) and compare its E½ with the expected value. Inspect the filling "
                      "solution and frit."),
        "tests": {"reference_uncertainty": "A stable, small offset allows a confirmed conversion; a large or drifting "
                                           "offset means the reference needs attention."},
        "effort": "quick",
    },
    "concentration_check": {
        "title": "Verify concentration and electrode area",
        "procedure": ("Recalculate the dilution from the stock (masses, volumes, dilution factors), prepare a fresh "
                      "standard if possible, and calibrate the electrode area with a redox standard of known D."),
        "tests": {"concentration_or_area": "If corrected values bring the Randles–Ševčík ratio near 1, the "
                                           "discrepancy was a preparation or area error."},
        "effort": "moderate",
    },
    "electrode_cleaning": {
        "title": "Clean the electrode and repeat the first cycles",
        "procedure": "Polish or electrochemically clean the working electrode, then record the first two cycles again.",
        "tests": {"electrode_fouling": "Recovered first-cycle currents after cleaning point to surface fouling."},
        "effort": "quick",
    },
}

QUALITY_CHECKS = {
    "no_return_sweep": {
        "title": "Record the return sweep",
        "procedure": "Run a full cycle (forward and return sweeps) over the same window so reversibility, peak "
                     "separation and charge balance can be assessed.",
    },
    "clipping": {
        "title": "Re-record with a larger current range",
        "procedure": "Increase the potentiostat current range (or disable autoranging limits) and repeat; clipped "
                     "currents make peak heights and ratios unreliable.",
    },
    "scan_rate_mismatch": {
        "title": "Confirm the scan rate",
        "procedure": "Compare the instrument method with the entered scan rate and correct whichever is wrong before "
                     "interpreting rate-dependent features.",
    },
    "sign_convention_hint": {
        "title": "Confirm the current sign convention",
        "procedure": "Check whether the instrument exports cathodic currents as positive (US convention) and set the "
                     "convention in BenchCheck accordingly.",
    },
}

CHARACTERIZATION = {
    "id": "rate_characterization",
    "title": "Characterize rate behavior with a scan-rate series",
    "procedure": ("No troubleshooting rule was triggered. To characterize the process, record 4–6 scan rates spanning "
                  "at least 10× ({rates}); fit log(peak current) against log(scan rate): a slope near 0.5 indicates "
                  "diffusion-limited behavior and near 1 surface-limited (capacitive or thin-film) behavior."),
    "effort": "moderate",
}


def _rates_text(v: float | None) -> str:
    if not v:
        return "e.g., 0.5×, 1×, 2×, 5× and 10× your current rate"
    rates = [v * k for k in (0.5, 1, 2, 5, 10)]
    if max(rates) < 0.1:
        return "e.g., " + ", ".join(f"{float(fmt_sig(r * 1e3)):g}" for r in rates[:-1]) + \
            f" and {float(fmt_sig(rates[-1] * 1e3)):g} mV s⁻¹"
    return "e.g., " + ", ".join(fmt_scan_rate(r) for r in rates)


def _cycle_minutes(analysis: dict) -> float | None:
    sel = analysis.get("selected") or {}
    fwd, ret = sel.get("forward"), sel.get("return")
    v = analysis.get("scan_rate_measured") or analysis.get("scan_rate_entered")
    if not (fwd and v):
        return None
    span = abs(fwd["e_end"] - fwd["e_start"]) + (abs(ret["e_end"] - ret["e_start"]) if ret else 0)
    return span / v / 60.0


def rank_checks(analysis: dict, hypotheses: list[dict], evidence_status: dict[str, str]) -> list[dict]:
    triggered = {h["id"]: h for h in hypotheses if h["triggered"]}
    meta = analysis.get("metadata") or {}
    v = analysis.get("scan_rate_measured") or analysis.get("scan_rate_entered")
    profile = user_material_profile(meta.get("electrode_material"))
    elements = [ELEMENT_NAMES[e] for e in profile["elements"] if e in ELEMENT_NAMES]
    minutes = _cycle_minutes(analysis)
    ranked = []

    for q in analysis.get("quality", []):
        if q["code"] in QUALITY_CHECKS and q["severity"] in ("high", "warning"):
            qc = QUALITY_CHECKS[q["code"]]
            ranked.append({
                "id": f"quality_{q['code']}", "title": qc["title"], "procedure": qc["procedure"], "tests": [],
                "effort": "quick", "effort_note": EFFORT_LABEL["quick"],
                "reasons": [f"Data-quality flag: {q['message']}", "Resolve before interpreting the hypotheses."],
                "_key": (0, 0, 0, 0, 0),
            })

    for order, (cid, c) in enumerate(CHECKS.items()):
        tested = [h for h in c["tests"] if h in triggered]
        if not tested:
            continue
        if c.get("requires_elements") and (meta.get("process_type") != "electrode_material" or not elements):
            continue
        matched = [h for h in tested if evidence_status.get(h) == "condition-matched"]
        related = [h for h in tested if evidence_status.get(h) == "related"]
        reasons = [f"Distinguishes {len(tested)} of {len(triggered)} triggered hypotheses: "
                   + "; ".join(RULES[h].title for h in tested) + "."]
        if matched:
            reasons.append("Condition-matched literature was retrieved for: " + "; ".join(RULES[h].title for h in matched) + ".")
        elif related:
            reasons.append("Only literature with different or partly matching conditions was retrieved for these.")
        elif evidence_status:
            reasons.append("No supporting passage was retrieved for these hypotheses; ranking uses the data alone.")
        note = EFFORT_LABEL[c["effort"]]
        if c["effort"] == "quick" and minutes and cid == "vertex_window":
            note += f"; about {minutes:.0f} min per cycle at your scan rate"
        reasons.append(f"Effort: {note}.")
        procedure = c["procedure"].format(rates=_rates_text(v), elements=" and ".join(elements) or "metals")
        ranked.append({
            "id": cid, "title": c["title"], "procedure": procedure,
            "tests": [{"id": h, "title": RULES[h].title, "outcome": c["tests"][h]} for h in tested],
            "effort": c["effort"], "effort_note": note, "reasons": reasons,
            "_key": (1, -len(tested), -len(matched), -len(related), EFFORT_RANK[c["effort"]], order),
        })

    if not triggered:
        ranked.append({
            "id": CHARACTERIZATION["id"], "title": CHARACTERIZATION["title"],
            "procedure": CHARACTERIZATION["procedure"].format(rates=_rates_text(v)), "tests": [],
            "effort": CHARACTERIZATION["effort"], "effort_note": EFFORT_LABEL[CHARACTERIZATION["effort"]],
            "reasons": ["No troubleshooting rule was triggered by the measured features.",
                        "A scan-rate series is the standard next characterization step."],
            "_key": (2, 0, 0, 0, 1, 0),
        })
    ranked.sort(key=lambda r: r["_key"])
    for k, r in enumerate(ranked, start=1):
        r["rank"] = k
        del r["_key"]
    return ranked


def metadata_checks(analysis: dict) -> list[dict]:
    rows = analysis.get("metadata_status") or []
    return [
        {"field": r["field"], "label": r["label"], "why": r["why"], "importance": r["importance"]}
        for r in rows if r["status"] == "missing" and r["importance"] in ("required", "recommended")
    ]
