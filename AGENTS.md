# AutoTradingBot — Agent Orientation

## What This Is
A Claude Opus-powered paper trading bot managing a $1M portfolio across G7 exchange-traded instruments (futures, options, ETFs). Claude analyzes market data, news, economic indicators daily and makes all trading decisions. A Next.js dashboard displays live performance.

## Directory Map
```
src/data/          → Data collection: market prices, economic indicators, news sentiment
src/utils/         → Shared helpers: config, paths, retry, structured logging
src/portfolio/     → `Portfolio` (SQLite), positions, margin, `validate_order`, instrument registry
src/execution/     → `OrderIntent`, `PaperSimulator` (slippage + commissions)
src/brain/         → Claude integration: prompt building, API calls, response parsing
src/journal/       → Trade journal and performance metrics (Sharpe, drawdown, etc.)
src/main.py        → Daily cycle: `python -m src.main` (`--date`, `--skip-claude`, `--analysis-only`, `--force-daily-analysis`)
config/            → instruments.yaml (universe), settings.yaml (`trading.options_enabled`, risk, Claude, …)
web/               → Next.js 14 dashboard; local `DATABASE_PATH` or Vercel Blob (`BLOB_READ_WRITE_TOKEN`); blob/local DB open paths in `web/lib/db.ts` (cache invalidation); `src.main` POST via `DASHBOARD_DB_SYNC_*` → `/api/admin/sync-db` (upload uses SQLite backup for a consistent snapshot)
storage/           → SQLite database + logs (created at runtime, gitignored)
specs/             → System and module specifications (source of truth for design)
docs/              → Architecture, quality scorecard, core beliefs
tests/             → Unit and integration tests
```

## Environment
- `FRED_API_KEY` — [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html)
- `FINNHUB_API_KEY` — [Finnhub](https://finnhub.io/register)
- Optional: `ANTHROPIC_API_KEY` (Phase 3+)
- Hosted dashboard sync: `DASHBOARD_DB_SYNC_URL`, `DASHBOARD_DB_SYNC_SECRET` (bot); Vercel `BLOB_READ_WRITE_TOKEN`, `DB_UPLOAD_SECRET` (web). See README “Web dashboard”.

## Key Commands
```bash
# Run daily trading cycle
python -m src.main

# Run with specific date (backtest mode)
python -m src.main --date 2026-03-30

# Refresh Claude daily_analysis only (no trade execution); use after a mistaken --skip-claude overwrite
python -m src.main --date 2026-04-06 --analysis-only

# If NAV looks ~1 ETF sale short after an old bug (stale portfolio_meta.cash), replay cash then refresh snapshot:
PYTHONPATH=. python3 scripts/repair_portfolio_cash.py --apply && PYTHONPATH=. python3 -m src.main --skip-claude --date YYYY-MM-DD

# Start web dashboard (from repo root: ../storage/trading_bot.db)
cd web && npm install && npm run dev

# Run tests (PYTHONPATH=. if not installed editable)
pytest tests/
# or: PYTHONPATH=. python3 -m pytest tests/

# Install dependencies
pip install -e ".[dev]"
cd web && npm install
```

## Data Flow
```
Collect Data → Check Stops/TPs → Build Prompt → Call Claude → Execute Orders → Record & Report
```

## Enforced Rules
1. **Read spec before coding** — Check `specs/` for the relevant module spec before implementing
2. **Update docs after changes** — Keep `docs/architecture.md` and specs synchronized
3. **Artifacts to disk** — All analysis, decisions, and reports persist in the project tree

## Workflows
- `implement-and-verify.md` — 7-step dev cycle: spec → implement → test → review → fix → finalize
- `daily-trading-cycle.md` — Runtime pipeline documentation

## Critical Files
- `src/brain/prompt_builder.py` — How data is presented to Claude determines trade quality
- `src/brain/response_parser.py` — Must handle malformed JSON robustly
- `src/portfolio/portfolio.py` — Source of truth for NAV, positions, P&L
- `src/utils/dashboard_sync.py` — Optional POST of `trading_bot.db` to the dashboard; snapshot via SQLite `backup()` (WAL-safe)
- `web/lib/db.ts` — Opens local SQLite or downloads newest Vercel Blob; caching keyed by blob `uploadedAt` + `size`, local invalidation by file `mtime`
- `config/instruments.yaml` — Drives data collection, margin calc, and prompt content
- `config/settings.yaml` — All tunable parameters in one place

## Database
SQLite at `storage/trading_bot.db`. Tables: `portfolio_snapshots`, `positions`, `trades`, `daily_analysis` (incl. `daily_findings` text), `data_cache`.

## Learned User Preferences
- Expect the hosted dashboard to reflect the latest bot run after a fresh blob upload and a deployed `web/` revision that matches the repo.
- Treat “Vercel not updated” as often a Git/deploy gap (unpushed commits or no new deployment), not only a sync failure.
- When helping with setup and daily ops, give short copy-pasteable terminal commands (venv, `PYTHONPATH`, `src.main`, dashboard) rather than only narrative steps.
- If an API key or secret appears in chat, treat it as compromised: revoke/regenerate at the provider and store the replacement only in local `.env`, never in transcripts or git.
- If `daily_analysis` for a date looks stubbed or missing after runs, refresh narrative with `--analysis-only` for that date; `--skip-claude` no longer overwrites substantive rows (use `--force-daily-analysis` only when intentionally replacing the stored analysis).

## Learned Workspace Facts
- The Python bot does not run on Vercel; production is read-only Next.js over Blob. The bot runs locally (or another host), updates `storage/trading_bot.db`, then optionally POSTs to `/api/admin/sync-db` with `DASHBOARD_DB_SYNC_URL` and `DASHBOARD_DB_SYNC_SECRET` matching Vercel `DB_UPLOAD_SECRET`.
- Dashboard DB upload uses SQLite `backup()` in `dashboard_sync.py` so WAL mode cannot produce a stale copy from the main `.db` file alone.
- `web/lib/db.ts` uses a composite blob cache key (`uploadedAt` + `size`), `fetch` with `cache: "no-store"`, and local-file reopen when `mtime` changes so warm serverless or local dev does not serve an old DB.
- Vercel project: Root Directory `web`; env vars `BLOB_READ_WRITE_TOKEN`, `DB_UPLOAD_SECRET` (and any others) must be set for Production; redeploy after env changes.
- CLI deploy from `web/`: e.g. `npx vercel deploy --prod`; may create `web/.vercel` (often gitignored). Git-connected projects also deploy on push to the linked branch.
- Stored `daily_return` uses the latest `portfolio_snapshots.nav` on a date strictly before `as_of` (else initial capital). Missing snapshots between runs make one bar cover a longer calendar window; futures/commodities can still mark through weekends, so Fri→Mon can move a lot in one ratio.
- `daily_findings` fills only when the model returns it on runs after that field exists; older `daily_analysis` rows stay empty unless backfilled. Brief cross-run hints for the prompt live in SQLite `claude_session_memory`; archival model output may be in `daily_analysis.raw_response`.
- Interpreting NAV vs leg tables: NAV is cash plus sum of position `market_value` (futures MTM strip, long ETFs full marked value); realized P&L is already in cash, so summing only open unrealized can miss the full picture. Closing a long ETF credits full sale proceeds to cash—a large move in `NAV − cash` alone is not proof of loss when a big ETF leg was flattened.
- `portfolio_meta.cash` is updated in the same SQLite transaction as position/trade rows so a close cannot leave cash stale if the process stops between writes.
- When a same-session `prices` map is passed in, `Position` marking for NAV prefers that feed price over a possibly stale `positions.current_price` if the two could diverge.
- Stop and take-profit levels on an existing leg update when adding to that leg (merge path); there is no separate stop-only update order in the paper executor.
- Root `.gitignore` lists `*.tsbuildinfo` so TypeScript incremental build caches (e.g. under `web/`) are not committed.
