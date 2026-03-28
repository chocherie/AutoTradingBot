"""Query helpers for trade history (used by API / future tooling)."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.journal.performance import db_path


def fetch_trades(
    *,
    limit: int = 20,
    offset: int = 0,
    ticker: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    path = db_path()
    if not path.exists():
        return [], 0
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        where = ""
        params: List[Any] = []
        if ticker:
            where = " WHERE ticker LIKE ?"
            params.append(f"%{ticker}%")
        total = conn.execute(f"SELECT COUNT(*) FROM trades{where}", params).fetchone()[0]
        qparams = list(params) + [limit, offset]
        rows = conn.execute(
            f"""SELECT * FROM trades {where} ORDER BY id DESC LIMIT ? OFFSET ?""",
            qparams,
        ).fetchall()
        return [dict(r) for r in rows], int(total)
    finally:
        conn.close()
