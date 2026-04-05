# Claude Brain Specification

**Status**: Draft | **Updated**: 2026-03-28

## Overview
Claude Opus is the sole decision-maker. The system presents structured market data and portfolio state; Claude returns a JSON object with trading decisions, rationale, risk assessment, and optional **`session_learnings`** (short strings persisted to SQLite and re-injected on later runs as **PRIOR SESSION LEARNINGS**). This is **not** model fine-tuning—it is explicit memory in the prompt.

Optional **Anthropic tool_use** tools (see `src/brain/claude_tools.py`): read recent **`trades`**, recent **`portfolio_snapshots`**, and **`safe_calculator`** for numeric expressions. Controlled by `claude.enable_tools` and `claude.tool_loop_max_rounds` in `config/settings.yaml`. JSON repair retries run **without** tools to reduce failure modes.

## Trading feature flags (`config/settings.yaml`)
- **`trading.options_enabled`** (default `true` if omitted): when `false`, the system prompt omits option instructions, **`fetch_market_snapshot`** skips options chains, and **`validate_order`** rejects any intent with `option_details` set.

## Model Configuration
- **Model**: `claude-opus-4-20250514`
- **Temperature**: 0.3 (consistent but allows variation)
- **Max output tokens**: 4096
- **Retries**: 3 with exponential backoff (2s, 8s, 32s)

## System Prompt

Authoritative copy lives in `SYSTEM_PROMPT` / `SYSTEM_PROMPT_OPTIONS_DISABLED` in [`src/brain/claude_client.py`](../src/brain/claude_client.py). Summary of **JSON fields**:

- **`market_regime`**, **`macro_summary`** (2–3 sentences only), **`daily_findings`** (multi-paragraph session narrative persisted to `daily_analysis.daily_findings`)
- **`orders`** with **`rationale`** structured as: (1) view/sentiment, (2) briefing evidence, (3) decision/conviction vs sizing and stops
- **`positions_to_close`**, **`risk_notes`** (sector/cash book aligned to MARKET DATA buckets, quantified where possible), **`session_learnings`**
- Options: same schema with `option_details` when `trading.options_enabled` is true

## User Prompt Structure (preamble + data sections, ~4000 tokens)

### Section 0: Daily pipeline (always first)
Plain-language steps **1–6** matching [docs/user-guide-trading-decisions.md](../docs/user-guide-trading-decisions.md) (“What happens each day”): prices refreshed, stops/TPs and optional circuit halt already applied, this briefing built, expected JSON shape, and **`positions_to_close` before `orders`** after the model replies. Implemented as `## DAILY PIPELINE …` in `build_user_prompt()` (`src/brain/prompt_builder.py`).

### Section 1: Portfolio State
```
## PORTFOLIO STATE (as of YYYY-MM-DD)
NAV: $X | Cash: $X | Margin Used: X% | Daily Return: X% | YTD Return: X% | Sharpe: X.XX

OPEN POSITIONS:
| Ticker | Dir | Qty | Entry | Current | Unrealized P&L | Stop | TP |
...
```

### Section 2: Market Data
```
## MARKET DATA
EQUITY INDICES:
| Ticker | Last | 5D Chg% | SMA20 | SMA50 | RSI | ATR |
...

BONDS:
...

COMMODITIES:
...

FX RATES:
...
```

### Section 3: Economic Indicators
```
## ECONOMIC INDICATORS
| Indicator | Current | Previous | Trend |
...
```

### Section 4a: Prior session learnings (when present)
```
## PRIOR SESSION LEARNINGS
Notes saved from earlier runs (newest first).
1. ...
```

### Section 5: News & Sentiment
```
## NEWS & SENTIMENT
Overall Sentiment: X.XX | Equities: X.XX | Bonds: X.XX | Commodities: X.XX

Top Headlines:
1. [sentiment: X.XX] headline text (source)
...
```

## Response Parsing
1. Extract JSON from response (handle potential markdown code blocks)
2. Validate against Pydantic schema (`ClaudeDecision`)
3. Verify all tickers exist in instrument universe
4. If parsing fails: retry once with repair instruction appended
5. If still fails: log error, skip new trades, enforce existing stops only

## Cost Tracking
Log tokens used (input + output) and estimated cost per call. Store in `daily_analysis` table together with regime, macro summary, **`daily_findings`**, risk notes, and raw response.
