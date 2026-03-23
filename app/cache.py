from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Any, Callable, Hashable


class TtlCache:
    def __init__(self, *, ttl_seconds: int, max_entries: int):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0 and self.max_entries > 0

    def get(self, key: Hashable) -> Any | None:
        if not self.enabled:
            return None

        now = monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            expires_at, value = entry
            if expires_at <= now:
                self._store.pop(key, None)
                return None

            self._store.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any) -> Any:
        if not self.enabled:
            return value

        expires_at = monotonic() + self.ttl_seconds
        with self._lock:
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            self._evict_locked()
        return value

    def get_or_set(self, key: Hashable, loader: Callable[[], Any]) -> Any:
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value
        return self.set(key, loader())

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict_locked(self) -> None:
        now = monotonic()
        expired_keys = [key for key, (expires_at, _) in self._store.items() if expires_at <= now]
        for key in expired_keys:
            self._store.pop(key, None)

        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)
