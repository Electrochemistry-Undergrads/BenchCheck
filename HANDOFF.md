# BenchCheck handoff

Status as of 2026-10-25.

Frontend update: the workspace now starts with file upload; the example picker and its automatic metadata filling have been removed. Synthetic fixtures remain under `examples/` for validation. When uploading them, check **My file contains simulated data** and enter their metadata explicitly. The frontend has keyboard-accessible upload, labeled unit selectors, and a focus-managed evidence drawer. See `docs/HACKTX.md` for verified official requirements and outstanding submission checks. AI assistance includes Claude Code and OpenAI Codex.

The implementation-status table below records the original handoff. Locally generated, uncommitted cache responses are not part of this frontend change and still need evidence review before publication.

 This file is for whoever picks up the project next: a teammate, or a new Claude Code session.

## One-paragraph summary

BenchCheck is a FastAPI + vanilla-JS web app for HackTX 2026, targeting **Best Use of SerpApi**. A user uploads a cyclic voltammogram (CSV), confirms columns and units, and enters experiment metadata. BenchCheck then measures peaks, ratios, charge balance, vertex behavior and cycle trends, and proposes rule-based hypotheses tied to those measurements. It searches Google Scholar (SerpApi) and pulls page text (SerpApi Extract API), compares paper conditions with the user's, and recommends a next check. The output is a report in three parts (Observed / Possible explanations / Next check), exportable as Markdown, HTML or JSON.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # add SERPAPI_API_KEY
python -m benchcheck          # http://127.0.0.1:8000
pip install -r requirements-dev.txt && python -m pytest   # 91 tests
python scripts/evaluate.py    # 16/16 checks -> docs/evaluation_results.md
```

## State

| Area | Status |
|---|---|
| CSV parsing, units, sign convention, segmentation, peaks, baselines, ratios, charge, quality flags | Done, tested, validated against theory (see docs/EVALUATION.md) |
| Hypothesis rules, next-check ranking, report + export | Done, tested on both synthetic examples against ground truth |
| SerpApi Google Scholar + Extract client, cache, evidence classification, condition comparison | Implemented; tested offline with labeled fixtures. **Never run against the live API** |
| Web UI (plot, evidence table, report, evidence log drawer, confirmation dialogs) | Done; checked with Playwright on desktop and phone widths |
| Offline demo cache (`data/cache/demo/`) | **Empty**: needs a live refresh |
| Human audit of cited passages | **Not done**: needs real evidence first |
| Docs: README, demo script, presentation, Devpost draft | Done; personal-story placeholders need filling |

## To-do, in priority order

1. **Get live SerpApi working.** The build sandbox blocked `serpapi.com` and had no key.
   - Locally: put `SERPAPI_API_KEY` in `.env`.
   - In a Claude Code cloud session: allow `serpapi.com` under Network access and add `SERPAPI_API_KEY` as a network secret, then start a new session.
2. **Smoke-test live:** upload the weak-return CSV, mark it simulated, confirm its mapping and metadata, click **Find literature evidence**, and check the evidence log drawer for errors. The Extract API launched on 2026-10-13, and its response parser (`benchcheck/evidence/sources.py::parse_extract`) was written against documented field names (`page_information`, `meta_tags`, `text_content.full/markdown`). If real responses differ, adjust it there.
3. **Record the demo fallback:** `python scripts/refresh_demo_cache.py`. It uses about 16 credits and writes `data/cache/demo/` plus `docs/demo_reports/`. Review the reports, then commit both folders.
4. **Audit the evidence:** `python scripts/evaluate.py`. Section D lists every cited passage; a human fills in "Supports the statement?". Report the real counts in docs/EVALUATION.md and docs/DEVPOST.md.
5. **Personalize** the `[Personalize: …]` placeholders in docs/DEMO_SCRIPT.md, docs/PRESENTATION.md and docs/DEVPOST.md with true stories only.
6. **Complete the remaining submission checks in `docs/HACKTX.md`**, including public code/video and accurate AI disclosure. Official rules were verified during the frontend update.
7. **Rehearse** with `BENCHCHECK_EVIDENCE_MODE=cache python -m benchcheck` as the fallback.

## Code map

| Path | What it does |
|---|---|
| `benchcheck/app.py` | FastAPI endpoints: `/api/inspect`, `/api/analyze`, `/api/evidence/{search,select,extract}`, `/api/report`, `/api/conversion-preview` |
| `benchcheck/cv/` | parsing, units, segmentation, peaks/baselines, analysis orchestrator, metadata status, reference conversions |
| `benchcheck/reasoning/` | `hypotheses.py` (rules, thresholds, query plan), `checks.py` (next-check ranking), `report.py` (report + exports) |
| `benchcheck/evidence/` | `serpapi.py` (client + cache), `sources.py` (evidence records, passages, Extract parsing), `conditions.py` (condition extraction/comparison), `pipeline.py` (server-side run for scripts) |
| `benchcheck/synth/` | thin-film and diffusion simulators (examples and validation) |
| `web/` | `index.html`, `app.js`, `styles.css`, vendored Plotly 2.35.3 |
| `examples/` | two SYNTHETIC CVs plus `.meta.json` (metadata, generator params, ground truth) |
| `scripts/` | `make_examples.py`, `refresh_demo_cache.py`, `evaluate.py` |
| `tests/` | 91 pytest tests; `tests/fixtures/` holds fake, clearly labeled SerpApi-shaped JSON (never copy into the cache) |

## Ground rules (keep these)

- Never invent papers, quotes, conditions, numbers or certainty scores. Passages must be verbatim slices of retrieved text.
- The cache holds only real live SerpApi responses, and anything served from it is labeled **cached** with its retrieval time.
- No mechanism is assigned to a peak; explanations are hypotheses tied to measured features.
- Reference conversion and area normalization require user confirmation.
- The API key stays server-side; `.env` is git-ignored.

## Known limitations

- Peak-height ratios read about 3–4% high on the clear example and 9–10% high on the weak example, because of the baseline window (measured, documented).
- Passage matching is lexical; a passage mentioning a phenomenon doesn't prove it explains the user's data.
- Only peaks of the expected sign per sweep are detected; overlapping peaks are not deconvoluted.
