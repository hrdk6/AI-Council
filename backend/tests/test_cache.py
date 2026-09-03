"""Tests for cache module."""

import asyncio

import pytest

from app.cache import TTLCache


@pytest.mark.asyncio
async def test_ttl_cache_basic():
    cache = TTLCache(maxsize=10, ttl_seconds=60)
    
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_ttl_cache_expiry():
    cache = TTLCache(maxsize=10, ttl_seconds=0.1)
    
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"
    
    await asyncio.sleep(0.15)
    assert await cache.get("key1") is None
    assert len(cache) == 0


@pytest.mark.asyncio
async def test_ttl_cache_maxsize():
    cache = TTLCache(maxsize=3, ttl_seconds=60)
    
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")
    assert len(cache) == 3
    
    await cache.set("key4", "value4")
    assert len(cache) == 3
    assert await cache.get("key1") is None  # LRU evicted
    assert await cache.get("key4") == "value4"


def test_ttl_cache_thread_safety():
    import threading
    
    cache = TTLCache(maxsize=100, ttl_seconds=60)
    errors = []
    
    def writer(i):
        try:
            asyncio.run(cache.set(f"key{i}", f"value{i}"))
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    
    def reader(i):
        try:
            asyncio.run(cache.get(f"key{i}"))
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    
    threads = []
    for i in range(50):
        threads.append(threading.Thread(target=writer, args=(i,)))
        threads.append(threading.Thread(target=reader, args=(i,)))
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0