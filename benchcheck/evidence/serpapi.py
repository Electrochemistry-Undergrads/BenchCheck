"""SerpApi client for the Google Scholar API and the Extract API, with a response cache.

* Google Scholar: GET https://serpapi.com/search.json?engine=google_scholar&q=...
* Extract API:    GET https://serpapi.com/search.json?engine=extract&url=...
  (launched October 2026; returns page_information, meta_tags, text_content, ...).

Cache rules (so cached evidence is always real evidence):
* Only successful, live SerpApi responses are written, verbatim, with the time
  they were retrieved. Nothing else writes to the cache.
* Responses served from the cache are always labeled `cached` together with
  their original retrieval time.
* The API key is never stored: request parameters are saved without it, and
  any accidental occurrence in a response or error message is redacted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..settings import Settings

SERPAPI_URL = "https://serpapi.com/search.json"
CACHE_FORMAT = "benchcheck-serpapi-cache/1"
EMPTY_RESULT_ERRORS = ("hasn't returned any results", "has not returned any results")

# httpx logs full request URLs (including query parameters) at INFO level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cache_key(params: dict) -> str:
    clean = {k: v for k, v in params.items() if k not in ("api_key", "no_cache", "async")}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass
class CallResult:
    ok: bool
    status: str  # "live" | "cached" | "error" | "unavailable"
    engine: str
    params: dict
    data: dict | None = None
    error: str | None = None
    cached: bool = False
    retrieved_at: str | None = None  # when SerpApi produced this response
    served_at: str | None = None
    elapsed_s: float | None = None
    fallback_note: str | None = None

    def log_entry(self, **extra) -> dict:
        meta = (self.data or {}).get("search_metadata") or {}
        entry = {
            "engine": self.engine,
            "query": self.params.get("q"),
            "url": self.params.get("url"),
            "status": self.status,
            "ok": self.ok,
            "cached": self.cached,
            "retrieved_at": self.retrieved_at,
            "served_at": self.served_at,
            "elapsed_s": self.elapsed_s,
            "error": self.error,
            "fallback_note": self.fallback_note,
            "serpapi_search_id": meta.get("id"),
            "serpapi_created_at": meta.get("created_at"),
            "google_scholar_url": meta.get("google_scholar_url"),
            "credits": 0 if self.cached or not self.ok else 1,
        }
        entry.update(extra)
        return entry


class ResponseCache:
    """Two folders: `live/` (local, git-ignored) and `demo/` (committed fallback demo evidence)."""

    def __init__(self, root: Path, write_to: str = "live"):
        self.root = Path(root)
        self.write_to = write_to

    def _path(self, folder: str, engine: str, key: str) -> Path:
        return self.root / folder / engine / f"{key}.json"

    def get(self, engine: str, key: str) -> dict | None:
        for folder in ("live", "demo"):
            path = self._path(folder, engine, key)
            if path.is_file():
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if record.get("format") == CACHE_FORMAT and "response" in record:
                    record["_folder"] = folder
                    return record
        return None

    def put(self, engine: str, key: str, params: dict, response: dict, retrieved_at: str, secret: str | None) -> Path:
        path = self._path(self.write_to, engine, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "format": CACHE_FORMAT,
            "note": "Verbatim SerpApi response retrieved live by BenchCheck. Do not edit.",
            "engine": engine,
            "params": {k: v for k, v in params.items() if k != "api_key"},
            "retrieved_at": retrieved_at,
            "serpapi_search_id": ((response or {}).get("search_metadata") or {}).get("id"),
            "response": response,
        }
        text = json.dumps(record, ensure_ascii=False, indent=1)
        if secret:
            text = text.replace(secret, "***REDACTED***")
        path.write_text(text, encoding="utf-8")
        return path

    def count(self) -> dict:
        out = {}
        for folder in ("live", "demo"):
            base = self.root / folder
            out[folder] = sum(1 for _ in base.glob("*/*.json")) if base.exists() else 0  # engine/key.json only
        return out


class SerpApiClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None, write_to: str = "live"):
        self.settings = settings
        self.cache = ResponseCache(settings.cache_dir, write_to=write_to)
        self._transport = transport

    def _redact(self, text: str) -> str:
        key = self.settings.serpapi_key
        return text.replace(key, "***") if key else text

    def call(self, engine: str, params: dict, prefer_cache: bool = False) -> CallResult:
        """Live call when enabled (falling back to cache on failure); cache only when live is disabled.

        With prefer_cache=True a previously retrieved response is reused (labeled cached) to save credits.
        """
        params = {"engine": engine, **params}
        key = cache_key(params)
        served = utc_now()
        record = self.cache.get(engine, key)

        def from_cache(note: str | None = None) -> CallResult:
            return CallResult(
                ok=True, status="cached", engine=engine, params=params, data=record["response"], cached=True,
                retrieved_at=record.get("retrieved_at"), served_at=served, fallback_note=note,
            )

        if record and (prefer_cache or not self.settings.live_enabled):
            return from_cache()
        if not self.settings.live_enabled:
            reason = ("SerpApi API key is not configured on the server"
                      if not self.settings.serpapi_key else "Live SerpApi calls are disabled (cache-only mode)")
            return CallResult(ok=False, status="unavailable", engine=engine, params=params, served_at=served,
                              error=f"{reason}, and no cached response exists for this request.")

        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.settings.timeout_s, transport=self._transport) as client:
                resp = client.get(SERPAPI_URL, params={**params, "api_key": self.settings.serpapi_key})
            elapsed = round(time.monotonic() - started, 2)
            try:
                data = resp.json()
            except ValueError:
                data = None
            error = None
            if data is None:
                error = f"SerpApi returned a non-JSON response (HTTP {resp.status_code})."
            elif "error" in data and not any(m in str(data["error"]) for m in EMPTY_RESULT_ERRORS):
                error = f"SerpApi error (HTTP {resp.status_code}): {data['error']}"
            elif resp.status_code >= 400:
                error = f"SerpApi returned HTTP {resp.status_code}."
            if error:
                error = self._redact(error)
                if record:
                    return from_cache(f"Live call failed ({error}); served the cached response instead.")
                return CallResult(ok=False, status="error", engine=engine, params=params, error=error,
                                  served_at=served, elapsed_s=elapsed)
            retrieved = utc_now()
            self.cache.put(engine, key, params, data, retrieved, self.settings.serpapi_key)
            return CallResult(ok=True, status="live", engine=engine, params=params, data=data, cached=False,
                              retrieved_at=retrieved, served_at=served, elapsed_s=elapsed)
        except httpx.HTTPError as exc:
            message = self._redact(f"Could not reach SerpApi ({type(exc).__name__}).")
            if record:
                return from_cache(f"{message} Served the cached response instead.")
            return CallResult(ok=False, status="error", engine=engine, params=params, error=message, served_at=served,
                              elapsed_s=round(time.monotonic() - started, 2))

    def scholar(self, query: str, num: int = 10, prefer_cache: bool = False) -> CallResult:
        return self.call("google_scholar", {"q": query, "hl": "en", "num": num}, prefer_cache)

    def extract(self, url: str, prefer_cache: bool = False) -> CallResult:
        return self.call("extract", {"url": url, "include_markdown": "true"}, prefer_cache)


def as_dict(result: CallResult) -> dict:
    return asdict(result)
