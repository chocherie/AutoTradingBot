# System Specification

**Status**: Draft | **Updated**: 2026-03-28

## Overview
AutoTradingBot is a daily-cycle paper trading system. Claude Opus analyzes multi-source market data and makes all trading decisions for a $1M portfolio of G7 exchange-traded instruments.

## Goals
1. Generate risk-adjusted returns measured by Sharpe ratio
2. Trade futures, options, and ETFs across equity indices, bonds, and commodities
3. Maintain full audit trail of every decision with rationale
4. Present live performance via web dashboard

## Architecture

### Daily Pipeline
```
17:00 ET Trigger (CLI or cron)
  ├── 1. Collect data (market, economic, news) — parallel
  ├── 2. Load portfolio, enforce stops/TPs
  ├── 3. Build prompt (4 sections)
  ├── 4. Call Claude Opus → parse JSON response
  ├── 5. Validate & execute orders (paper)
  └── 6. Record trades, update portfolio, snapshot metrics
```

### Core Types
```python
class Position:
    ticker: str
    asset_class: str          # equity_index, bond, commodity
    instrument_type: str      # future, option, etf
    direction: str            # LONG, SHORT
    quantity: float
    entry_price: float
    entry_date: str
    stop_loss: float
    take_profit: float
    # Options-specific (nullable)
    option_type: str | None   # CALL, PUT
    strike: float | None
    expiry: str | None

class OrderIntent:
    ticker: str
    action: str               # BUY, SELL, SHORT, COVER
    size_pct_nav: float
    order_type: str           # MARKET, LIMIT
    stop_loss_pct: float
    take_profit_pct: float
    rationale: str
    confidence: str           # HIGH, MEDIUM, LOW
    signal_source: str
    option_details: dict | None

class ClaudeDecision:
    market_regime: str        # RISK_ON, RISK_OFF, TRANSITIONAL, CRISIS
    macro_summary: str
    orders: list[OrderIntent]
    positions_to_close: list[str]
    risk_notes: str
```

## Database
SQLite with WAL mode at `storage/trading_bot.db`. Five tables: `portfolio_snapshots`, `positions`, `trades`, `daily_analysis`, `data_cache`.

## Error Handling
- Data failures: use cache, abort if all sources fail
- Claude failures: 3 retries, enforce stops only if exhausted
- Invalid JSON: 1 repair retry, skip new trades if still invalid
- Order validation: reject violations, log rejections

## Security
- API keys in `.env` (gitignored)
- No real broker connection
- SQLite file permissions restricted to owner
