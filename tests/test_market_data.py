"""Market data technicals (offline-friendly)."""

import pandas as pd

from src.data import market_data


def test_rsi_atr_macd():
    close = pd.Series(range(50, 150), dtype=float)
    high = close + 1.0
    low = close - 1.0
    assert market_data._rsi(close) is not None
    assert market_data._atr(high, low, close) is not None
    m = market_data._macd(close)
    assert m["macd"] is not None
    assert m["signal"] is not None
    assert m["histogram"] is not None


def test_serialize_ticker_row():
    idx = pd.date_range("2026-01-01", periods=70, freq="B")
    hist = pd.DataFrame(
        {
            "Open": range(70),
            "High": [x + 1 for x in range(70)],
            "Low": [x - 1 for x in range(70)],
            "Close": range(70),
            "Volume": [1_000_000] * 70,
        },
        index=idx,
    )
    row = market_data._serialize_ticker_row("TEST", hist, {"name": "Test"})
    assert row["ticker"] == "TEST"
    assert row["last_close"] == 69.0
    assert row["sma_20"] is not None
    assert row["sma_50"] is not None
