"""Runtime configuration, read from environment variables (and an optional .env file).

The SerpApi key is only ever read here, on the server. It is never sent to the
browser, written to the cache, or included in logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EVIDENCE_MODES = ("auto", "live", "cache")


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Never overrides variables already set."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class Settings:
    serpapi_key: str | None
    evidence_mode: str
    cache_dir: Path
    max_queries: int
    max_extracts: int
    timeout_s: float

    @property
    def live_enabled(self) -> bool:
        """True when BenchCheck may call SerpApi over the network."""
        return self.evidence_mode in ("auto", "live") and bool(self.serpapi_key)

    def describe_mode(self) -> str:
        if self.live_enabled:
            return "live"
        return "cache"


def get_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    mode = os.environ.get("BENCHCHECK_EVIDENCE_MODE", "auto").strip().lower()
    if mode not in EVIDENCE_MODES:
        mode = "auto"
    key = os.environ.get("SERPAPI_API_KEY", "").strip() or None
    cache_dir = Path(os.environ.get("BENCHCHECK_CACHE_DIR", PROJECT_ROOT / "data" / "cache"))
    try:
        timeout = float(os.environ.get("BENCHCHECK_SERPAPI_TIMEOUT", "40"))
    except ValueError:
        timeout = 40.0
    return Settings(
        serpapi_key=key,
        evidence_mode=mode,
        cache_dir=cache_dir,
        max_queries=_int_env("BENCHCHECK_MAX_QUERIES", 3, 1, 6),
        max_extracts=_int_env("BENCHCHECK_MAX_EXTRACTS", 5, 0, 12),
        timeout_s=timeout,
    )
