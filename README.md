# BenchCheck

BenchCheck helps researchers make sense of a cyclic voltammogram (CV). Upload your data and it measures the peaks, suggests possible explanations, pulls supporting passages from the literature, and recommends what to check next.

## Features

- **Upload** CSV/TXT exports from most potentiostats and confirm the detected columns and units.
- **Measure** peaks, ΔEp, peak-height and charge ratios, cycle-to-cycle trends, and data-quality issues.
- **Explain** observations with rule-based hypotheses, each tied to the measured feature that triggered it.
- **Search** Google Scholar through [SerpApi](https://serpapi.com), quote matching passages verbatim, and compare each paper's conditions with yours.
- **Recommend** the next measurement that best separates the competing explanations.
- **Export** a report (Markdown, HTML, or JSON).

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/Electrochemistry-Undergrads/BenchCheck.git
cd BenchCheck
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # add your SerpApi key
python -m benchcheck
```

Then open http://127.0.0.1:8000.

The numerical analysis works without a SerpApi key; only the literature search needs one.

## Configuration

Set these in `.env`:

| Variable | Default | Description |
|---|---|---|
| `SERPAPI_API_KEY` | — | Your SerpApi key |
| `BENCHCHECK_EVIDENCE_MODE` | `auto` | `auto`, `live`, or `cache` |
| `BENCHCHECK_MAX_QUERIES` | `3` | Scholar searches per analysis |
| `BENCHCHECK_MAX_EXTRACTS` | `5` | Pages extracted per analysis |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
python scripts/evaluate.py
```

## Project structure

```
benchcheck/   FastAPI backend, CV analysis, hypotheses, literature evidence
web/          Browser interface
examples/     Synthetic example CVs
scripts/      Evaluation and data-generation scripts
tests/        Test suite
docs/         Evaluation details
```

## Acknowledgments

Built for HackTX 2026. Frontend styling adapted from [Hallmark](https://github.com/Nutlope/hallmark) ([MIT license](LICENSES/Hallmark-MIT.txt)).
