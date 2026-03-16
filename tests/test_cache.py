import os
import time
from pathlib import Path

from hallubib import cache


def test_put_and_get(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cache.put("test_ns", "abc123", {"foo": "bar"})
    result = cache.get("test_ns", "abc123")
    assert result == {"foo": "bar"}


def test_get_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache.get("test_ns", "nonexistent") is None


def test_ttl_expiry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cache.put("test_ns", "old", {"val": 1})
    f = tmp_path / "hallubib" / "test_ns" / "old.json"
    old_time = time.time() - 31 * 86400
    os.utime(f, (old_time, old_time))
    assert cache.get("test_ns", "old") is None


def test_clear(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cache.put("test_ns", "x", {"v": 1})
    cache.clear()
    assert not (tmp_path / "hallubib").exists()


def test_cache_key_deterministic():
    k1 = cache.cache_key("hello")
    k2 = cache.cache_key("hello")
    assert k1 == k2
    assert k1 != cache.cache_key("world")
