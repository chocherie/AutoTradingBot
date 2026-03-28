"""yfinance market data: OHLCV, technicals, options summaries."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from src.data.data_cache import cache_key, get_cached, set_cached
from src.utils.config import load_instruments, load_settings
from src.utils.retry import with_backoff

logger = logging.getLogger(__name__)

MARKET_TTL_SECONDS = 3600


def _build_ticker_meta(instruments: dict[str, Any]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for category, rows in instruments.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            t = row.get("ticker")
            if not t:
                continue
            meta[t] = {"name": row.get("name", t), "category": category}
            fx = row.get("fx_ticker")
            if fx:
                meta.setdefault(fx, {"name": row.get("fx_ticker", fx), "category": "fx_rates"})
    return meta


def _ordered_tickers(instruments: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _cat, rows in instruments.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            for key in ("ticker", "fx_ticker"):
                t = row.get(key)
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
    return out


def _options_underlyings(instruments: dict[str, Any]) -> list[str]:
    rows = instruments.get("options_underlyings") or []
    return [r["ticker"] for r in rows if r.get("ticker")]


def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    ag = float(avg_gain.iloc[-1]) if len(avg_gain) else 0.0
    al = float(avg_loss.iloc[-1]) if len(avg_loss) else 0.0
    if al == 0.0 and ag > 0.0:
        return 100.0
    if ag == 0.0 and al > 0.0:
        return 0.0
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1] if len(rsi) else None
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return float(val)


def _atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> Optional[float]:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    val = atr.iloc[-1] if len(atr) else None
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return float(val)


def _macd(close: pd.Series) -> Dict[str, Optional[float]]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    line = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    hist = line - signal
    if line.empty:
        return {"macd": None, "signal": None, "histogram": None}
    i = -1
    m, s, h = float(line.iloc[i]), float(signal.iloc[i]), float(hist.iloc[i])
    if any(np.isnan(x) for x in (m, s, h)):
        return {"macd": None, "signal": None, "histogram": None}
    return {"macd": m, "signal": s, "histogram": h}


def _fetch_history(ticker: str, lookback_days: int) -> pd.DataFrame:
    t = yf.Ticker(ticker)

    def load() -> pd.DataFrame:
        return t.history(period=f"{lookback_days}d", auto_adjust=True)

    return with_backoff(load, operation=f"yfinance:{ticker}")


def _options_summary(ticker: str) -> Optional[Dict[str, Any]]:
    try:
        t = yf.Ticker(ticker)
        exps: tuple[str, ...] = getattr(t, "options", ()) or ()
        if not exps:
            return None
        expiry = exps[0]
        chain = t.option_chain(expiry)
        hist = t.history(period="5d", auto_adjust=True)
        if hist.empty:
            spot = None
        else:
            spot = float(hist["Close"].iloc[-1])
        calls = chain.calls
        puts = chain.puts
        out: dict[str, Any] = {
            "nearest_expiry": expiry,
            "spot": spot,
            "calls_sample": [],
            "puts_sample": [],
        }
        if spot is not None and not calls.empty:
            calls = calls.copy()
            calls["strike_dist"] = (calls["strike"] - spot).abs()
            take = calls.nsmallest(5, "strike_dist")
            for _, r in take.iterrows():
                out["calls_sample"].append(
                    {
                        "strike": float(r["strike"]),
                        "impliedVolatility": float(r["impliedVolatility"])
                        if pd.notna(r.get("impliedVolatility"))
                        else None,
                        "volume": float(r["volume"]) if pd.notna(r.get("volume")) else None,
                        "openInterest": float(r["openInterest"])
                        if pd.notna(r.get("openInterest"))
                        else None,
                    }
                )
        if spot is not None and not puts.empty:
            puts = puts.copy()
            puts["strike_dist"] = (puts["strike"] - spot).abs()
            takep = puts.nsmallest(5, "strike_dist")
            for _, r in takep.iterrows():
                out["puts_sample"].append(
                    {
                        "strike": float(r["strike"]),
                        "impliedVolatility": float(r["impliedVolatility"])
                        if pd.notna(r.get("impliedVolatility"))
                        else None,
                        "volume": float(r["volume"]) if pd.notna(r.get("volume")) else None,
                        "openInterest": float(r["openInterest"])
                        if pd.notna(r.get("openInterest"))
                        else None,
                    }
                )
        return out
    except Exception as e:
        logger.warning("options_chain_failed", extra={"ticker": ticker, "error": str(e)})
        return None


def _serialize_ticker_row(ticker: str, hist: pd.DataFrame, meta: dict[str, Any]) -> dict[str, Any]:
    hist = hist.dropna(how="all")
    if hist.empty or "Close" not in hist:
        return {
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "error": "no_history",
        }
    close = hist["Close"]
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else last_close
    change_pct = (last_close / prev_close - 1.0) * 100.0 if prev_close else 0.0
    prev_5 = close.iloc[-6] if len(close) > 6 else None
    change_5d_pct = (last_close / float(prev_5) - 1.0) * 100.0 if prev_5 else None

    high = hist["High"] if "High" in hist else close
    low = hist["Low"] if "Low" in hist else close
    vol_col = hist["Volume"] if "Volume" in hist else None

    sma_20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

    out: dict[str, Any] = {
        "ticker": ticker,
        "name": meta.get("name", ticker),
        "category": meta.get("category"),
        "last_close": last_close,
        "prev_close": prev_close,
        "change_pct": round(change_pct, 4),
        "change_5d_pct": round(change_5d_pct, 4) if change_5d_pct is not None else None,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "rsi_14": _rsi(close, 14),
        "atr_14": _atr(high, low, close, 14),
        "macd": _macd(close),
    }
    if vol_col is not None and len(vol_col):
        v = vol_col.iloc[-1]
        out["volume"] = float(v) if pd.notna(v) else None
    return out


def fetch_market_snapshot(options_chains: bool = True) -> dict[str, Any]:
    """OHLCV + technicals for universe; optional options summaries for underlyings."""
    settings = load_settings()
    instruments = load_instruments()
    lookback = int(settings.get("data", {}).get("lookback_days", 60))
    meta = _build_ticker_meta(instruments)
    tickers = _ordered_tickers(instruments)
    opt_set = set(_options_underlyings(instruments)) if options_chains else set()

    result: dict[str, Any] = {"tickers": {}}
    for ticker in tickers:
        ck = cache_key("yfinance", ticker, "spot")
        cached = get_cached(ck)
        if cached is not None:
            result["tickers"][ticker] = cached
            continue
        try:
            hist = _fetch_history(ticker, lookback)
            row = _serialize_ticker_row(ticker, hist, meta.get(ticker, {}))
            if ticker in opt_set:
                row["options"] = _options_summary(ticker)
            result["tickers"][ticker] = row
            set_cached(ck, row, ttl_seconds=MARKET_TTL_SECONDS)
        except Exception as e:
            logger.warning("market_ticker_failed", extra={"ticker": ticker, "error": str(e)})
            result["tickers"][ticker] = {
                "ticker": ticker,
                "name": meta.get(ticker, {}).get("name", ticker),
                "error": str(e),
            }

    return result


def last_close_prices(market_snapshot: Dict[str, Any]) -> Dict[str, float]:
    """Flat map ticker -> last_close for portfolio pricing."""
    out: Dict[str, float] = {}
    for t, row in (market_snapshot.get("tickers") or {}).items():
        if not isinstance(row, dict) or "error" in row:
            continue
        lc = row.get("last_close")
        if lc is None:
            continue
        try:
            out[t] = float(lc)
        except (TypeError, ValueError):
            continue
    return out
