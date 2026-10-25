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
import ipaddress
import socket
from urllib.parse import urlsplit
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..settings import Settings

SERPAPI_URL = "https://serpapi.com/search.json"
CACHE_FORMAT = "benchcheck-serpapi-cache/1"
_DOMAIN_FAILURES = {}
DOMAIN_FAILURE_TTL = 900

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
    credit_estimate: int | None = None

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
            "credits": self.credit_estimate if self.credit_estimate is not None else (0 if self.cached or self.status == "provider-cached" or not self.ok else 1),
            "credits_are_estimates": True,
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
                error = f"SerpApi upstream error: {data['error']}"
            elif resp.status_code >= 400:
                error = f"SerpApi returned HTTP {resp.status_code}."
            if error:
                error = self._redact(error)
                if record:
                    return from_cache(f"Live call failed ({error}); served the cached response instead.")
                return CallResult(ok=False, status="error", engine=engine, params=params, error=error,
                                  served_at=served, elapsed_s=elapsed)
            created = (data.get("search_metadata") or {}).get("created_at")
            provider_cached = False
            if created:
                try:
                    produced = datetime.fromisoformat(created.replace(" UTC", "+00:00").replace("Z", "+00:00"))
                    if produced.tzinfo is None:
                        produced = produced.replace(tzinfo=timezone.utc)
                    provider_cached = (datetime.now(timezone.utc) - produced).total_seconds() > 60
                except (ValueError, TypeError):
                    pass
            retrieved = created if provider_cached else utc_now()
            self.cache.put(engine, key, params, data, retrieved, self.settings.serpapi_key)
            return CallResult(ok=True, status="provider-cached" if provider_cached else "live", engine=engine, params=params, data=data, cached=provider_cached,
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
        # Even server-selected search results can contain malicious target URLs.
        host = validate_public_url(url, resolve=self._transport is None)
        failure_key = (str(self.settings.cache_dir), host)
        failure = _DOMAIN_FAILURES.get(failure_key)
        if failure and time.monotonic() - failure[0] < DOMAIN_FAILURE_TTL:
            return CallResult(ok=False, status="unavailable", engine="extract", params={"url": url},
                              error="This domain recently failed extraction; retry after 15 minutes.")
        result = self.call("extract", {"url": url, "include_markdown": "true"}, prefer_cache)
        if result.ok:
            result.credit_estimate = 0 if result.cached else 1
            from .sources import parse_extract
            if parse_extract(result.data or {}).get("level") is None:
                result.ok, result.status = False, "error"
                result.error = "The retrieved page has no usable abstract or full text."
        if not result.ok and (result.status == "error" or "robots" in (result.error or "").lower()):
            _DOMAIN_FAILURES[failure_key] = (time.monotonic(), result.error)
        return result


def as_dict(result: CallResult) -> dict:
    return asdict(result)


def validate_public_url(url: str, resolve: bool = True) -> str:
    try:
        parsed = urlsplit(url.strip())
        host = parsed.hostname
        if parsed.scheme.lower() not in ("http", "https") or not host or parsed.username or parsed.password:
            raise ValueError
        if host.lower() == "localhost" or host.lower().endswith(".localhost"):
            raise ValueError
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or 443)] if resolve else []
        if any(not address.is_global for address in addresses):
            raise ValueError
        return host.lower()
    except (ValueError, OSError) as exc:
        raise ValueError("source link must resolve to a public HTTP/HTTPS address") from exc


def domain_recently_failed(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(key[1] == host and time.monotonic() - value[0] < DOMAIN_FAILURE_TTL for key, value in _DOMAIN_FAILURES.items())
