"""Journal metrics helpers."""

import sqlite3
from pathlib import Path

import pytest

from src.journal import performance as perf_mod


def test_prior_nav_before_uses_initial_capital_not_cash(tmp_path: Path, monkeypatch):
    """Cash fallback made daily return look like NAV/cash-1 when positions exist."""
    db = tmp_path / "t.db"
    monkeypatch.setattr(perf_mod, "db_path", lambda: db)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE portfolio_snapshots (date TEXT PRIMARY KEY, nav REAL, cash REAL, total_margin_used REAL, "
        "daily_return REAL, cumulative_return REAL, sharpe_ratio REAL, max_drawdown REAL)"
    )
    conn.execute(
        "CREATE TABLE portfolio_meta (id INTEGER PRIMARY KEY, cash REAL, peak_nav REAL)"
    )
    conn.execute("INSERT INTO portfolio_meta (id, cash, peak_nav) VALUES (1, 850000, 1000000)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        perf_mod,
        "load_settings",
        lambda: {"portfolio": {"initial_capital": 1_000_000.0}},
    )
    assert perf_mod.prior_nav_before("2026-03-30") == 1_000_000.0


def test_prior_nav_before_prefers_earlier_snapshot(tmp_path: Path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(perf_mod, "db_path", lambda: db)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE portfolio_snapshots (date TEXT PRIMARY KEY, nav REAL, cash REAL, total_margin_used REAL, "
        "daily_return REAL, cumulative_return REAL, sharpe_ratio REAL, max_drawdown REAL)"
    )
    conn.executemany(
        "INSERT INTO portfolio_snapshots VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-03-28", 1_000_000.0, 900_000.0, 0.0, 0.0, 0.0, None, 0.0),
            ("2026-03-29", 1_001_000.0, 900_000.0, 0.0, 0.001, 0.001, None, 0.0),
        ],
    )
    conn.commit()
    conn.close()
    assert perf_mod.prior_nav_before("2026-03-30") == 1_001_000.0
