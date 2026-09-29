"""Content-addressed disk cache for LLM completions.

Every call to an LLM is expensive and, at temperature 0, deterministic given its
inputs. Caching on a hash of those inputs makes re-running the eval harness or
re-processing an unchanged protocol free, and is a prerequisite for the audit
trail (DESIGN.md L9) recording a stable ``prompt_hash``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

_DEFAULT_DB = Path("data/cache/llm.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS completions (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def cache_key(model: str, messages: list[dict], max_tokens: int) -> str:
    """Return a stable hash over everything that determines the response.

    Args:
        model: OpenRouter model slug.
        messages: The chat messages sent (system + user), in order.
        max_tokens: The response token cap (affects truncation, so it is
            part of the key).

    Returns:
        A hex sha256 digest usable as both the cache key and the audit
        trail's ``prompt_hash``.
    """
    payload = json.dumps(
        {"model": model, "messages": messages, "max_tokens": max_tokens},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMCache:
    """A sqlite-backed cache keyed by :func:`cache_key`.

    Args:
        path: Database file location. Defaults to ``data/cache/llm.sqlite``
            (gitignored), overridable via ``USDM4_CACHE_PATH``.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("USDM4_CACHE_PATH", _DEFAULT_DB))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, key: str) -> str | None:
        """Return the cached response for ``key``, or ``None`` on a miss."""
        row = self._conn.execute(
            "SELECT response FROM completions WHERE key = ?", (key,)
        ).fetchone()
        # Rows written before empty responses were refused are misses, not answers.
        return row[0] if row and row[0].strip() else None

    def put(self, key: str, *, model: str, prompt_hash: str, response: str) -> None:
        """Store a response under ``key``, overwriting any prior entry.

        An empty (or whitespace-only) response is a failed call, not an answer:
        it is never stored, so a re-run retries instead of replaying the failure.
        """
        if not response.strip():
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO completions "
            "(key, model, prompt_hash, response, created_at) VALUES (?, ?, ?, ?, ?)",
            (key, model, prompt_hash, response, time.time()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


_default_cache: LLMCache | None = None


def default_cache() -> LLMCache:
    """Return a process-wide default :class:`LLMCache` instance (lazy)."""
    global _default_cache
    if _default_cache is None:
        _default_cache = LLMCache()
    return _default_cache
