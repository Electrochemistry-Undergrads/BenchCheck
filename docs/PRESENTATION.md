# Three-minute judge presentation

Five beats. Keep the demo itself to about 80 seconds (use the [demo script](DEMO_SCRIPT.md) in compressed form).

## 1. The problem (0:00–0:25)

**Slide:** an explicitly labeled synthetic CV with a weak return peak and three question marks: *material? reference? scan rate?*

> "Cyclic voltammetry is the first experiment almost every electrochemistry student runs, and the first one that confuses them. A weak return peak can mean the material is degrading, a side reaction at the vertex, a bad reference electrode, or just the wrong scan rate. The literature has answers, but under conditions that rarely match yours: different electrolyte, different reference, a scan rate a hundred times slower. Students lose a lot of time on this. I have hands-on research experience with lithium manganese oxide electrodes for lithium extraction, and I've run into confusing results myself." *[Personalize: one true example from your own work.]*

## 2. What BenchCheck does (0:25–0:40)

**Slide:** three columns: **Observed · Possible explanations · Next check**.

> "BenchCheck turns a confusing electrochemical experiment into measured observations, traceable evidence, and a clearer next step. Observed is pure calculation. Possible explanations are hypotheses tied to those numbers and to cited passages. Next check is one practical measurement that best tells the hypotheses apart."

## 3. Live demo (0:40–2:00)

Upload the weak-return synthetic CSV, confirm its columns, units, and metadata → analyze → key numbers → **Find literature evidence** → evidence table → next check → export JSON. (See the demo script for exact lines.)

## 4. Why SerpApi is essential (2:00–2:25)

**Slide:** pipeline diagram: *features → Scholar queries → Extract → verbatim passages → condition comparison → ranking*.

> "SerpApi's Google Scholar API turns our measured features into targeted searches. The Extract API, launched this month, pulls abstracts or full text so we can quote passages instead of paraphrasing them. Every source is labeled full text, abstract, or snippet. Every condition is compared with the user's, and the result changes which check we recommend. If the API is down, the analysis still works and the gap is stated. Cached results are always real, earlier responses, labeled with their retrieval time."

## 5. Credibility and what's next (2:25–3:00)

**Slide:** validation table (Randles–Ševčík −0.42%, ΔEp 57 mV, FWHM 89.9 vs 90.6 mV, 16/16 checks) and a "known limits" line.

> "We validated the math against electrochemical theory on simulated data with exact answers. We also measured our own bias: return peaks read about 10% high when a side reaction tails into the baseline, and we say so. The examples are labeled synthetic, so we know the ground truth: BenchCheck flagged exactly the mechanisms the generator contained, and recommended the check that fixes them. Next, we'll run real lab data, then add charge–discharge analysis and an ICP-OES dilution checker, because dilution errors are another place I've seen results go wrong." *[Personalize if you have a specific story.]*

**Close:** "BenchCheck: measured observations, traceable evidence, a clearer next step."

## Slide checklist

1. Problem CV + question marks
2. Observed / Possible explanations / Next check
3. (Live app)
4. SerpApi pipeline diagram + evidence-level badges
5. Validation numbers + known limitations + roadmap

## Timing tips

- Rehearse the demo with the cached fallback ready (`BENCHCHECK_EVIDENCE_MODE=cache`).
- If live search takes more than 10 s, talk through the query list while it loads. The rows update live.
- Do not claim results from real experimental data until you have analyzed some; the current demo data are synthetic.
