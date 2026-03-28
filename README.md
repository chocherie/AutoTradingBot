# AutoTradingBot

Paper-trading stack where **[Claude](https://www.anthropic.com/)** acts as the portfolio manager: it ingests **market data, macro (FRED), and news (Finnhub)**, returns a strict JSON trading plan, and a Python engine enforces **risk limits**, **simulates fills**, and persists everything to **SQLite**. A **Next.js** dashboard reads the same database for performance and positions.

**This is not a live broker.** Orders are simulated; there is no guarantee of profitability.

Public repo: [github.com/chocherie/AutoTradingBot](https://github.com/chocherie/AutoTradingBot)

---

## Features

| Area | What you get |
|------|----------------|
| **Brain** | System + user prompt (portfolio, market tables, econ, news). Optional **tools**: trade journal, NAV history, safe calculator. **Session memory**: model can save `session_learnings` → stored in DB and injected as *PRIOR SESSION LEARNINGS* on later runs. |
| **Risk** | Position caps, margin and heat limits, drawdown **circuit breakers** (warn / halt). Orders validated against the real open book (no selling what you don’t hold). |
| **Data** | Yahoo-backed market snapshot, FRED indicators, Finnhub general news with VADER sentiment and a **rolling headline buffer** (configurable). |
| **Ops** | JSON logs, SQLite artifacts, optional **LaunchAgent** example for macOS weekdays. |

More detail: [docs/architecture.md](docs/architecture.md), [docs/user-guide-trading-decisions.md](docs/user-guide-trading-decisions.md), and [specs/](specs/).

---

## Requirements

- **Python** ≥ 3.9  
- **Node.js** ≥ 18 (for `web/`)  
- API keys: **FRED**, **Finnhub**, **Anthropic** (full run). See [.env.example](.env.example).

---

## Quick start

```bash
git clone https://github.com/chocherie/AutoTradingBot.git
cd AutoTradingBot

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

python3 -m pip install --upgrade pip setuptools
pip install -e ".[dev]"

cp .env.example .env
# Edit .env: FRED_API_KEY, FINNHUB_API_KEY, ANTHROPIC_API_KEY
```

Run one daily cycle (UTC *as-of* defaults to today):

```bash
python3 -m src.main
```

Smoke test without Claude (data + DB snapshot only):

```bash
python3 -m src.main --skip-claude
```

Historical *as-of* date:

```bash
python3 -m src.main --date 2026-03-28
```

Tests:

```bash
PYTHONPATH=. python3 -m pytest tests/ -q
```

---

## Configuration

| File | Role |
|------|------|
| [config/settings.yaml](config/settings.yaml) | Risk limits, Claude model/temperature, news caps, tool toggles, DB path, logging. |
| [config/instruments.yaml](config/instruments.yaml) | Tradable universe (tickers, types, margin assumptions). |

Runtime database and logs live under **`storage/`** (created on first run, **gitignored**). **Do not commit `.env` or `storage/`.**

---

## Web dashboard

From repo root:

```bash
cd web && npm install && npm run dev
```

Point the app at your SQLite file if needed (default layout assumes repo-relative `storage/trading_bot.db`):

```bash
export DATABASE_PATH=/absolute/path/to/AutoTradingBot/storage/trading_bot.db
```

---

## Scheduling (macOS)

Example LaunchAgent plist (weekdays, 9:30 PM **local** — edit `Hour` / `Minute` to taste):

- [scripts/launchd/com.autotradingbot.daily.plist](scripts/launchd/com.autotradingbot.daily.plist)

Install flow (once):

```bash
cp scripts/launchd/com.autotradingbot.daily.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.autotradingbot.daily.plist
```

The Mac must be **awake** at the scheduled time. See comments in the plist and [AGENTS.md](AGENTS.md) for paths and env.

---

## Repository layout

```
src/main.py          # Daily orchestrator
src/brain/           # Prompt, Claude client, tools, JSON parsing
src/data/            # Market, FRED, news
src/portfolio/       # SQLite portfolio, risk validation
src/execution/       # Paper simulator
src/journal/         # Metrics from NAV series
config/              # YAML settings + instrument universe
web/                 # Next.js dashboard
docs/                # Architecture + user guide
specs/               # Design specs (read before large changes)
tests/               # pytest
scripts/launchd/     # macOS scheduling template
```

Agent-oriented onboarding: [AGENTS.md](AGENTS.md).

---

## Troubleshooting

- **`ModuleNotFoundError`**: use the venv’s Python and run `pip install -e ".[dev]"` from the repo root.  
- **`which python3`** should resolve to `.venv/bin/python3` when the venv is active.  
- **urllib3 / LibreSSL warning** on Apple CLT Python: often harmless; use [python.org](https://www.python.org/downloads/) or Homebrew Python if TLS issues appear.  
- **GitHub**: only source is pushed; clone on a new machine and recreate `.env` and `storage/`.

---

## License

No license file is bundled. Add a `LICENSE` if you want others to reuse the code under clear terms.
