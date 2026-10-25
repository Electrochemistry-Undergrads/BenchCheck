# 90-second demo script

**Setup before judging:** server running (`python -m benchcheck`), browser at `http://127.0.0.1:8000`, window ≥ 1280 px wide, page zoom 100%, other tabs closed. Have the evidence fallback ready (see the end of this file).

| Time | On screen | Say |
|---|---|---|
| 0:00 | Landing page | "I work with lithium manganese oxide electrodes and cyclic voltammetry, and I've hit results I couldn't interpret. *[Personalize: one true sentence about a confusing result you had.]* With a weak return peak, is the material degrading, is the reference off, or did I push the potential too far? BenchCheck answers three questions: what did I measure, what could explain it, and what should I check next?" |
| 0:12 | Click **Synthetic CV · weak return peak** | "This is a labeled synthetic CV, LMO-like in aqueous lithium chloride. BenchCheck suggests the columns and units, and I confirm them. It also flags missing metadata, like pH and electrode area, and says why each one matters." |
| 0:25 | Click **Confirm & analyze** | "Everything here is measured, not guessed. Blue is the forward sweep, orange is the return, and the arrows show scan direction. The return peaks are only 0.61 of the forward peaks. Only 46% of the charge comes back. The current is still rising at the vertex, and the peaks drop 67% over three cycles." |
| 0:42 | Click **Find literature evidence** | "Now SerpApi. BenchCheck builds Google Scholar queries from my conditions and the flagged features, like LMO plus aqueous LiCl plus oxygen evolution. Then it uses SerpApi's Extract API to pull abstracts or full text." |
| 0:55 | Scroll to the evidence table | "Each row quotes a verbatim passage and labels it full text, abstract, or snippet. Then it compares conditions with mine: material, electrolyte, aqueous vs organic, reference electrode, scan-rate regime." *Point at a row with a ✗ chip if there is one:* "This paper's conditions differ from mine, and BenchCheck says how that limits what I can conclude." |
| 1:08 | Point at **Next check** | "The recommendation: pull the vertex back 50 to 100 millivolts. It distinguishes all three hypotheses in one 30-minute cycle, and the reasons are listed." *If a reason mentions condition-matched literature, read it out.* |
| 1:18 | Click **Evidence log** (drawer) | "Every SerpApi call is logged with its query, timestamp, search ID, and whether it was live or cached." |
| 1:24 | Close the drawer | "Because the data are synthetic, we know the truth: the generator added a side reaction and material loss above 1.15 V. BenchCheck wasn't told that. BenchCheck turns a confusing experiment into measured observations, traceable evidence, and a clearer next step." |

## If something fails

- **Live SerpApi is slow or down:** say "SerpApi is unreachable, so BenchCheck says so." The numbers, hypotheses and next check still appear, and the evidence panel shows *unavailable* with the reason. That is the graceful-failure feature, so show it.
- **Pre-recorded fallback:** restart with `BENCHCHECK_EVIDENCE_MODE=cache python -m benchcheck`. Evidence is then served from `data/cache/demo/`: real responses recorded earlier with `scripts/refresh_demo_cache.py`, each labeled *cached* with its retrieval time. Say "this is cached evidence, retrieved at [time]".
- **Run `refresh_demo_cache.py` before the event.** Without it, the cache-only fallback has nothing to show.

## Backup lines for judges' questions

- *"Is the AI making things up?"* No language model writes the evidence. Passages are verbatim slices of retrieved text, checked as substrings. Hypotheses come from published rules with thresholds shown in the app.
- *"How do you know the numbers are right?"* On simulated data with exact answers, the peak current is within 0.4% of Randles–Ševčík, ΔEp is 57 mV and FWHM is 89.9 vs 90.6 mV. 16 of 16 evaluation checks pass.
- *"What is SerpApi doing that a plain web search couldn't?"* It gives structured Google Scholar results (titles, venues, citation counts, PDF resources) plus page extraction from one API. That makes the condition comparison and the evidence log possible in real time.
