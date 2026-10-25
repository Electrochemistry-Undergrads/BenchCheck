"""Experimental-condition extraction and comparison.

The same dictionaries and patterns are applied to the user's metadata and to
retrieved literature text, so a "match" means both sides mention the same
material family, electrolyte, solvent class, reference electrode or scan-rate
regime. Extraction is deliberately conservative: anything not found is reported
as "not stated in the retrieved text", never guessed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .text import normalize


@dataclass(frozen=True)
class Material:
    key: str
    label: str
    family: str
    patterns: tuple[str, ...]
    elements: tuple[str, ...] = ()


MATERIALS: tuple[Material, ...] = (
    Material("lmo", "LiMn₂O₄ (spinel LMO)", "mn_spinel",
             (r"LiMn\s?2\s?O\s?4", r"\bLMO\b", r"lithium manganese oxide", r"lithium manganate",
              r"spinel lithium manganese"), ("Mn",)),
    Material("lambda_mno2", "λ-MnO₂", "mn_spinel", (r"λ\s*-?\s*MnO\s?2", r"lambda\s*-?\s*MnO\s?2"), ("Mn",)),
    Material("mn_ion_sieve", "Li₁.₆Mn₁.₆O₄ / H₁.₆Mn₁.₆O₄ ion sieve", "mn_spinel",
             (r"[LH]i?1\.6Mn1\.6O4", r"[LH]i?1\.33Mn1\.67O4", r"\bHMO\b"), ("Mn",)),
    Material("lnmo", "LiNi₀.₅Mn₁.₅O₄", "mn_spinel", (r"LiNi0\.5Mn1\.5O4", r"\bLNMO\b"), ("Ni", "Mn")),
    Material("mno2", "MnO₂", "mn_oxide",
             (r"(?<![λA-Za-z0-9\-])MnO2\b", r"[αβγδε]\s*-\s*MnO2", r"manganese dioxide"), ("Mn",)),
    Material("lfp", "LiFePO₄", "olivine", (r"LiFePO4", r"\bLFP\b", r"lithium iron phosphate"), ("Fe",)),
    Material("lco", "LiCoO₂", "layered_oxide", (r"LiCoO2", r"\bLCO\b", r"lithium cobalt oxide"), ("Co",)),
    Material("nmc", "LiNiMnCoO₂ (NMC)", "layered_oxide",
             (r"\bNMC\d{0,3}\b", r"\bNCM\d{0,3}\b", r"LiNi[0-9.xyz]*Mn[0-9.xyz]*Co[0-9.xyz]*O2",
              r"LiNi[0-9.xyz]*Co[0-9.xyz]*Mn[0-9.xyz]*O2"), ("Ni", "Mn", "Co")),
    Material("lto", "Li₄Ti₅O₁₂", "titanate", (r"Li4Ti5O12", r"\bLTO\b"), ("Ti",)),
    Material("pba", "Prussian blue analogue", "pba",
             (r"prussian blue", r"(?:nickel|copper|cobalt|manganese|zinc|iron) hexacyanoferrate",
              r"\b(?:Ni|Cu|Co|Mn|Zn)HCF\b", r"\bPBAs?\b"), ("Fe",)),
    Material("ferricyanide", "ferri/ferrocyanide", "dissolved_couple",
             (r"ferricyanide", r"ferrocyanide", r"Fe\(CN\)\s?6", r"potassium hexacyanoferrate"), ("Fe",)),
    Material("ferrocene", "ferrocene", "dissolved_couple", (r"ferrocen", r"Fc\s?/\s?Fc\+", r"Fc\+\s?/\s?Fc"), ("Fe",)),
    Material("graphite", "graphite", "carbon", (r"\bgraphite\b",)),
    Material("glassy_carbon", "glassy carbon", "electrode_substrate", (r"glassy carbon",)),
)

_FAMILY_LABELS = {
    "mn_spinel": "manganese-oxide spinel family",
    "mn_oxide": "manganese oxides",
    "olivine": "olivine phosphates",
    "layered_oxide": "layered oxides",
    "titanate": "titanates",
    "pba": "Prussian blue analogues",
    "dissolved_couple": "dissolved redox couples",
    "carbon": "carbons",
    "electrode_substrate": "electrode substrates",
}

_COMPILED_MATERIALS = [(m, [re.compile(p, re.IGNORECASE if p.islower() else 0) for p in m.patterns]) for m in MATERIALS]

TRANSITION_METALS = ("Mn", "Ni", "Co", "Fe", "Cu", "Zn", "Ti", "V", "Cr", "Mo", "W", "Nb")

SALTS = (
    "LiCl", "Li2SO4", "LiNO3", "LiOH", "Li2CO3", "LiPF6", "LiClO4", "LiTFSI", "LiFSI", "LiBF4", "LiBOB",
    "NaCl", "Na2SO4", "NaNO3", "NaClO4", "NaPF6", "NaOH", "KCl", "K2SO4", "KNO3", "KOH",
    "MgCl2", "MgSO4", "CaCl2", "ZnSO4", "H2SO4", "HCl", "HClO4", "HNO3", "PBS",
    "K3Fe(CN)6", "K4Fe(CN)6", "TBAPF6", "TBAP",
)
_SALT_PATTERNS = [(s, re.compile(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])")) for s in SALTS]

_AQUEOUS = [re.compile(p, re.IGNORECASE) for p in (
    r"\baqueous\b", r"\bin water\b", r"water-in-salt", r"\bbrines?\b", r"sea\s?water", r"salt[- ]lake",
    r"geothermal", r"\bH2O\b",
)]
_NONAQUEOUS = [re.compile(p, re.IGNORECASE) for p in (
    r"non-?aqueous", r"organic electrolyte", r"ethylene carbonate", r"dimethyl carbonate", r"diethyl carbonate",
    r"propylene carbonate", r"acetonitrile", r"ionic liquid", r"\bglyme\b",
)] + [re.compile(p) for p in (r"\bEC\s*[/:]\s*(?:DMC|DEC|EMC)\b", r"\bLiPF6\b", r"\bDMSO\b")]
_BRINE = re.compile(r"\bbrines?\b|sea\s?water|salt[- ]lake|geothermal", re.IGNORECASE)

_CONC = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mM|M|mol\s?(?:L|dm|dm3)\s?-\s?1|mol\s?(?:L|dm3?)\^?-1|mol/L|mol\s?kg\s?-\s?1|mol/kg)"
    r"\s+(?:of\s+)?(" + "|".join(re.escape(s) for s in SALTS) + r")(?![A-Za-z0-9])"
)

# Reference electrodes: family key -> patterns (searched in normalized text).
_REFERENCES = (
    ("ag_agcl", r"Ag\s?/\s?AgCl|silver[ -/]silver chloride"),
    ("sce", r"\bSCE\b|saturated calomel"),
    ("hg_hgo", r"Hg\s?/\s?HgO"),
    ("mse", r"Hg\s?/\s?Hg2SO4|\bMSE\b|mercury(?:ous)? sulfate"),
    ("li", r"Li\s?/\s?Li\s?\+|Li\s?\+\s?/\s?Li\b|\bvs\.?\s?Li\b|versus Li\b|lithium metal (?:as )?(?:the )?reference"),
    ("na", r"Na\s?/\s?Na\s?\+|Na\s?\+\s?/\s?Na\b|\bvs\.?\s?Na\b"),
    ("rhe", r"\bRHE\b|reversible hydrogen electrode"),
    ("she", r"\bSHE\b|\bNHE\b|standard hydrogen electrode|normal hydrogen electrode"),
    ("ag_ag_plus", r"Ag\s?/\s?Ag\s?\+(?!\s?Cl)"),
    ("pseudo", r"(?:pseudo|quasi)[- ]reference"),
)
_REFERENCE_PATTERNS = [(k, re.compile(p, re.IGNORECASE)) for k, p in _REFERENCES]
REFERENCE_FAMILY_LABELS = {
    "ag_agcl": "Ag/AgCl", "sce": "SCE", "hg_hgo": "Hg/HgO", "mse": "Hg/Hg₂SO₄", "li": "Li/Li⁺",
    "na": "Na/Na⁺", "rhe": "RHE", "she": "SHE/NHE", "ag_ag_plus": "Ag/Ag⁺", "pseudo": "pseudo-reference",
    "other": "other",
}

_SCAN_UNIT = re.compile(r"(mV|uV|V)\s?(?:s\s?-\s?1|s\^?-1|/\s?s(?:ec)?\b|per\s+s(?:econd)?)")
_NUM_LIST_TAIL = re.compile(r"((?:\d+(?:\.\d+)?\s*(?:,|;|and|or|to|-|&|\s)\s*)*\d+(?:\.\d+)?)\s*$")


@dataclass
class Found:
    value: str
    excerpt: str
    location: str
    start: int
    end: int


@dataclass
class ExtractedConditions:
    materials: list[Found] = field(default_factory=list)
    salts: list[Found] = field(default_factory=list)
    concentrations: list[dict] = field(default_factory=list)
    solvent: dict = field(default_factory=dict)
    references: list[Found] = field(default_factory=list)
    scan_rates_v_s: list[float] = field(default_factory=list)
    scan_rate_ranges: list[tuple[float, float]] = field(default_factory=list)
    scan_rate_excerpts: list[Found] = field(default_factory=list)


def _excerpt(original: str, start: int, end: int, pad: int = 40) -> str:
    a = max(0, start - pad)
    b = min(len(original), end + pad)
    prefix = "…" if a > 0 else ""
    suffix = "…" if b < len(original) else ""
    return prefix + re.sub(r"\s+", " ", original[a:b]).strip() + suffix


def find_materials(original: str, location: str = "text") -> list[Found]:
    norm = normalize(original)
    found = []
    for mat, patterns in _COMPILED_MATERIALS:
        for pat in patterns:
            m = pat.search(norm)
            if m:
                found.append(Found(mat.key, _excerpt(original, m.start(), m.end()), location, m.start(), m.end()))
                break
    return found


def material_by_key(key: str) -> Material | None:
    return next((m for m in MATERIALS if m.key == key), None)


def parse_electrolyte(original: str) -> dict:
    norm = normalize(original or "")
    salts = [s for s, pat in _SALT_PATTERNS if pat.search(norm)]
    concentrations = []
    for m in _CONC.finditer(norm):
        value = float(m.group(1))
        unit = m.group(2).replace(" ", "")
        if unit.lower().startswith("mol") and "kg" in unit.lower():
            molar, unit_label = None, "mol/kg"
        elif unit == "mM":
            molar, unit_label = value * 1e-3, "mM"
        else:
            molar, unit_label = value, "M"
        concentrations.append({"salt": m.group(3), "value": value, "unit": unit_label, "molar": molar,
                               "text": original[m.start():m.end()]})
    aqueous = any(p.search(norm) for p in _AQUEOUS)
    nonaq = any(p.search(norm) for p in _NONAQUEOUS)
    solvent = "both mentioned" if aqueous and nonaq else "aqueous" if aqueous else "non-aqueous" if nonaq else None
    return {"salts": salts, "concentrations": concentrations, "solvent": solvent, "brine": bool(_BRINE.search(norm))}


def find_references(original: str, location: str = "text") -> list[Found]:
    norm = normalize(original)
    found = []
    for key, pat in _REFERENCE_PATTERNS:
        m = pat.search(norm)
        if m:
            found.append(Found(key, _excerpt(original, m.start(), m.end()), location, m.start(), m.end()))
    return found


def find_scan_rates(original: str, location: str = "text") -> tuple[list[float], list[tuple[float, float]], list[Found]]:
    norm = normalize(original)
    values: list[float] = []
    ranges: list[tuple[float, float]] = []
    excerpts: list[Found] = []
    for m in _SCAN_UNIT.finditer(norm):
        unit = m.group(1)
        factor = {"mV": 1e-3, "uV": 1e-6, "V": 1.0}[unit]
        head = norm[max(0, m.start() - 60) : m.start()]
        tail = _NUM_LIST_TAIL.search(head)
        if not tail:
            continue
        chunk = tail.group(1)
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", chunk)]
        if not nums:
            continue
        # A two-number span written with "to" or a dash is a range; anything else is a list.
        if len(nums) == 2 and re.search(r"\bto\b|-", chunk):
            lo, hi = sorted(n * factor for n in nums)
            ranges.append((lo, hi))
        else:
            values.extend(n * factor for n in nums)
        start = m.start() - len(head) + tail.start()
        excerpts.append(Found(f"{chunk.strip()} {unit} s⁻¹", _excerpt(original, start, m.end(), pad=25), location, start, m.end()))
    return values, ranges, excerpts


def custom_material_pattern(material_text: str | None) -> re.Pattern | None:
    """Pattern for a user material that is not in the dictionary (e.g. 'Fe2O3')."""
    if not material_text or find_materials(material_text):
        return None
    token = normalize(material_text).split("(")[0].strip().split()[0] if material_text.strip() else ""
    if len(token) < 3:
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def extract_conditions(texts: list[tuple[str, str]], extra_material: re.Pattern | None = None) -> ExtractedConditions:
    """Run all extractors over [(location, text), ...] in priority order."""
    out = ExtractedConditions()
    seen_materials, seen_refs, seen_salts = set(), set(), set()
    solvent_votes: dict[str, str] = {}
    for location, text in texts:
        if not text:
            continue
        for f in find_materials(text, location):
            if f.value not in seen_materials:
                seen_materials.add(f.value)
                out.materials.append(f)
        if extra_material is not None and "user_material" not in seen_materials:
            m = extra_material.search(normalize(text))
            if m:
                seen_materials.add("user_material")
                out.materials.append(Found("user_material", _excerpt(text, m.start(), m.end()), location, m.start(), m.end()))
        electrolyte = parse_electrolyte(text)
        for s in electrolyte["salts"]:
            if s not in seen_salts:
                seen_salts.add(s)
                out.salts.append(Found(s, s, location, -1, -1))
        out.concentrations.extend(electrolyte["concentrations"])
        if electrolyte["solvent"] and "solvent" not in solvent_votes:
            solvent_votes["solvent"] = electrolyte["solvent"]
            solvent_votes["location"] = location
        for f in find_references(text, location):
            if f.value not in seen_refs:
                seen_refs.add(f.value)
                out.references.append(f)
        vals, rngs, exc = find_scan_rates(text, location)
        out.scan_rates_v_s.extend(vals)
        out.scan_rate_ranges.extend(rngs)
        out.scan_rate_excerpts.extend(exc)
    out.solvent = solvent_votes
    return out


# --------------------------------------------------------------------------------------
# Comparison with the user's experiment
# --------------------------------------------------------------------------------------


def user_material_profile(material_text: str | None) -> dict:
    found = find_materials(material_text or "")
    keys = [f.value for f in found]
    families = sorted({material_by_key(k).family for k in keys if material_by_key(k)})
    elements = []
    for k in keys:
        mat = material_by_key(k)
        if mat:
            elements.extend(e for e in mat.elements if e not in elements)
    if not elements and material_text:
        for el in TRANSITION_METALS:
            if re.search(el + r"(?![a-z])", material_text):
                elements.append(el)
    return {"raw": material_text, "keys": keys, "families": families, "elements": elements}


def _fmt_rate(v: float) -> str:
    return f"{v * 1e3:g} mV s⁻¹" if v < 0.1 else f"{v:g} V s⁻¹"


def compare(extracted: ExtractedConditions, user: dict) -> list[dict]:
    """Row per condition: status is match | related | differs | not_stated | user_missing."""
    rows = []

    # Material
    u = user["material"]
    paper_keys = [f.value for f in extracted.materials]

    def label_for(key: str) -> str:
        mat = material_by_key(key)
        return mat.label if mat else (u["raw"] or key)

    def family_for(key: str) -> str | None:
        mat = material_by_key(key)
        return mat.family if mat else None

    paper_labels = [label_for(k) for k in paper_keys]
    user_keys = set(u["keys"]) or ({"user_material"} if u["raw"] else set())
    if not u["raw"]:
        status, note = "user_missing", "Enter your electrode material to compare."
    elif not paper_keys:
        status, note = "not_stated", "No electrode material recognized in the retrieved text."
    elif user_keys & set(paper_keys):
        status, note = "match", "Same material as your experiment."
    elif u["families"] and {family_for(k) for k in paper_keys} & set(u["families"]):
        status = "related"
        note = (f"Related material ({_FAMILY_LABELS.get(u['families'][0], u['families'][0])}), "
                "not the same compound: behaviour may differ.")
    else:
        status = "differs"
        note = "Studies a different electrode material; mechanistic conclusions may not transfer to yours."
    rows.append({
        "condition": "Electrode material", "user": u["raw"], "paper": ", ".join(paper_labels) or None,
        "excerpt": extracted.materials[0].excerpt if extracted.materials else None,
        "location": extracted.materials[0].location if extracted.materials else None,
        "status": status, "note": note,
    })

    # Electrolyte (salt)
    ue = user["electrolyte"]
    paper_salts = [f.value for f in extracted.salts]
    if not ue["salts"]:
        status, note = "user_missing", "Enter your electrolyte (e.g., '1 M LiCl') to compare."
    elif not paper_salts:
        status, note = "not_stated", "Electrolyte salt not stated in the retrieved text."
    elif set(ue["salts"]) & set(paper_salts):
        status, note = "match", "Same electrolyte salt."
        u_conc = {c["salt"]: c["molar"] for c in ue["concentrations"] if c["molar"]}
        p_conc = {c["salt"]: c["molar"] for c in extracted.concentrations if c["molar"]}
        common = set(u_conc) & set(p_conc)
        if common:
            salt = sorted(common)[0]
            if not math.isclose(u_conc[salt], p_conc[salt], rel_tol=0.25):
                status = "related"
                note = (f"Same salt, different concentration ({p_conc[salt]:g} M vs your {u_conc[salt]:g} M): "
                        "insertion potentials and side reactions can shift.")
    else:
        status = "differs"
        note = "Different electrolyte salt: ion insertion, side reactions and peak positions may differ."
    rows.append({
        "condition": "Electrolyte", "user": user.get("electrolyte_text"),
        "paper": ", ".join(paper_salts) or None,
        "excerpt": next((c["text"] for c in extracted.concentrations), None),
        "location": extracted.salts[0].location if extracted.salts else None,
        "status": status, "note": note,
    })

    # Solvent class
    us = user["solvent"]
    ps = extracted.solvent.get("solvent")
    if us in (None, "unknown"):
        status, note = "user_missing", "Select aqueous or non-aqueous to compare."
    elif not ps:
        status, note = "not_stated", "Solvent (aqueous vs non-aqueous) not stated in the retrieved text."
    elif ps == "both mentioned":
        status, note = "related", "The text mentions both aqueous and non-aqueous electrolytes; check which applies."
    elif ps == us:
        status, note = "match", f"Also {us}."
    else:
        status = "differs"
        note = (f"{ps.capitalize()} vs your {us} electrolyte: the stability window and side reactions "
                "(e.g., water oxidation/reduction) differ, so peak behaviour is not directly comparable.")
    rows.append({
        "condition": "Solvent", "user": us if us not in (None, "unknown") else None, "paper": ps,
        "excerpt": None, "location": extracted.solvent.get("location"), "status": status, "note": note,
    })

    # Reference electrode
    ur = user["reference_family"]
    pr = [f.value for f in extracted.references]
    if not ur:
        status, note = "user_missing", "Select your reference electrode to compare potentials."
    elif not pr:
        status, note = "not_stated", "Reference electrode not stated in the retrieved text; peak potentials cannot be compared."
    elif ur in pr:
        status, note = "match", "Same reference electrode family (check the filling solution)."
    else:
        status = "differs"
        labels = ", ".join(REFERENCE_FAMILY_LABELS.get(k, k) for k in pr)
        note = (f"Potentials reported vs {labels}; yours vs {REFERENCE_FAMILY_LABELS.get(ur, ur)}. "
                "Compare peak positions only after an explicit, confirmed conversion.")
    rows.append({
        "condition": "Reference electrode", "user": REFERENCE_FAMILY_LABELS.get(ur, ur) if ur else None,
        "paper": ", ".join(REFERENCE_FAMILY_LABELS.get(k, k) for k in pr) or None,
        "excerpt": extracted.references[0].excerpt if extracted.references else None,
        "location": extracted.references[0].location if extracted.references else None,
        "status": status, "note": note,
    })

    # Scan rate regime
    uv = user["scan_rate_v_s"]
    values = list(extracted.scan_rates_v_s)
    ranges = list(extracted.scan_rate_ranges)
    paper_desc = ", ".join([_fmt_rate(v) for v in values[:4]] + [f"{_fmt_rate(a)}–{_fmt_rate(b)}" for a, b in ranges[:2]])
    if uv is None:
        status, note = "user_missing", "Enter your scan rate to compare."
    elif not values and not ranges:
        status, note = "not_stated", "Scan rate not stated in the retrieved text."
    else:
        in_range = any(a / 3.0 <= uv <= b * 3.0 for a, b in ranges)
        nearest = min(values + [x for r in ranges for x in r], key=lambda v: abs(math.log10(v / uv)))
        ratio = nearest / uv
        if in_range or abs(math.log10(ratio)) <= math.log10(3.0):
            status, note = "match", "Similar scan-rate regime (within a factor of 3)."
        else:
            factor = ratio if ratio >= 1 else 1 / ratio
            direction = "faster" if ratio > 1 else "slower"
            status = "differs"
            note = (f"Closest reported rate is {factor:.0f}× {direction} than yours: rate-dependent features "
                    "(peak separation, current ratio) may not transfer.")
    rows.append({
        "condition": "Scan rate", "user": _fmt_rate(uv) if uv else None, "paper": paper_desc or None,
        "excerpt": extracted.scan_rate_excerpts[0].excerpt if extracted.scan_rate_excerpts else None,
        "location": extracted.scan_rate_excerpts[0].location if extracted.scan_rate_excerpts else None,
        "status": status, "note": note,
    })
    return rows


def applicability(rows: list[dict]) -> dict:
    matches = [r["condition"] for r in rows if r["status"] == "match"]
    related = [r["condition"] for r in rows if r["status"] == "related"]
    differs = [r for r in rows if r["status"] == "differs"]
    unknown = [r["condition"] for r in rows if r["status"] == "not_stated"]
    material = next(r for r in rows if r["condition"] == "Electrode material")
    solvent = next(r for r in rows if r["condition"] == "Solvent")
    if material["status"] == "match" and solvent["status"] == "match":
        level = "condition-matched"
    elif material["status"] in ("match", "related") and solvent["status"] != "differs":
        level = "partially matched"
    elif material["status"] == "differs" or solvent["status"] == "differs" or differs:
        level = "different conditions"
    else:
        level = "conditions not stated"
    return {
        "level": level,
        "matches": matches,
        "related": related,
        "differences": [{"condition": r["condition"], "note": r["note"]} for r in differs],
        "not_stated": unknown,
    }
