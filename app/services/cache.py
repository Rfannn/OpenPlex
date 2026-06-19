import hashlib
import time
import logging
from typing import Any, Callable, Optional, Dict
from functools import wraps

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple in-memory cache with per-key TTL."""

    def __init__(self, default_ttl: int = 30):
        self._default_ttl = default_ttl
        self._store: Dict[str, tuple[float, Any, int]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, val, ttl = entry
        if time.time() - ts > ttl:
            del self._store[key]
            return None
        return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (time.time(), value, effective_ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def invalidate_pattern(self, prefix: str) -> None:
        for k in list(self._store.keys()):
            if k.startswith(prefix):
                del self._store[k]


# Global cache instance
response_cache = TTLCache(default_ttl=30)


def evict_oldest(cache: Dict[str, tuple], max_size: int) -> None:
    """Evict the oldest entry from a {key: (timestamp, value)} cache when it exceeds max_size."""
    while len(cache) > max_size:
        oldest_key = min(cache, key=lambda k: cache[k][0])
        del cache[oldest_key]


def _make_key(fn_name: str, args: tuple, kwargs: tuple) -> str:
    raw = f"{fn_name}:{args}:{kwargs}"
    return hashlib.md5(raw.encode("utf-8", errors="replace")).hexdigest()


def cached(ttl: int = 30):
    """Decorator: cache async function return value by (func_name, args, kwargs)."""
    def decorator(fn: Callable):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            key = _make_key(fn.__name__, args, tuple(sorted(kwargs.items())))
            cached_val = response_cache.get(key)
            if cached_val is not None:
                return cached_val
            result = await fn(*args, **kwargs)
            response_cache.set(key, result, ttl=ttl)
            return result
        return wrapper
    return decorator
