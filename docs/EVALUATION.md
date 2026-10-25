# Evaluation

How BenchCheck was checked, what the results are, and what is still pending. Every number below comes from `python scripts/evaluate.py` (output: [evaluation_results.md](evaluation_results.md)) or from the pytest suite. The simulations are deterministic, so rerunning reproduces the numbers.

## 1. Methodology

| Group | Question | Ground truth |
|---|---|---|
| A. Theory | Are peak currents, potentials, widths and ratios measured correctly? | Closed-form results for simulated CVs: Randles–Ševčík (reversible diffusion), F v Q/4RT and 3.53 RT/F (reversible surface-confined couple), the 57 mV / 28.5 mV reversible criteria, and the √v scaling |
| B. Examples | On the demo data, do the measured ratios and the triggered hypotheses match what the generator did? | Faradaic-only components and the mechanisms switched on in the synthetic model |
| C. Robustness | Do format, units, sign convention, start potential and noise change the answer? | The same data in another encoding should give the same features |
| D. Evidence | Are cited passages verbatim, and do they support the statement they are attached to? | Automated substring check, then human judgment |

Simulators (`benchcheck/synth/`):
- `diffusion.py`: Crank–Nicolson finite differences for planar semi-infinite diffusion of a reversible couple. Its raw dimensionless peak current is 0.4463, the textbook Randles–Ševčík constant, before any BenchCheck processing.
- `thinfilm.py`: exact matrix-exponential integration of Butler–Volmer kinetics per potential step.

## 2. Results

### A. Numerical validation (all pass)

| Case | Quantity | BenchCheck | Expected |
|---|---|---|---|
| Reversible diffusion, 100 mV/s | forward peak current | 79.12 µA (−0.42%) | 79.46 µA, Randles–Ševčík |
| | ΔEp | 57.0 mV | ≈57 mV |
| | Ep − E⁰ | 28.0 mV | 28.5 mV (1 mV data step) |
| | midpoint vs E⁰ | −0.5 mV | 0 |
| | Nicholson ratio | 1.015 | 1.00 |
| | flat-baseline height ratio | 1.052 | 1.00 (reported, not used as a criterion) |
| Reversible surface-confined, 10 mV/s | peak current | −0.93% | F v Q/4RT |
| | FWHM | 89.9 mV | 90.6 mV |
| | ΔEp, charge ratio | 0.0 mV, 1.0000 | 0, 1 |
| Diffusion, 10–500 mV/s | log i<sub>p</sub> vs log v slope | 0.500 | 0.5 |

Interpretation: peak location, height and width measurements agree with theory to about 1%. The −0.93% on the surface peak comes from the default 10 mV Savitzky–Golay smoothing slightly lowering a 90 mV-wide peak. For a dissolved species, the simple flat baseline overestimates the return/forward ratio by 5% because it cannot follow the decaying forward current. That is why BenchCheck reports the Nicholson estimate for dissolved species.

### B. Synthetic examples vs ground truth

| Example (cycle 2) | Pair | Measured height ratio | Faradaic truth | Error |
|---|---|---|---|---|
| clear return | C1/A1 | 0.996 | 0.960 | +3.8% |
| clear return | C2/A2 | 1.048 | 1.015 | +3.3% |
| weak return | C1/A1 | 0.614 | 0.557 | +10.3% |
| weak return | C2/A2 | 0.642 | 0.588 | +9.1% |

| Example | Net charge ratio | Hypotheses triggered | Generator mechanisms | Recommended next check |
|---|---|---|---|---|
| clear return | 0.980 | none | none significant | scan-rate series (characterization) |
| weak return | 0.460 | side reaction at vertex; charge not recovered; progressive degradation | side current; loss of oxidized state (→ within-cycle loss and fading) | pull the forward vertex back |

Interpretation: the hypothesis rules flagged exactly the mechanisms the generator contains, without being told about them. The recommended check, pulling the vertex back, matches the clear example, which is the same model run to 1.10 V. **Known bias:** the return-peak heights read 9–10% high in the weak example because the side-current tail sits in the return sweep's baseline window. The ratio is still clearly weak (0.61 vs 1.0), but absolute ratios near the 0.70 threshold should be read with this uncertainty in mind.

### C. Robustness (all pass)

| Case | Result |
|---|---|
| Semicolon-delimited, decimal-comma file in mV and µA, no time column (scan rate entered instead) | peak heights identical (0.000% change), charge ratio unchanged |
| Cathodic-positive (US convention) export | identical results when the convention is set; a sign-convention warning when it is not |
| Scan starting mid-window (0.62 V) | 3 cycles found, cycle 2 analyzed, both peak pairs found |
| Gaussian noise with σ = 1% of the maximum current | peak potentials within 4.0 mV, ratios within 0.015 |

### D. Evidence audit: pending

The evidence pipeline is unit- and API-tested with **synthetic, clearly labeled fixtures** (`tests/fixtures/`). These tests show that:
- passages are verbatim and exclude the references section;
- full-text, abstract and snippet levels are classified as designed;
- conditions such as carbonate vs aqueous, Li/Li⁺ vs Ag/AgCl and a 10× scan-rate difference are detected and carried into the report's limits;
- the API key never reaches the cache or error messages.

These tests do **not** show that live Google Scholar results support the hypotheses. No real SerpApi responses were available in the build environment (`serpapi.com` was blocked and no key was configured).

To complete the audit:

1. Add `SERPAPI_API_KEY` and allow `serpapi.com`, then run `python scripts/refresh_demo_cache.py` (≈16 credits for both examples).
2. Run `python scripts/evaluate.py`. Section D lists every cited passage with its evidence level and an automated verbatim check.
3. A reviewer (ideally the electrochemist on the team) reads each passage and fills *Supports the statement?* with **yes**, **partially** (mentions the phenomenon under different conditions), or **no**. Report the counts as measured, for example "9 of 12 cited passages support their hypothesis; 3 mention the term in an unrelated context".
4. Fix or tighten any rule whose query or terms consistently retrieve unsupportive passages.

## 3. Test suite

`python -m pytest`: 84 tests covering units, parsing (EC-Lab-, Autolab- and Gamry-style headers, European formatting, headerless files), segmentation (noise, plateaus, mid-window starts, negative-first scans), peaks and baselines, pairing, Nicholson's formula, charge integration, the analysis pipeline, reasoning, the SerpApi client and cache (live, cached, errors, redaction, empty results), evidence records, and the HTTP API end to end.
