"""Evaluate BenchCheck on predefined cases with known answers and write docs/evaluation_results.md.

Cases:
  A. Numerical validation against electrochemical theory (simulated data).
  B. The two synthetic examples against their generator ground truth.
  C. Robustness: units/format re-encoding, sign convention, start mid-window, added noise.
  D. Evidence audit of cited passages, using real cached SerpApi responses if any exist.

Every number in the output is computed by this script; nothing is typed in by hand.
Usage:  python scripts/evaluate.py
"""

from __future__ import annotations

import io
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchcheck.cv.analysis import analyze  # noqa: E402
from benchcheck.cv.parsing import parse_table  # noqa: E402
from benchcheck.evidence.pipeline import run_evidence  # noqa: E402
from benchcheck.evidence.serpapi import SerpApiClient  # noqa: E402
from benchcheck.models import AnalysisConfig  # noqa: E402
from benchcheck.reasoning.hypotheses import evaluate as eval_hyps  # noqa: E402
from benchcheck.reasoning.hypotheses import evidence_plan  # noqa: E402
from benchcheck.reasoning.report import build_report  # noqa: E402
from benchcheck.settings import Settings, get_settings  # noqa: E402
from benchcheck.synth.diffusion import simulate_reversible  # noqa: E402
from benchcheck.synth.thinfilm import F, R, Site, ThinFilmParams, simulate  # noqa: E402

RT_F = R * 298.15 / F
rows_out: list[str] = []
summary: list[tuple[str, bool]] = []


def emit(line: str = "") -> None:
    rows_out.append(line)


def check(name: str, ok: bool) -> str:
    summary.append((name, ok))
    return "pass" if ok else "**FAIL**"


def csv_bytes(t, E, i, header="time/s,E/V,I/A", sep=",", decimal=".", e_scale=1.0, i_scale=1.0, with_time=True):
    buf = io.StringIO()
    cols = header.split(",")
    buf.write(sep.join(cols if with_time else cols[1:]) + "\n")
    for a, b, c in zip(t, E, i):
        vals = [f"{a:.4f}"] if with_time else []
        vals += [f"{b * e_scale:.6f}", f"{c * i_scale:.9e}"]
        line = sep.join(vals)
        if decimal == ",":
            line = line.replace(".", ",")
        buf.write(line + "\n")
    return buf.getvalue().encode()


def run(raw: bytes, **cfg) -> dict:
    base = {"mapping": {"potential": "E/V", "current": "I/A", "time": "time/s"},
            "units": {"potential": "V", "current": "A", "time": "s"}}
    base.update(cfg)
    result = analyze(parse_table(raw), AnalysisConfig(**base))
    result["hypotheses"] = eval_hyps(result)
    result["evidence_plan"] = evidence_plan(result, result["hypotheses"], 3)
    return result


def example(example_id: str) -> tuple[dict, dict]:
    meta = json.loads((ROOT / "examples" / f"{example_id}.meta.json").read_text(encoding="utf-8"))
    raw = (ROOT / "examples" / meta["file"]).read_bytes()
    result = analyze(parse_table(raw, meta["file"]),
                     AnalysisConfig(mapping=meta["mapping"], units=meta["units"], metadata=meta["metadata"],
                                    example_id=example_id))
    result["hypotheses"] = eval_hyps(result)
    result["evidence_plan"] = evidence_plan(result, result["hypotheses"], 3)
    return result, meta


def case_a() -> None:
    emit("## A. Numerical validation against theory (simulated data)")
    emit()
    emit("| Case | Quantity | BenchCheck | Theory / expected | Difference | Result |")
    emit("|---|---|---|---|---|---|")
    sim = simulate_reversible(e0=0.25, e_start=-0.05, e_vertex=0.55, scan_rate=0.1)
    res = run(csv_bytes(sim["time_s"], sim["potential_v"], sim["current_a"]),
              metadata={"process_type": "dissolved_species", "scan_rate": {"value": 100, "unit": "mV/s"}})
    sel = res["selected"]
    ip = sel["forward"]["peaks"][0]["height"]
    rs = sim["randles_sevcik_a"]
    pair = sel["pairs"][0]
    a1 = sel["forward"]["peaks"][0]
    err = (ip - rs) / rs * 100
    emit(f"| A1 reversible diffusion, 100 mV/s | forward peak current | {ip * 1e6:.2f} µA | {rs * 1e6:.2f} µA (Randles–Ševčík) | {err:+.2f}% | {check('A1 ip', abs(err) < 2)} |")
    emit(f"| A1 | ΔEp | {pair['delta_ep'] * 1e3:.1f} mV | ≈57 mV (2.22 RT/F) | {pair['delta_ep'] * 1e3 - 57:+.1f} mV | {check('A1 dEp', 55 <= pair['delta_ep'] * 1e3 <= 62)} |")
    emit(f"| A1 | Ep − E0 | {(a1['potential'] - 0.25) * 1e3:.1f} mV | 28.5 mV (1.109 RT/F) | {(a1['potential'] - 0.25) * 1e3 - 28.5:+.1f} mV | {check('A1 Ep', abs((a1['potential'] - 0.25) * 1e3 - 28.5) <= 2)} |")
    emit(f"| A1 | midpoint vs E0 | {pair['e_mid'] * 1e3:.1f} mV | 250.0 mV | {(pair['e_mid'] - 0.25) * 1e3:+.1f} mV | {check('A1 Emid', abs(pair['e_mid'] - 0.25) < 0.004)} |")
    emit(f"| A1 | Nicholson return/forward ratio | {pair['nicholson_ratio']:.3f} | 1.000 | {pair['nicholson_ratio'] - 1:+.3f} | {check('A1 Nicholson', abs(pair['nicholson_ratio'] - 1) < 0.05)} |")
    emit(f"| A1 | peak-height ratio (flat baseline) | {pair['height_ratio']:.3f} | 1.000 (true ratio) | {pair['height_ratio'] - 1:+.3f} | reported only |")

    q = 1e-4
    p = ThinFilmParams(sites=[Site(0.5, q, k0=1e4)], e_low=0.2, e_high=0.8, e_start=0.2, scan_rate=0.01, n_cycles=2)
    s = simulate(p)
    res = run(csv_bytes(s["time_s"], s["potential_v"], s["current_a"]), metadata={"process_type": "electrode_material"})
    sel = res["selected"]
    a = sel["forward"]["peaks"][0]
    theory = F * p.scan_rate * q / (4 * R * 298.15)
    err = (a["height"] - theory) / theory * 100
    emit(f"| A2 reversible surface-confined, 10 mV/s | peak current | {a['height'] * 1e6:.2f} µA | {theory * 1e6:.2f} µA (F v Q / 4RT) | {err:+.2f}% | {check('A2 ip', abs(err) < 1)} |")
    fwhm_t = 3.5255 * RT_F
    emit(f"| A2 | FWHM | {a['width_v'] * 1e3:.1f} mV | {fwhm_t * 1e3:.1f} mV (3.53 RT/F) | {(a['width_v'] - fwhm_t) * 1e3:+.1f} mV | {check('A2 FWHM', abs(a['width_v'] - fwhm_t) < 0.002)} |")
    emit(f"| A2 | ΔEp | {sel['pairs'][0]['delta_ep'] * 1e3:.1f} mV | 0 mV | — | {check('A2 dEp', abs(sel['pairs'][0]['delta_ep']) < 0.004)} |")
    emit(f"| A2 | charge ratio | {sel['charge_ratio']:.4f} | 1.0000 | {sel['charge_ratio'] - 1:+.4f} | {check('A2 Q', abs(sel['charge_ratio'] - 1) < 0.01)} |")

    rates, ips = [0.01, 0.05, 0.2, 0.5], []
    for v in rates:
        sim = simulate_reversible(e0=0.25, e_start=-0.05, e_vertex=0.55, scan_rate=v)
        res = run(csv_bytes(sim["time_s"], sim["potential_v"], sim["current_a"]),
                  metadata={"process_type": "dissolved_species", "scan_rate": {"value": v * 1e3, "unit": "mV/s"}})
        ips.append(res["selected"]["forward"]["peaks"][0]["height"])
    slope = float(np.polyfit(np.log10(rates), np.log10(ips), 1)[0])
    emit(f"| A3 diffusion scan-rate series (10–500 mV/s) | slope of log ip vs log v | {slope:.3f} | 0.500 | {slope - 0.5:+.3f} | {check('A3 slope', abs(slope - 0.5) < 0.02)} |")
    emit()


def case_b() -> None:
    emit("## B. Synthetic examples vs generator ground truth")
    emit()
    expected = {
        "synthetic_lmo_clear_return": set(),
        "synthetic_lmo_weak_return": {"side_reaction_vertex", "irreversible_loss", "progressive_degradation"},
    }
    emit("| Example | Pair | Measured height ratio | Ground-truth Faradaic ratio | Relative error |")
    emit("|---|---|---|---|---|")
    hyp_rows = []
    for ex_id, exp in expected.items():
        res, meta = example(ex_id)
        sel = res["selected"]
        cycle = sel["number"]
        truth = next(r for r in meta["ground_truth"]["per_cycle"] if r["cycle"] == cycle)
        by_ret = {p["return"]: p["height_ratio"] for p in sel["pairs"]}
        for ret, key in (("C1", "faradaic_ratio_C1_A1"), ("C2", "faradaic_ratio_C2_A2")):
            m, t = by_ret.get(ret), truth[key]
            rel = (m - t) / t * 100 if m is not None else float("nan")
            emit(f"| {ex_id} (cycle {cycle}) | {ret} | {m:.3f} | {t:.3f} | {rel:+.1f}% |")
        triggered = {h["id"] for h in res["hypotheses"] if h["triggered"]}
        report = build_report({k: v for k, v in res.items() if k != "data"}, {"mode": "not run"})
        hyp_rows.append((ex_id, sel["charge_ratio"], truth["faradaic_charge_ratio"], triggered, exp,
                         report["next_check"]["title"] if report["next_check"] else None))
    emit()
    emit("Charge ratios are net sweep charge (includes the side current), so they are expected to be lower than the "
         "Faradaic-only ground truth for the weak example.")
    emit()
    emit("| Example | Net charge ratio | Faradaic-only truth | Hypotheses triggered | Expected from generator | Next check |")
    emit("|---|---|---|---|---|---|")
    for ex_id, q, qt, trig, exp, nc in hyp_rows:
        ok = check(f"B {ex_id} hypotheses", trig == exp)
        emit(f"| {ex_id} | {q:.3f} | {qt:.3f} | {', '.join(sorted(trig)) or 'none'} | {', '.join(sorted(exp)) or 'none'} ({ok}) | {nc} |")
    emit()


def case_c() -> None:
    emit("## C. Robustness of parsing, units, sign convention and segmentation")
    emit()
    emit("| Case | What changed | Check | Result |")
    emit("|---|---|---|---|")
    meta = json.loads((ROOT / "examples" / "synthetic_lmo_clear_return.meta.json").read_text())
    ref, _ = example("synthetic_lmo_clear_return")
    ref_sel = ref["selected"]
    raw = (ROOT / "examples" / meta["file"]).read_text().splitlines()
    data = [ln.split(",") for ln in raw if ln and not ln.startswith("#")][1:]
    t = np.array([float(r[0]) for r in data])
    E = np.array([float(r[1]) for r in data])
    i = np.array([float(r[2]) for r in data]) * 1e-3

    eu = csv_bytes(t, E, i, header="time/s,Potential (mV),Current (µA)", sep=";", decimal=",", e_scale=1e3,
                   i_scale=1e6, with_time=False)
    res = run(eu, mapping={"potential": "Potential (mV)", "current": "Current (µA)"},
              units={"potential": "mV", "current": "µA"},
              metadata={**meta["metadata"], "scan_rate": {"value": 1, "unit": "mV/s"}})
    dh = max(abs(a["height"] - b["height"]) / b["height"] for a, b in zip(res["selected"]["forward"]["peaks"], ref_sel["forward"]["peaks"]))
    dq = abs(res["selected"]["charge_ratio"] - ref_sel["charge_ratio"])
    emit(f"| C1 | semicolon + decimal comma, mV and µA, no time column | max peak-height change {dh * 100:.3f}%, charge-ratio change {dq:.4f} | {check('C1', dh < 1e-3 and dq < 0.01)} |")

    flipped = csv_bytes(t, E, -i)
    res_ok = run(flipped, current_convention="cathodic_positive", metadata=meta["metadata"])
    res_bad = run(flipped, metadata=meta["metadata"])
    same = abs(res_ok["selected"]["pairs"][0]["height_ratio"] - ref_sel["pairs"][0]["height_ratio"]) < 1e-9
    hinted = "sign_convention_hint" in [q["code"] for q in res_bad["quality"]]
    emit(f"| C2 | cathodic-positive export | identical ratio when convention set: {same}; sign hint when not set: {hinted} | {check('C2', same and hinted)} |")

    p = ThinFilmParams(sites=[Site(0.80, 0.15, 0.02), Site(0.95, 0.15, 0.02)], e_low=0.30, e_high=1.10, e_start=0.62,
                       scan_rate=0.001, n_cycles=3, c_dl=0.04, noise_a=4e-6)
    s = simulate(p)
    res = run(csv_bytes(s["time_s"], s["potential_v"], s["current_a"]), metadata=meta["metadata"])
    n_pairs = len(res["selected"]["pairs"])
    emit(f"| C3 | scan starts mid-window (0.62 V) | {len(res['cycle_list'])} cycles found, analyzed cycle {res['selected_cycle']}, {n_pairs} pairs | {check('C3', n_pairs == 2 and res['selected_cycle'] == 2)} |")

    rng = np.random.default_rng(11)
    noisy = i + rng.normal(0, 0.01 * np.max(np.abs(i)), i.size)
    res = run(csv_bytes(t, E, noisy), metadata=meta["metadata"])
    de = max(abs(a["potential"] - b["potential"]) for a, b in zip(res["selected"]["forward"]["peaks"], ref_sel["forward"]["peaks"]))
    dr = max(abs(a["height_ratio"] - b["height_ratio"]) for a, b in zip(res["selected"]["pairs"], ref_sel["pairs"]))
    emit(f"| C4 | added noise, σ = 1% of max current | peak-potential shift ≤ {de * 1e3:.1f} mV, ratio change ≤ {dr:.3f} | {check('C4', de <= 0.005 and dr <= 0.05)} |")
    emit()


def case_d() -> None:
    emit("## D. Evidence audit (cited passages)")
    emit()
    s = get_settings()
    cache_only = Settings(serpapi_key=None, evidence_mode="cache", cache_dir=s.cache_dir, max_queries=s.max_queries,
                          max_extracts=s.max_extracts, timeout_s=s.timeout_s)
    client = SerpApiClient(cache_only)
    if not any(client.cache.count().values()):
        emit("No real SerpApi responses are cached, so there is nothing to audit yet. Run "
             "`python scripts/refresh_demo_cache.py` with a SerpApi key and network access, then rerun this script. "
             "Automated checks below will then list every cited passage with a verbatim check; the column "
             "*Supports the statement?* must be filled in by a human reviewer.")
        emit()
        return
    for ex_id in ("synthetic_lmo_weak_return", "synthetic_lmo_clear_return"):
        res, _ = example(ex_id)
        evidence = run_evidence(res, client, cache_only.max_extracts)
        report = build_report({k: v for k, v in res.items() if k != "data"}, evidence)
        emit(f"### {ex_id}: evidence mode {evidence['mode']}, {len(evidence['sources'])} sources")
        emit()
        levels = {}
        for src in evidence["sources"]:
            levels[src["evidence_level"]] = levels.get(src["evidence_level"], 0) + 1
        emit(f"Evidence levels: {json.dumps(levels)}")
        emit()
        emit("| Hypothesis | Source | Level | Verbatim check | Matched terms | Supports the statement? (human) |")
        emit("|---|---|---|---|---|---|")
        n = 0
        for h in report["explanations"]:
            for e in h.get("evidence", []):
                src = next(s for s in evidence["sources"] if s["source_id"] == e["source_id"])
                verbatim = next((p["verbatim_verified"] for p in src["passages"] if p["text"] == e["passage"]), False)
                n += 1
                check(f"D verbatim {ex_id} {n}", bool(verbatim))
                title = (e["title"] or "")[:70].replace("|", "/")
                emit(f"| {h['title']} | {title} | {e['level']} | {'pass' if verbatim else '**FAIL**'} | {', '.join(e['matched_terms'])} | |")
        if not n:
            emit("| — | no passages cited | | | | |")
        emit()


def main() -> int:
    emit("# BenchCheck evaluation results")
    emit()
    emit(f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `scripts/evaluate.py`. "
         "All numbers are computed by the script.")
    emit()
    case_a()
    case_b()
    case_c()
    case_d()
    passed = sum(ok for _, ok in summary)
    emit("## Summary")
    emit()
    emit(f"{passed} of {len(summary)} automated checks passed.")
    failed = [name for name, ok in summary if not ok]
    if failed:
        emit()
        emit("Failed: " + ", ".join(failed))
    out = ROOT / "docs" / "evaluation_results.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(rows_out) + "\n", encoding="utf-8")
    print("\n".join(rows_out))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
