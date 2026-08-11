\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\


import time
from collections import OrderedDict
from typing import Any, Optional


class TTLCache:
    def __init__(self, maxsize: int = 200, ttl_seconds: float = 900):
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        timestamp, value = item
        if time.time() - timestamp > self.ttl_seconds:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.time(), value)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)


ATTACHMENT_CACHE = TTLCache(maxsize=100, ttl_seconds=3600)                            
COUNCIL_RESULT_CACHE = TTLCache(maxsize=200, ttl_seconds=900)
