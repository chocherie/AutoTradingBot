"""FRED macro indicators with SQLite TTL cache."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from typing import Optional, Tuple

import pandas as pd
from fredapi import Fred

from src.data.data_cache import cache_key, get_cached, set_cached
from src.utils.retry import with_backoff

logger = logging.getLogger(__name__)

# FRED series id -> display label (per specs/data-pipeline.md)
FRED_SERIES: dict[str, str] = {
    "GDP": "GDP (level)",
    "CPIAUCSL": "CPI (YoY %)",
    "UNRATE": "Unemployment rate",
    "DFF": "Fed funds effective",
    "DGS10": "10Y Treasury",
    "DGS2": "2Y Treasury",
    "T10Y2Y": "10Y-2Y spread",
    "VIXCLS": "VIX",
    "MANEMP": "Manufacturing employment",
    "UMCSENT": "Consumer sentiment",
}

ECONOMIC_TTL_SECONDS = 24 * 3600


def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _fred_client() -> Fred:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY is not set")
    return Fred(api_key=api_key)


def _latest_prior(
    series: pd.Series,
) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    series = series.dropna()
    if series.empty:
        return None, None, None, None
    latest_val = float(series.iloc[-1])
    latest_dt = series.index[-1]
    latest_date = latest_dt.date().isoformat() if hasattr(latest_dt, "date") else str(latest_dt)[:10]
    if len(series) < 2:
        return latest_val, None, latest_date, None
    prior_val = float(series.iloc[-2])
    prior_dt = series.index[-2]
    prior_date = prior_dt.date().isoformat() if hasattr(prior_dt, "date") else str(prior_dt)[:10]
    return latest_val, prior_val, latest_date, prior_date


def _cpi_yoy(
    series: pd.Series,
) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    series = series.dropna()
    if len(series) < 13:
        return None, None, None, None
    yoy = (series / series.shift(12) - 1.0) * 100.0
    yoy = yoy.dropna()
    if yoy.empty:
        return None, None, None, None
    latest = float(yoy.iloc[-1])
    latest_dt = yoy.index[-1]
    latest_date = latest_dt.date().isoformat() if hasattr(latest_dt, "date") else str(latest_dt)[:10]
    if len(yoy) < 2:
        return latest, None, latest_date, None
    prior = float(yoy.iloc[-2])
    prior_dt = yoy.index[-2]
    prior_date = prior_dt.date().isoformat() if hasattr(prior_dt, "date") else str(prior_dt)[:10]
    return latest, prior, latest_date, prior_date


def fetch_economic_snapshot(as_of: Optional[date] = None) -> dict:
    """Return latest + prior for each configured FRED series. Cached daily."""
    day = (as_of or datetime.now(timezone.utc).date()).isoformat()
    ck = cache_key("fred", "snapshot", day)
    hit = get_cached(ck)
    if hit is not None:
        return hit

    fred = _fred_client()
    out: dict = {"as_of": day, "series": {}}

    for sid, label in FRED_SERIES.items():
        try:
            def fetch_one() -> pd.Series:
                return fred.get_series(sid)

            s = with_backoff(fetch_one, operation=f"fred:{sid}")
            if sid == "CPIAUCSL":
                latest, prior, ld, pd_ = _cpi_yoy(s)
            else:
                latest, prior, ld, pd_ = _latest_prior(s)
            out["series"][sid] = {
                "label": label,
                "latest": latest,
                "prior": prior,
                "latest_date": ld,
                "prior_date": pd_,
            }
        except Exception as e:
            logger.warning("fred_series_failed", extra={"series": sid, "error": str(e)})
            out["series"][sid] = {
                "label": label,
                "latest": None,
                "prior": None,
                "latest_date": None,
                "prior_date": None,
                "error": str(e),
            }

    set_cached(ck, out, ttl_seconds=ECONOMIC_TTL_SECONDS)
    return out
