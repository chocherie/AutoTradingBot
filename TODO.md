# AutoTradingBot — Implementation Roadmap

## Status
| Phase | Status | Description |
|-------|--------|-------------|
| 0 | ✅ Done | Project scaffold |
| 1 | ✅ Done | Data pipeline |
| 2 | ✅ Done | Portfolio & execution engine |
| 3 | ✅ Done | Claude brain |
| 4 | ✅ Done | Orchestrator, journal & performance |
| 5 | ✅ Done | Web dashboard |
| 6 | ✅ Done | Scheduling & polish (baseline) |

## Phase 1: Data Pipeline
- [x] `src/data/market_data.py` — yfinance wrapper with technicals + options chains
- [x] `src/data/economic_data.py` — FRED wrapper for macro indicators
- [x] `src/data/news_sentiment.py` — Finnhub news + VADER sentiment
- [x] `src/data/data_cache.py` — SQLite TTL cache
- [x] `src/utils/logging_config.py` — Structured JSON logging
- [x] Verify: fetch real data from all sources (requires `FRED_API_KEY`, `FINNHUB_API_KEY`; yfinance has no key)

## Phase 2: Portfolio & Execution
- [x] `src/portfolio/position.py` — Position dataclass (futures, options, ETF)
- [x] `src/portfolio/portfolio.py` — Portfolio state, NAV, SQLite persistence
- [x] `src/portfolio/margin.py` — Margin calculation per instrument type
- [x] `src/portfolio/instrument_registry.py` — Universe metadata from YAML
- [x] `src/portfolio/risk.py` — Limits, heat, circuit checks, `validate_order`
- [x] `src/execution/order.py` — `OrderIntent` (Pydantic)
- [x] `src/execution/simulator.py` — Paper fills with slippage/commissions
- [x] Verify: mock trade lifecycle (see `tests/test_portfolio.py`)

## Phase 3: Claude Brain
- [x] `src/brain/claude_client.py` — Anthropic SDK wrapper (Opus)
- [x] `src/brain/prompt_builder.py` — 4-section daily prompt assembly
- [x] `src/brain/response_parser.py` — Pydantic-validated JSON parsing + repair pass via second call
- [x] Verify: `tests/test_response_parser.py`; live call needs `ANTHROPIC_API_KEY`

## Phase 4: Orchestrator & Journal
- [x] `src/journal/trade_journal.py` — Trade DB queries
- [x] `src/journal/performance.py` — Sharpe, drawdown, snapshot helpers
- [x] `src/main.py` — Daily pipeline (`--skip-claude` for data-only)
- [x] `daily_analysis` table + extended `trades` (confidence, signal_source)
- [x] Verify: `python -m src.main --skip-claude`

## Phase 5: Web Dashboard
- [x] Next.js 14 app in `web/` (Tailwind, Recharts, better-sqlite3)
- [x] Pages: `/`, `/positions`, `/trades`, `/performance`, `/analysis`
- [x] API routes per `specs/web-dashboard.md`
- [x] Verify: `cd web && npm run build`

## Phase 6: Scheduling & Polish
- [x] `scripts/run_daily.sh` — Cron-friendly wrapper
- [x] Baseline unit tests (`pytest tests/`)
- [ ] Cron on host (operator): 17:00 ET weekdays — not automated in-repo
- [ ] First live daily run — operator

## Decision Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-28 | Paper trading only | Start without real money risk |
| 2026-03-28 | Claude Opus model | Best reasoning for complex multi-asset decisions |
| 2026-03-28 | Include options | More expressive trading strategies |
| 2026-03-28 | Next.js dashboard | Full-featured React framework with SSR |
| 2026-03-28 | SQLite database | Zero infrastructure, sufficient for daily writes |
