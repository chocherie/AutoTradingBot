# Architecture

For a **non-technical, friendly explanation** of how the bot thinks about opening and closing trades (stops, circuit breakers, Claude vs the risk engine), see [user-guide-trading-decisions.md](./user-guide-trading-decisions.md).

## System Overview
AutoTradingBot is a daily-cycle trading system where Claude Opus acts as a systematic macro trader. Each trading day follows a fixed pipeline: collect market data → enforce existing stops → present data to Claude → execute Claude's decisions → record everything.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Data Layer  │────▶│  Claude Brain │────▶│  Execution  │
│  (collect)   │     │  (analyze)    │     │  (simulate) │
└─────────────┘     └──────────────┘     └─────────────┘
       │                    │                     │
       └────────────────────┴─────────────────────┘
                            │
                    ┌───────▼───────┐
                    │   Portfolio    │
                    │   (state)     │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │   SQLite DB   │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │  Web Dashboard │
                    │  (Next.js)    │
                    └───────────────┘
```

## Domain Organization

### `src/data/` — Data Collection
Collects market prices (yfinance), economic indicators (FRED), and news sentiment (Finnhub + VADER). All data cached in SQLite with TTL to avoid redundant API calls.

**Modules**: `data_cache.py` (TTL + `data_cache` table), `market_data.py` (`fetch_market_snapshot`), `economic_data.py` (`fetch_economic_snapshot`), `news_sentiment.py` (`fetch_news_sentiment`). **Utils**: `utils/config.py`, `utils/logging_config.py`, `utils/paths.py`, `utils/retry.py`.

### `src/portfolio/` — Portfolio State
**Modules**: `instrument_registry.py` (YAML → `InstrumentMeta`), `position.py`, `margin.py`, `risk.py` (`validate_order`, heat, circuit helpers), `portfolio.py` (`Portfolio` + SQLite tables: `portfolio_meta`, `positions`, `trades`, `portfolio_snapshots`). Futures use **fractional contracts** in paper mode so position sizing can respect % NAV limits at $1M capital.

### `src/execution/` — Paper Execution
**Modules**: `order.py` (`OrderIntent`), `simulator.py` (`PaperSimulator.execute_intent` — incremental BUY/SHORT merges into the same open leg with VWAP entry when ticker/direction/instrument match).

### `src/brain/` — Claude
**Modules**: `claude_client.py` (system prompt + `call_claude` + cost estimate), `prompt_builder.py` (4 sections), `response_parser.py` (`ClaudeDecision`, `parse_claude_response`, `orders_to_intents`). Package `__init__` stays light — import submodules directly to avoid loading Anthropic until needed.

### `src/journal/` — Metrics
**Modules**: `performance.py` (NAV series, Sharpe, drawdown from snapshots), `trade_journal.py` (SQL helpers).

### `src/main.py`
Orchestrates: data fetch → price update → stop/TP + circuit halt → prompt → Claude → `daily_analysis` (incl. `daily_findings` narrative) + orders → `portfolio_snapshots`.

### `web/` — Dashboard
Next.js App Router, Tailwind, Recharts; `lib/db.ts` + `lib/data.ts` read SQLite (read-only). Override DB path with `DATABASE_PATH`. On Vercel, `getDbAsync` can pull the latest copy from **Vercel Blob** (`BLOB_READ_WRITE_TOKEN`), re-fetching when blob `uploadedAt` or `size` changes; `src/utils/dashboard_sync.py` snapshots the DB via SQLite `backup()` (WAL-safe) then `POST /api/admin/sync-db` after each `src.main` run when `DASHBOARD_DB_SYNC_*` is set. API routes under `app/api/*`.

### `scripts/run_daily.sh`
Sets `PYTHONPATH` and runs `python3 -m src.main`.

### `src/brain/` — Claude Integration
The most architecturally important domain. `prompt_builder.py` assembles a structured 4-section prompt from collected data and portfolio state. `response_parser.py` validates Claude's JSON output into typed `OrderIntent` objects.

### `src/portfolio/` — Portfolio State
Source of truth for positions, cash, NAV, and margin. Handles futures (with multipliers), options (with Greeks), and ETFs. Enforces risk limits and circuit breakers.

### `src/execution/` — Paper Trade Simulator
Converts `OrderIntent` objects into executed trades with realistic slippage and commissions. Validates orders against risk limits before filling.

### `src/journal/` — Trade Journal & Performance
Logs every trade with Claude's rationale. Calculates Sharpe, Sortino, Calmar, drawdown, win rate, profit factor.

### `web/` — Next.js Dashboard
Reads from the same SQLite database. 5 pages: dashboard (NAV curve), positions, trade journal, performance metrics, daily analysis log.

## Technical Guidelines
- **Python 3.10+** for the trading bot
- **SQLite in WAL mode** for concurrent read (web) / write (bot) access
- **Pydantic v2** for all data validation
- **Structured JSON logging** for all events
- All monetary values stored as floats with 2 decimal precision
- Dates stored as ISO 8601 strings (YYYY-MM-DD)
