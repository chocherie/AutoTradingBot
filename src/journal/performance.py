"""Sharpe, drawdown, and snapshot helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.utils.config import load_settings
from src.utils.paths import project_root


def db_path() -> Path:
    s = load_settings()
    rel = s.get("database", {}).get("path", "storage/trading_bot.db")
    return project_root() / Path(rel)


def load_snapshot_rows(limit: int = 500) -> List[Tuple[Any, ...]]:
    path = db_path()
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            """SELECT date, nav, daily_return, cumulative_return, sharpe_ratio, max_drawdown
               FROM portfolio_snapshots ORDER BY date ASC LIMIT ?""",
            (limit,),
        ).fetchall()
        return list(rows)
    finally:
        conn.close()


def prior_nav_before(as_of: str) -> Optional[float]:
    """Previous session NAV for daily return: last snapshot strictly before *as_of*, else initial capital.

    Never use ``portfolio_meta.cash`` here — with open positions, cash understates total portfolio value
    and makes *daily return* look like ``NAV / cash - 1`` (bogus large positive prints).

    If there is no snapshot for intermediate calendar dates (e.g. weekend + holiday), the ratio
    ``NAV_today / prior_nav`` spans multiple trading sessions — not a single-day return unless you
    insert a row per session day.
    """
    path = db_path()
    if not path.exists():
        return float(load_settings().get("portfolio", {}).get("initial_capital", 1_000_000.0))
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT nav FROM portfolio_snapshots WHERE date < ? ORDER BY date DESC LIMIT 1",
            (as_of,),
        ).fetchone()
        if row:
            return float(row[0])
        return float(load_settings().get("portfolio", {}).get("initial_capital", 1_000_000.0))
    finally:
        conn.close()


def compute_metrics_from_nav_series(
    navs: List[float],
    *,
    initial_nav: float,
    annualization: float = 252.0,
) -> Dict[str, Optional[float]]:
    if len(navs) < 2:
        cum0 = ((navs[0] / initial_nav) - 1.0) if len(navs) == 1 and initial_nav else None
        return {
            "cumulative_return": float(cum0) if cum0 is not None else None,
            "sharpe_ratio": None,
            "max_drawdown": 0.0 if len(navs) == 1 else None,
            "sortino_ratio": None,
            "calmar_ratio": None,
        }
    arr = np.array(navs, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    cum = (arr[-1] / initial_nav) - 1.0 if initial_nav else None
    mu = float(np.mean(rets))
    sd = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
    sharpe = (mu / sd * np.sqrt(annualization)) if sd > 1e-12 else None
    downside = rets[rets < 0]
    dsd = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = (mu / dsd * np.sqrt(annualization)) if dsd > 1e-12 else None

    peak = np.maximum.accumulate(arr)
    dd = (peak - arr) / peak
    max_dd = float(np.max(dd)) if len(dd) else 0.0

    years = len(rets) / annualization
    total_ret = (arr[-1] / arr[0]) - 1.0 if arr[0] else 0.0
    cagr = ((1 + total_ret) ** (1 / years) - 1) if years > 0 and total_ret > -1 else 0.0
    calmar = (cagr / max_dd) if max_dd > 1e-8 else None

    return {
        "cumulative_return": float(cum) if cum is not None else None,
        "sharpe_ratio": float(sharpe) if sharpe is not None else None,
        "max_drawdown": max_dd,
        "sortino_ratio": float(sortino) if sortino is not None else None,
        "calmar_ratio": float(calmar) if calmar is not None else None,
    }


def next_metrics_for_prompt(
    as_of: str,
    current_nav: float,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(daily_return_pct, cumulative_return_pct, sharpe_from_history)."""
    prev = prior_nav_before(as_of)
    daily = None
    if prev and prev > 0:
        daily = (current_nav / prev - 1.0) * 100.0
    rows = load_snapshot_rows()
    navs = [float(r[1]) for r in rows] + [current_nav]
    initial = float(load_settings().get("portfolio", {}).get("initial_capital", 1_000_000.0))
    m = compute_metrics_from_nav_series(navs, initial_nav=initial)
    cum_pct = m["cumulative_return"] * 100.0 if m["cumulative_return"] is not None else None
    return daily, cum_pct, m["sharpe_ratio"]
