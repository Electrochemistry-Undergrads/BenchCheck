"""Record REAL SerpApi responses for the offline fallback demo.

Runs the same evidence pipeline as the web app for both synthetic examples and
stores every live response verbatim in data/cache/demo/ (with retrieval times).
The web app labels anything served from this cache as "cached".

Requirements: SERPAPI_API_KEY in the environment or .env, and network access
to serpapi.com. Credit use per example: up to BENCHCHECK_MAX_QUERIES searches
plus BENCHCHECK_MAX_EXTRACTS Extract pages (defaults 3 + 5).

Usage:  python scripts/refresh_demo_cache.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchcheck.cv.analysis import analyze  # noqa: E402
from benchcheck.cv.parsing import parse_table  # noqa: E402
from benchcheck.evidence.pipeline import run_evidence  # noqa: E402
from benchcheck.evidence.serpapi import SerpApiClient, utc_now  # noqa: E402
from benchcheck.models import AnalysisConfig  # noqa: E402
from benchcheck.reasoning.hypotheses import evaluate, evidence_plan  # noqa: E402
from benchcheck.reasoning.report import build_report  # noqa: E402
from benchcheck.settings import get_settings  # noqa: E402

EXAMPLES = ["synthetic_lmo_weak_return", "synthetic_lmo_clear_return"]


def analysis_for(example_id: str, max_queries: int) -> dict:
    meta = json.loads((ROOT / "examples" / f"{example_id}.meta.json").read_text(encoding="utf-8"))
    cfg = AnalysisConfig(mapping=meta["mapping"], units=meta["units"], metadata=meta["metadata"], example_id=example_id)
    result = analyze(parse_table((ROOT / "examples" / meta["file"]).read_bytes(), meta["file"]), cfg)
    result["hypotheses"] = evaluate(result)
    result["evidence_plan"] = evidence_plan(result, result["hypotheses"], max_queries)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print the planned queries without calling SerpApi.")
    args = parser.parse_args()
    settings = get_settings()
    plans = {ex: analysis_for(ex, settings.max_queries) for ex in EXAMPLES}
    for ex, a in plans.items():
        print(f"\n{ex}: {len(a['evidence_plan'])} Scholar queries, up to {settings.max_extracts} Extract pages")
        for q in a["evidence_plan"]:
            print(f"  - {q['query']}")
    if args.dry_run:
        return 0
    if not settings.serpapi_key:
        print("\nSERPAPI_API_KEY is not set (environment or .env). Nothing was retrieved.", file=sys.stderr)
        return 2
    if settings.evidence_mode == "cache":
        print("\nBENCHCHECK_EVIDENCE_MODE=cache disables live calls. Unset it to refresh.", file=sys.stderr)
        return 2
    client = SerpApiClient(settings, write_to="demo")
    manifest = {"refreshed_at": utc_now(), "note": "Real SerpApi responses stored verbatim for the offline demo.",
                "examples": {}}
    out_dir = ROOT / "docs" / "demo_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    for ex, a in plans.items():
        evidence = run_evidence(a, client, settings.max_extracts)
        report = build_report({k: v for k, v in a.items() if k != "data"}, evidence)
        (out_dir / f"{ex}.md").write_text(report["markdown"], encoding="utf-8")
        levels = {}
        for s in evidence["sources"]:
            levels[s["evidence_level"]] = levels.get(s["evidence_level"], 0) + 1
        manifest["examples"][ex] = {
            "mode": evidence["mode"],
            "queries": [{"query": q["query"], "status": q["status"]} for q in evidence["queries"]],
            "calls": [{k: e.get(k) for k in ("engine", "query", "url", "status", "retrieved_at", "serpapi_search_id",
                                             "error", "classification")} for e in evidence["log"]],
            "sources": len(evidence["sources"]),
            "evidence_levels": levels,
            "next_check": (report.get("next_check") or {}).get("title"),
        }
        print(f"\n{ex}: mode={evidence['mode']} sources={len(evidence['sources'])} levels={levels}")
        for e in evidence["log"]:
            print(f"  [{e['status']}] {e['engine']}: {e.get('query') or e.get('url')} {e.get('error') or ''}")
    (ROOT / "data" / "cache" / "demo").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "cache" / "demo" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("\nWrote data/cache/demo/ and docs/demo_reports/. Review the reports, then commit both folders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
