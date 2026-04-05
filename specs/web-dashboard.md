# Web Dashboard Specification

**Status**: Draft | **Updated**: 2026-03-28

## Overview
Next.js web app reading from the shared SQLite database. Displays live portfolio performance, positions, trade journal, and Claude's analysis.

## Tech Stack
- **Framework**: Next.js 14+ (App Router)
- **Styling**: Tailwind CSS
- **Charts**: Recharts
- **DB Access**: better-sqlite3 (server-side only, via API routes)
- **Date Formatting**: date-fns

## Pages

### 1. Dashboard (`/`)
- **Hero stats row**: NAV, total return %, today's P&L, Sharpe ratio, max drawdown
- **Equity curve**: Line chart of daily NAV (from `portfolio_snapshots`)
- **Daily returns**: Bar chart (green/red) of daily returns
- **Asset allocation**: Donut chart by asset class (from open positions)
- **Market regime**: Badge showing Claude's latest assessment

### 2. Positions (`/positions`)
- **Open positions table**: ticker, name, direction, qty, entry price, current price, unrealized P&L (colored), % of NAV, stop-loss, take-profit
- **Filter**: by asset class (all, equities, bonds, commodities, options)
- **Margin bar**: visual indicator of margin utilization vs 60% limit
- **Closed positions**: toggle to show recently closed (last 30 days)

### 3. Trade Journal (`/trades`)
- **Table**: one row per **position** (open + closed): ticker, direction, status, qty, entry date/price/notional, exit date/price/notional (blank while open), P&L (realized when closed, unrealized when open)
- **Notionals**: `entry_notional_usd` / `exit_notional_usd` from SQLite (populated on open/close; legacy rows fallback to `|qty × price|`)
- **Pagination**: 20 positions per page; optional `ticker` search via query string

### 4. Performance (`/performance`)
- **Metrics grid**: Sharpe, Sortino, Calmar, win rate, profit factor, avg win/loss ratio
- **Rolling Sharpe**: Line chart (30-day rolling window)
- **Drawdown chart**: Area chart showing drawdown from peak
- **Monthly returns heatmap**: Grid of months × years, colored by return
- **Benchmark comparison**: Overlay S&P 500 returns on equity curve

### 5. Daily Analysis (`/analysis`)
- **Latest entry**: market regime, macro summary, expanded **`daily_findings`**, risk notes (from `daily_analysis`)
- **History**: scrollable list of past entries, one per trading day
- **Cost tracking**: tokens used, estimated API cost per day and cumulative

## API Routes
All data access via Next.js API routes (server-side SQLite queries):
- `GET /api/portfolio/summary` — latest snapshot + open positions
- `GET /api/portfolio/history?days=N` — NAV time series
- `GET /api/positions?status=OPEN|CLOSED` — positions list
- `GET /api/trades?page=N&limit=20&ticker=X` — paginated trades
- `GET /api/performance` — all performance metrics
- `GET /api/analysis?page=N` — daily analysis entries

## Database Path
The web app reads from `../storage/trading_bot.db` (relative to `web/` directory). Configured via environment variable `DATABASE_PATH`.
