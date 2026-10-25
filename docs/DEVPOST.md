# BenchCheck — Devpost draft

**Tagline:** BenchCheck turns a confusing electrochemical experiment into measured observations, traceable evidence, and a clearer next step.

**Tracks:** Best Use of SerpApi (primary) · Best Pitch

---

## Inspiration

I have hands-on research experience with lithium manganese oxide (LMO) electrodes and lithium extraction: cyclic voltammetry, charge–discharge experiments, sample preparation and ICP-OES. Along the way I've run into confusing electrochemical results and dilution errors. *[Personalize: one or two true sentences about a specific result that confused you and what it cost you.]* The answers often exist in the literature, but under different conditions: an organic electrolyte instead of an aqueous one, a Li/Li⁺ reference instead of Ag/AgCl, a very different scan rate. It isn't obvious which differences matter. Undergraduate and early graduate researchers face this constantly.

## What it does

Upload a cyclic voltammogram (CSV/TXT). BenchCheck:

1. **Observed:** confirms columns, units and sign convention with you, then measures scan reversals, cycles, peak potentials and heights, peak separation, return/forward peak and charge ratios, vertex behavior and cycle-to-cycle trends. Every smoothing or baseline step is disclosed, and reference conversions or area normalization require explicit confirmation.
2. **Possible explanations:** rule-based hypotheses, each triggered by a measured feature with a visible threshold and stated assumptions. It never assigns a peak to a mechanism.
3. **Literature evidence (SerpApi):** builds Google Scholar queries from your conditions and the flagged features, retrieves results via SerpApi's Google Scholar API, and pulls abstracts or full text with SerpApi's Extract API. Each source shows a verbatim passage, whether it came from full text, an abstract or only a search snippet, which experimental conditions match yours, and which differ and why that matters.
4. **Next check:** ranks practical measurements by how many hypotheses they distinguish, whether condition-matched literature supports them, and effort. For example: "repeat with the forward vertex pulled back 50–100 mV."

Reports export as Markdown, HTML or JSON. An evidence log shows every SerpApi call with its query, timestamp, search ID and live/cached status.

## How we built it

- **Backend:** Python + FastAPI. Numerical analysis with NumPy/SciPy: zigzag reversal detection, Savitzky–Golay-located peaks, pre-wave baselines, order-preserving peak pairing, Nicholson's ratio, charge integration and data-quality checks (clipping, scan-rate mismatch, sign convention).
- **SerpApi:** `engine=google_scholar` for search and `engine=extract` for page content. The cache stores only verbatim live responses with retrieval times, and reuse is always labeled cached. The API key stays server-side and is redacted from anything stored.
- **Evidence engine:** deterministic, with no generative text in the evidence chain. Full-text/abstract/snippet classification, verbatim passage selection (references excluded), and condition extraction (material family, electrolyte, aqueous vs non-aqueous, reference electrode, scan-rate regime) using the same dictionaries for the user's metadata and for paper text.
- **Frontend:** vanilla JavaScript and Plotly with no build step. Interactive CV with scan-direction arrows, cycles, peaks and baselines; an evidence comparison table; the report; confirmation dialogs.
- **Validation:** finite-difference and thin-film simulators with known answers, plus two labeled synthetic LMO-like examples with ground truth.

## Challenges

- **Baselines are where CV analysis goes wrong.** A straight line extrapolated under a decaying side-reaction current gave a *negative* return peak in an early version. We switched to a flat pre-wave baseline placed from the forward peak's width, measured the remaining bias against ground truth (+9–10% on the stress case), and documented it instead of hiding it.
- **Peak widths for overlapping peaks.** Widths at half prominence flip between overlapping peaks. We now measure FWHM above the baseline and report "unresolved" when a valley is reached first.
- **Not overstating evidence.** Search snippets look authoritative, so the UI never presents one as full-paper evidence, and every unstated condition is shown as "not stated" rather than guessed.
- **Using a brand-new API.** SerpApi's Extract API launched days before the event. We wrote the parser defensively against the documented fields.

## Accomplishments (demonstrated results)

All of these are measured by `scripts/evaluate.py`:

- Peak current within **0.42%** of Randles–Ševčík on a simulated reversible CV; ΔEp **57.0 mV**; Nicholson ratio **1.015**.
- Surface-confined peak current within **0.93%** of theory; FWHM **89.9 mV** vs 90.6 mV.
- log i<sub>p</sub> vs log v slope **0.500** across 10–500 mV/s.
- On the labeled synthetic examples, BenchCheck flagged **exactly** the mechanisms the generator contained. For the weak-return case it recommended the check (lower the vertex) that the clear example shows resolves the problem.
- 91 automated tests; 16/16 evaluation checks pass; works at phone width.

*Fill in before submitting:* results of the live SerpApi run and the human evidence audit (how many cited passages actually support their hypothesis). Report the real counts.

## What we learned

- Most of the value is in being explicit: which cycle, which baseline, which sign convention, which reference scale.
- Condition mismatch is the main reason literature misleads students, so comparing conditions turned out to be more useful than summarizing papers.

## What's next

- Run BenchCheck on real CVs from our lab.
- Add charge–discharge and EIS with the same Observed → Explanations → Next check structure.
- Add an ICP-OES dilution-chain checker.
- Accept scan-rate series to automate b-value and ratio-vs-rate analysis.

## Built with

Python · FastAPI · NumPy · SciPy · httpx · Plotly.js · SerpApi (Google Scholar API, Extract API) · Claude Code (AI coding assistant)

## Try it out

- GitHub: https://github.com/Electrochemistry-Undergrads/BenchCheck
- Run locally: `pip install -r requirements.txt && python -m benchcheck`
