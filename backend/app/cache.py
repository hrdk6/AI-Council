import asyncio
import time
from collections import OrderedDict
from typing import Any

from .config import cfg


class TTLCache:
    def __init__(self, maxsize: int = 200, ttl_seconds: float = 900):
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            timestamp, value = item
            if time.time() - timestamp > self.ttl_seconds:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (time.time(), value)
            while len(self._store) > self.maxsize:
                self._store.popitem(last=False)

    def __len__(self) -> int:
        # Note: This is not thread-safe without the lock, but used for monitoring only
        return len(self._store)


COUNCIL_RESULT_CACHE = TTLCache(maxsize=cfg.council_cache_maxsize, ttl_seconds=cfg.council_cache_ttl)
