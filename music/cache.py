"""Thread-safe TTL cache restricted strictly to permitted metadata and provider status.

Audio binary content must never be cached or redistributed against provider terms.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple


class MetadataTTLCache:
    """In-memory LRU + TTL cache for API metadata responses."""

    def __init__(self, default_ttl: int = 300, max_entries: int = 1024) -> None:
        self.default_ttl = max(1, int(default_ttl))
        self.max_entries = max(16, int(max_entries))
        self._store: OrderedDict[str, Tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if now >= expires_at:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise ValueError("Caching raw binary/audio payloads is strictly prohibited.")
        ttl_seconds = self.default_ttl if ttl is None else max(1, int(ttl))
        expires_at = time.monotonic() + ttl_seconds
        with self._lock:
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            self._evict_if_needed()

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict_if_needed(self) -> None:
        now = time.monotonic()
        expired_keys = [k for k, (exp, _) in self._store.items() if now >= exp]
        for k in expired_keys:
            self._store.pop(k, None)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)
