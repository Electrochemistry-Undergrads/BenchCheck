# SerpApi response cache

Only **real, live SerpApi responses** are ever written here, verbatim, by `benchcheck/evidence/serpapi.py`, together with the UTC time they were retrieved. Nothing else writes to this folder, and files must not be edited by hand.

- `live/` — responses from normal use of the app (git-ignored; local only).
- `demo/` — responses recorded by `scripts/refresh_demo_cache.py` for the offline fallback demo (committed). `manifest.json` lists the queries, call statuses and retrieval times.

Whenever the app serves a response from either folder, it is labeled **cached** in the UI, the evidence log and exported reports, with the original retrieval time. Stored request parameters never include the API key; any accidental echo of the key is redacted before writing.

Test fixtures (`tests/fixtures/`) are synthetic and must never be copied here.
