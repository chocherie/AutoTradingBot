"""data_cache TTL behavior."""

import json
import time

from src.data import data_cache


def test_write_read_expire_cycle(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(data_cache, "_db_path", lambda: db)

    k = data_cache.cache_key("test", "id1", "2026-03-28")
    data_cache.set_cached(k, {"x": 1}, ttl_seconds=3600)
    assert data_cache.get_cached(k) == {"x": 1}

    data_cache.set_cached(k, {"x": 2}, ttl_seconds=0.01)
    time.sleep(0.05)
    assert data_cache.get_cached(k) is None
