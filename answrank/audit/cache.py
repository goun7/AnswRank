"""HTTP asset cache for auxiliary audit assets (robots.txt, llms.txt, llms-full.txt, sitemap.xml).

The main page HTML is intentionally NEVER cached — every audit must observe the
live document. Only side assets that rarely change and are re-requested for
every page of the same domain during batch audits are cached with a TTL.

This is a pure in-memory TTL cache with no external dependencies.
"""

import time
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, Callable, Awaitable, Any

import logging

logger = logging.getLogger("answrank.cache")


@dataclass
class _CacheEntry:
    value: Any
    stored_at: float
    ttl_seconds: float
    hits: int = 0

    def is_fresh(self, now: float) -> bool:
        """Önbellek girdisinin hâlâ taze olup olmadığını döndürür."""
        return (now - self.stored_at) < self.ttl_seconds


class TTLCache:
    """In-memory TTL cache with per-key locking to avoid thundering-herd fetches."""

    # A None result may mean "transient fetch failure", not proven absence — so
    # negatives are remembered only briefly and retried soon, while positives
    # keep the full TTL. Batches (which finish well under 60s) still dedupe.
    NEGATIVE_TTL_SECONDS = 60.0

    def __init__(self, default_ttl_seconds: float = 300.0, max_entries: int = 512):
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_entries
        self._store: Dict[str, _CacheEntry] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._hits = 0
        self._misses = 0
        self._fetches = 0

    def _evict_if_needed(self) -> None:
        """Simple FIFO-ish eviction: drop expired entries first, then oldest."""
        now = time.monotonic()
        if len(self._store) < self.max_entries:
            return
        # First pass: remove expired
        expired = [k for k, v in self._store.items() if not v.is_fresh(now)]
        for k in expired:
            self._store.pop(k, None)
            self._locks.pop(k, None)
        # Second pass: if still over, remove oldest stored_at
        while len(self._store) >= self.max_entries:
            oldest_key = min(self._store, key=lambda k: self._store[k].stored_at)
            self._store.pop(oldest_key, None)
            self._locks.pop(oldest_key, None)

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl_seconds: Optional[float] = None,
    ) -> Any:
        """Returns the cached value or fetches it exactly once per key.

        Concurrent callers for the same key await the same in-flight fetch
        (per-key asyncio.Lock), so a batch audit of 15 URLs on one domain
        triggers at most ONE robots.txt HTTP request.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        now = time.monotonic()

        entry = self._store.get(key)
        if entry is not None and entry.is_fresh(now):
            entry.hits += 1
            self._hits += 1
            return entry.value

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Double-check after acquiring the lock — another coroutine
            # may have populated it while we waited.
            now = time.monotonic()
            entry = self._store.get(key)
            if entry is not None and entry.is_fresh(now):
                entry.hits += 1
                self._hits += 1
                return entry.value

            self._misses += 1
            self._fetches += 1
            value = await fetcher()
            self._evict_if_needed()
            # None = "absent or not verifiable": cache it only briefly so a
            # transient network error can never masquerade as confirmed absence
            # for the full TTL window.
            effective_ttl = self.NEGATIVE_TTL_SECONDS if value is None else ttl
            self._store[key] = _CacheEntry(value=value, stored_at=time.monotonic(), ttl_seconds=effective_ttl)
            return value

    def invalidate(self, key: Optional[str] = None) -> None:
        """Drops one key or the whole cache."""
        if key is None:
            self._store.clear()
            self._locks.clear()
        else:
            self._store.pop(key, None)
            self._locks.pop(key, None)

    def stats(self) -> Dict[str, Any]:
        """Cache observability: hit/miss counters and entry count."""
        return {
            "entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "fetches": self._fetches,
            "hit_rate_pct": round(100.0 * self._hits / (self._hits + self._misses), 1) if (self._hits + self._misses) else 0.0,
        }


# Singleton caches shared across engines within one process.
# robots/llms/llms-full change rarely — 5 minutes TTL is safe for audits.
# sitemap.xml — same class of asset.
asset_cache = TTLCache(default_ttl_seconds=300.0, max_entries=512)

__all__ = ["TTLCache", "asset_cache"]
