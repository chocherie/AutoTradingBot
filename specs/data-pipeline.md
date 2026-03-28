# Data Pipeline Specification

**Status**: Draft | **Updated**: 2026-03-28

## Overview
Collects market prices, economic indicators, and news sentiment from free APIs. All data cached in SQLite with TTL to minimize API calls.

## Data Sources

### Market Data (`market_data.py`)
**Source**: yfinance
**Coverage**: All instruments in `config/instruments.yaml`
**Data collected per instrument**:
- OHLCV: 60-day lookback, daily bars
- Technicals: SMA-20, SMA-50, RSI-14, ATR-14, MACD (12,26,9)
- Options chains: for SPY, QQQ, TLT, GLD, USO — strikes, expiries, IV, Greeks

**Output format** (per instrument):
```python
{
    "ticker": "ES=F",
    "name": "S&P 500 E-mini",
    "last_close": 5250.50,
    "prev_close": 5230.00,
    "change_pct": 0.39,
    "change_5d_pct": 1.2,
    "sma_20": 5200.00,
    "sma_50": 5150.00,
    "rsi_14": 58.3,
    "atr_14": 45.2,
    "macd": {"macd": 12.5, "signal": 10.2, "histogram": 2.3},
    "volume": 1500000
}
```

### Economic Data (`economic_data.py`)
**Source**: FRED API (`fredapi`)
**Series fetched**:
| Indicator | FRED Series | Frequency |
|-----------|------------|-----------|
| GDP Growth | GDP | Quarterly |
| CPI (YoY) | CPIAUCSL | Monthly |
| Unemployment | UNRATE | Monthly |
| Fed Funds Rate | DFF | Daily |
| 10Y Treasury | DGS10 | Daily |
| 2Y Treasury | DGS2 | Daily |
| 10Y-2Y Spread | T10Y2Y | Daily |
| VIX | VIXCLS | Daily |
| PMI | MANEMP | Monthly |
| Consumer Sentiment | UMCSENT | Monthly |

**Output**: Latest value + prior value for trend context.

### News Sentiment (`news_sentiment.py`)
**Source**: Finnhub (`finnhub-python`)
**Process**: Fetch general market news → score each headline with VADER → aggregate by asset class. Up to `max_news_headlines` items per fetch are kept; rolling history stores the last `news_rolling_fetch_batches` fetches (FIFO: adding a batch evicts the oldest batch). Headlines older than `news_headline_retention_days` are dropped. SQLite key `finnhub:news:rolling_v1` persists batches; optional `news_finnhub_cooldown_hours` throttles API calls.
**Output**:
```python
{
    "headlines": [
        {"title": "...", "source": "...", "sentiment": 0.65, "datetime": "..."}
    ],
    "aggregate_sentiment": {
        "equities": 0.12,
        "bonds": -0.05,
        "commodities": 0.08,
        "overall": 0.05
    }
}
```

## Caching
- **Storage**: `data_cache` SQLite table
- **Key**: `{source}:{identifier}:{date}`
- **TTL**: 24 hours for economic data, 1 hour for market data; news uses rolling state with TTL tied to headline retention + slack (see `settings.yaml` `data.*news_*`)
- **Eviction**: Expired entries cleaned on each fetch cycle

## Error Handling
- Individual ticker failure: log warning, use cached value, continue
- Full source failure: log error, mark data as unavailable in prompt
- API rate limit: exponential backoff (2s, 4s, 8s)
