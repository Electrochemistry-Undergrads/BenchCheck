# QA implementation, 25 October 2026

Implements the supplied `BENCHCHECK_FIXES.md` and reproductions from
`BenchCheck_QA_Findings.ipynb`. The original attachments and their observations
were left unchanged. The frontend source is `web/`, served at `/static/`.

## Issue map

| IDs | Status | Change and verification |
|---|---|---|
| U1 | Fixed | Detect data start across malformed cells; preserve header and earlier rows; count damaged cells. Early/middle/late cell regressions. |
| U2, U8 | Fixed | CSV quoting, decimal commas, grouped thousands, consistent delimiter scoring. Quoted and European-number regressions. |
| U3 | Fixed | Unicode minus normalization; analysis notices when more than 5% of mapped rows are excluded. |
| U4 | Fixed | Gamry name/unit headers and index exclusions, including unlabeled restarting point indices. |
| U5 | Fixed | High-magnitude potential/current unit warning after conversion. |
| U6 | Fixed | Infer omitted/null units from mapped headers; disclose assumed defaults. |
| U7 | Fixed | API validates distinct potential/current/time columns. Duplicate multipart file parts rejected separately. |
| U9 | Fixed | Numeric coverage required for suggestions; nonnumeric columns disclosed in inspect notes. |
| U10 | Fixed | Robust current-outlier warning; excluded stability cycles disclosed. |
| U11 | Fixed | UTF-16/32 BOM decoding; actionable gzip/ZIP rejection. |
| U13, M10 | Fixed | 30 MiB overall request limit, 25 MiB file limit, 1 MiB report limit; min/max plot decimation preserving extrema, peaks, and vertex indices. |
| M1 | Fixed | Shared physical metadata validation prevents invalid Nernst/Randles calculations; numerical overflow guard. |
| M2 | Fixed | Explicit concentration factors for M, mM, µM/μM/uM, nM, mol/L, mmol/L; reject other units. |
| M3, M4 | Fixed | Shared finite/range validation and unusual-value notices/caveats in analysis and conversion previews. |
| M5 | Fixed | Reject NaN/Infinity, including safe validation-error serialization. |
| M6 | Fixed | Custom scale label retains reference and numeric offset; description is a separate note; unverified-offset caveat remains. |
| M7, M8 | Fixed | Validate scan-rate units/values, positive area/mass/D/concentration, and integer n ≥ 1. |
| M9 | Fixed | Validation errors retain field locations and messages. |
| M11 | Fixed | Configurable trusted hosts, localhost defaults plus TestClient's `testserver`. |
| M12 | Fixed | Markdown escapes HTML/link syntax and strips NUL/bidi controls; HTTP(S)-only links. HTML escaping retained. |
| M13 | Fixed | Reports use canonical analysis stored by server-generated `analysis_id`; ignore client numerical/provenance/evidence edits. |
| M14 | Fixed | Unknown references rejected; undescribed `other` remains missing. |
| M15 | Fixed | Accurate SHE identity, temperature/Nernst assumptions, nonaqueous RHE caveat; reject offset with noncustom target. |
| M16 | Fixed | HEAD on GET routes, nosniff and CSP compatible with bundled Plotly and web fonts. |
| A1 | Fixed | Vertex rise requires current in the sweep's Faradaic direction and a noise-resolved positive slope. EC reproduction passes. |
| A2 | Fixed | Boundary settling extrema excluded; enforce 5 mV width; near-vertex peaks excluded from loss/EC comparisons. Pure RC reproduction passes for both process types. |
| A3 | Fixed | Coordinate zero-baseline fallback on both sweeps and disclose affected cycles; remove unsupported “broader” wording. Ideal surface ratio passes. |
| A4 | Fixed | Vertex-side half-width/current-decay test; near-vertex tag alone cannot trigger truncation. All four reversible windows pass. |
| A5 | Fixed | Unknown process type suppresses loss/EC diagnoses and adds notice. |
| A6 | Fixed | Raw second-difference noise estimate remains available without smoothing. Noisy one-peak reproduction passes. |
| A7 | Fixed | Initial nontrivial partial sweep determines auto forward direction. OCP-start EC reproduction passes. |
| A8 | Fixed | Dissolved kinetic cutoff 80/n mV; rule text states n and threshold. Two-electron reproduction passes. |
| A9 | Fixed | Multiplicative scan mismatch, suppress Randles comparison on mismatch, disclose time gaps. |
| A10 | Fixed | Avoid peak-relative claims without peaks/ratios; unresolved rising wave alone does not establish a separate side reaction; dissolved charge imbalance does not support the vertex rule. |
| A11 | Fixed | Geometric per-cycle peak change. |
| A12 | Fixed | Prominence threshold uses noise propagated through the smoothing filter; raw noise still reported. |
| E1 | Fixed | Compare dissolved analyte independently from electrode/substrate; support named custom analytes. |
| E2 | Fixed | Condition-matched requires material/analyte, electrolyte and solvent matches with no listed differences; experimental-context filters, mixture and molal distinctions, ±20% scan-rate criterion. |
| E3 | Fixed | Reference/citation filtering; passing body mentions cannot establish an experimental material match. |
| E4 | Fixed | Prussian-blue formulas distinguished from dissolved ferricyanide and analogues; specific organic solvent enters dissolved-species queries. |
| E5 | Fixed | Non-aqueous no longer also matches aqueous. |
| E6 | Fixed | Fifteen-minute domain failure memory; blocked/ScienceDirect downranking and PDF/OA preference; unusable extraction counts as failed. |
| E7 | Fixed | Server-enforced per-analysis budgets, shared across repeated identical analysis, and 30 live evidence calls/minute; trimmed 1–300 character queries; server-selected source IDs only. |
| E8 | Fixed | HTTP(S) public-address validation after DNS resolution; client links ignored. |
| E9 | Fixed | Typed source references reject malformed select/extract inputs with 422. |
| E10 | Fixed | Canonical server sources, passages, provenance and found-by values used for selection and reports; fabricated client records cannot establish evidence. |
| E11 | Fixed | Preserve duplicate-source snippets; snippet-specific verification label; citation metadata and cached Crossref DOI enrichment supply full venue/publication year. |
| E12 | Fixed | Provider-cached labeling for old provider timestamps; no estimated new credit for those responses; honest extraction success counts and upstream errors. Credit counts are estimates, not billing records. |
| UI1 | Fixed | Failed upload opens setup, clears previous results/summary, restores focus and accepts another file. Browser checked. |
| UI2 | Fixed | Bounded selects, wrapped labels, stacked mapping units, full-name tooltips. Long headers checked at 375/1024/1440 px. |
| UI3 | Fixed | Applied configuration snapshot, draft-change banner and disabled result controls/exports until confirmation. Browser and Node regression. |
| UI4, UI5 | Fixed | Generation/request guards prevent old analysis, evidence and report responses entering a newer file's state; disable cycle controls in flight. Node regressions. |
| UI6 | Fixed | Frontend numeric constraints and browser validation, reset normalization after area edits; synchronize normalized state with server response. |
| UI7 | Fixed | Restore focused form control on rerender; aria-pressed cycles; preserve cycle-button focus. |
| UI8 | Fixed | Changed analyses have separate canonical evidence sessions; outdated evidence excluded from the report request. |
| UI9 | Fixed | Explicit white PNG export background and dark axes. |
| UI10 | Fixed | Disable pending/impossible conversion; guard stale preview responses; apply previewed custom offset and show server scale label. |
| UI11 | Fixed | Escape user-supplied Plotly title text. |
| UI12 | Fixed | Avoid repeated header units, wider scan units, completed progress states, mobile evidence pill, reset metadata for a new file, beforeunload warning. |

Smaller parsing items: Fortran D exponents and leading NULs are accepted; stored
filenames are capped at 240 characters; oversized preambles have a specific
error; duplicate file parts return 422.

## Evidence label definitions and limits

- **Condition-matched:** the active material (or dissolved analyte), electrolyte
  and solvent match, and no compared condition differs.
- **Partially matched:** material/analyte is matched or related, but required
  conditions are missing/related rather than all matched.
- **Different conditions:** at least one compared condition differs and the
  stronger matching criteria are not met.
- **Conditions not stated:** insufficient relevant conditions were retrieved.

Condition extraction remains a conservative, rule-based text heuristic. It
cannot establish that every literature experiment is comparable. Missing
concentrations, synthesis/precursor context, bracketed citations and passing
material mentions reduce applicability rather than establishing a match.

## API and operating notes

Analyze first, then include the returned `analysis_id` in evidence/search,
evidence/select, evidence/extract, and report requests. Report also accepts an
older full-analysis envelope only when it contains a valid server-issued ID;
the server ignores that envelope's contents. Source references require
`source_id` and a string `title`; links and evidence flags are taken from server
state. Existing external API clients, including older notebook evidence helpers,
need to pass this ID. The website does so automatically.

Sessions expire after one hour or a server restart; at most 64 report sessions
are retained. Budgets persist per identical file/settings for an hour. State
and the global call limiter are per server process; this app defaults to one
local process. Re-analyze after restarting. Public deployments with multiple
workers should use a shared session/limiter store.

Plot arrays are capped at about 20,000 points per cycle. Calculations always use
all points. POST `/api/analyze?full_resolution=true` requests the full arrays;
decimated responses include original indices. Time gaps are flagged; their
intervals still contribute to reported integrated charge.

CSP permits inline styles for Plotly's layout/style operations, while scripts
remain restricted to the app. Configure `BENCHCHECK_ALLOWED_HOSTS` when serving
under another explicitly selected hostname. Crossref enrichment is optional,
cached, and leaves metadata unchanged on failure. Provider credit totals are
estimates; actual billing remains with the provider.

## Verification

- `python -m pytest -q`: 200 passing backend tests, including 28 notebook
  upload/metadata/security input replays and ten numerical reproduction groups.
- `node --test tests/frontend_state.test.cjs`: three passing state/concurrency
  regressions. `node --check web/app.js` also passes.
- Existing reference offsets, reversible separation, Nicholson ratio,
  Randles–Ševčík, surface charge/FWHM, sign/unit invariance, path traversal and
  25 MiB file-limit checks remain passing.
- Browser: upload/analyze/report, impossible RHE preview blocked, confirmed SHE conversion applied at +0.210 V, draft edit/disabled exports, failed empty
  re-upload and recovery, and >300-character headers at 375/1024/1440 pixels.
  Select bounds stayed inside the viewport; no JavaScript errors were logged.
- SerpApi tests use mocked transports or a cache-only server. No live SerpApi
  credits were used. Real-provider E1–E3 search results and E7 credit-spending
  reproductions were **not** re-run live; those provider-dependent verification
  steps are deferred, while their implementation is covered by local fixtures.
- The original notebook was not overwritten. Its API inputs are preserved in
  `tests/qa_cases`; some old print expressions stop after an expected rejection
  or a now-empty suggestion. Focused tests assert the intended corrected behavior.
