# BenchCheck evaluation results

Generated 2026-10-25 00:40 UTC by `scripts/evaluate.py`. All numbers are computed by the script.

## A. Numerical validation against theory (simulated data)

| Case | Quantity | BenchCheck | Theory / expected | Difference | Result |
|---|---|---|---|---|---|
| A1 reversible diffusion, 100 mV/s | forward peak current | 79.12 µA | 79.46 µA (Randles–Ševčík) | -0.42% | pass |
| A1 | ΔEp | 57.0 mV | ≈57 mV (2.22 RT/F) | +0.0 mV | pass |
| A1 | Ep − E0 | 28.0 mV | 28.5 mV (1.109 RT/F) | -0.5 mV | pass |
| A1 | midpoint vs E0 | 249.5 mV | 250.0 mV | -0.5 mV | pass |
| A1 | Nicholson return/forward ratio | 1.015 | 1.000 | +0.015 | pass |
| A1 | peak-height ratio (flat baseline) | 1.052 | 1.000 (true ratio) | +0.052 | reported only |
| A2 reversible surface-confined, 10 mV/s | peak current | 9.64 µA | 9.73 µA (F v Q / 4RT) | -0.93% | pass |
| A2 | FWHM | 89.9 mV | 90.6 mV (3.53 RT/F) | -0.6 mV | pass |
| A2 | ΔEp | 0.0 mV | 0 mV | — | pass |
| A2 | charge ratio | 1.0000 | 1.0000 | +0.0000 | pass |
| A3 diffusion scan-rate series (10–500 mV/s) | slope of log ip vs log v | 0.500 | 0.500 | +0.000 | pass |

## B. Synthetic examples vs generator ground truth

| Example | Pair | Measured height ratio | Ground-truth Faradaic ratio | Relative error |
|---|---|---|---|---|
| synthetic_lmo_clear_return (cycle 2) | C1 | 0.996 | 0.960 | +3.8% |
| synthetic_lmo_clear_return (cycle 2) | C2 | 1.048 | 1.015 | +3.3% |
| synthetic_lmo_weak_return (cycle 2) | C1 | 0.614 | 0.557 | +10.3% |
| synthetic_lmo_weak_return (cycle 2) | C2 | 0.642 | 0.588 | +9.1% |

Charge ratios are net sweep charge (includes the side current), so they are expected to be lower than the Faradaic-only ground truth for the weak example.

| Example | Net charge ratio | Faradaic-only truth | Hypotheses triggered | Expected from generator | Next check |
|---|---|---|---|---|---|
| synthetic_lmo_clear_return | 0.980 | 0.987 | none | none (pass) | Characterize rate behavior with a scan-rate series |
| synthetic_lmo_weak_return | 0.460 | 0.572 | irreversible_loss, progressive_degradation, side_reaction_vertex | irreversible_loss, progressive_degradation, side_reaction_vertex (pass) | Repeat with the forward vertex pulled back |

## C. Robustness of parsing, units, sign convention and segmentation

| Case | What changed | Check | Result |
|---|---|---|---|
| C1 | semicolon + decimal comma, mV and µA, no time column | max peak-height change 0.000%, charge-ratio change 0.0000 | pass |
| C2 | cathodic-positive export | identical ratio when convention set: True; sign hint when not set: True | pass |
| C3 | scan starts mid-window (0.62 V) | 3 cycles found, analyzed cycle 2, 2 pairs | pass |
| C4 | added noise, σ = 1% of max current | peak-potential shift ≤ 4.0 mV, ratio change ≤ 0.015 | pass |

## D. Evidence audit (cited passages)

No real SerpApi responses are cached, so there is nothing to audit yet. Run `python scripts/refresh_demo_cache.py` with a SerpApi key and network access, then rerun this script. Automated checks below will then list every cited passage with a verbatim check; the column *Supports the statement?* must be filled in by a human reviewer.

## Summary

16 of 16 automated checks passed.
