"""SQLite TTL cache for API responses."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from src.utils.config import load_settings
from src.utils.paths import project_root

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    settings = load_settings()
    rel = settings.get("database", {}).get("path", "storage/trading_bot.db")
    return project_root() / Path(rel)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def ensure_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_cache (
            cache_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
        """
    )
    conn.commit()


def purge_expired(conn: sqlite3.Connection) -> int:
    now = time.time()
    cur = conn.execute("DELETE FROM data_cache WHERE expires_at <= ?", (now,))
    conn.commit()
    return cur.rowcount


def get_cached(cache_key: str) -> Optional[Any]:
    with _connect() as conn:
        ensure_cache_table(conn)
        purge_expired(conn)
        row = conn.execute(
            "SELECT payload FROM data_cache WHERE cache_key = ? AND expires_at > ?",
            (cache_key, time.time()),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])


def set_cached(cache_key: str, value: Any, ttl_seconds: float) -> None:
    payload = json.dumps(value, default=str)
    expires_at = time.time() + ttl_seconds
    with _connect() as conn:
        ensure_cache_table(conn)
        conn.execute(
            """
            INSERT INTO data_cache (cache_key, payload, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload = excluded.payload,
                expires_at = excluded.expires_at
            """,
            (cache_key, payload, expires_at),
        )
        conn.commit()


def cache_key(source: str, identifier: str, date_str: str) -> str:
    return f"{source}:{identifier}:{date_str}"
