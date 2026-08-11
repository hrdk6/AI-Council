"""
Small dependency-free TTL+LRU cache.

Two things get expensive to redo and are both safe to cache because they're
pure functions of their input bytes/text:

  1. OCR / vision transcription of an uploaded file (ingestion.py) — keyed by
     a hash of the file's raw bytes, so the *same* PDF/image uploaded again
     (even in a different conversation) skips the vision call entirely.
  2. A full council deliberation — keyed by a hash of (prompt, context), so an
     identical question (e.g. a user double-submitting, or a retry after a
     network blip on the frontend) doesn't re-spend 6-10 LLM calls.

This is intentionally in-process memory, not Redis/disk. It resets on
restart and isn't shared across workers. That's a fine trade for a single-
instance deployment; swap the internals for a Redis-backed store if this
runs behind multiple workers.
"""

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


# Shared instances imported by ingestion.py and council.py.
ATTACHMENT_CACHE = TTLCache(maxsize=100, ttl_seconds=3600)   # extracted file text, 1h
COUNCIL_RESULT_CACHE = TTLCache(maxsize=200, ttl_seconds=900)  # full deliberations, 15m