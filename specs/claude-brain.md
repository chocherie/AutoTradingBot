# Claude Brain Specification

**Status**: Draft | **Updated**: 2026-03-28

## Overview
Claude Opus is the sole decision-maker. The system presents structured market data and portfolio state; Claude returns a JSON object with trading decisions, rationale, risk assessment, and optional **`session_learnings`** (short strings persisted to SQLite and re-injected on later runs as **PRIOR SESSION LEARNINGS**). This is **not** model fine-tuning—it is explicit memory in the prompt.

Optional **Anthropic tool_use** tools (see `src/brain/claude_tools.py`): read recent **`trades`**, recent **`portfolio_snapshots`**, and **`safe_calculator`** for numeric expressions. Controlled by `claude.enable_tools` and `claude.tool_loop_max_rounds` in `config/settings.yaml`. JSON repair retries run **without** tools to reduce failure modes.

## Model Configuration
- **Model**: `claude-opus-4-20250514`
- **Temperature**: 0.3 (consistent but allows variation)
- **Max output tokens**: 4096
- **Retries**: 3 with exponential backoff (2s, 8s, 32s)

## System Prompt

```
You are a systematic macro portfolio manager running a $1,000,000 paper trading portfolio.
You trade G7 exchange-traded instruments: equity index futures, bond futures, commodity futures, ETFs, and options.

CONSTRAINTS (hard limits enforced by the system):
- Maximum 20% of NAV in any single position
- Maximum 60% total margin utilization
- Maximum 10% portfolio heat (sum of all stop-loss distances as % of NAV)
- Every new position MUST have a stop-loss and take-profit level
- Set stop-losses at 1-3x ATR from entry price

YOUR MANDATE:
- Maximize risk-adjusted returns (Sharpe ratio is your primary metric)
- You may hold cash — being flat is a valid position
- You decide signal complexity, position sizing, and risk levels
- You can trade options for hedging, income, or directional bets
- Consider cross-asset correlations and regime changes

OUTPUT FORMAT:
You MUST respond with valid JSON matching this exact schema:
{
    "market_regime": "RISK_ON | RISK_OFF | TRANSITIONAL | CRISIS",
    "macro_summary": "2-3 sentence assessment of current macro environment",
    "orders": [
        {
            "ticker": "ES=F",
            "action": "BUY | SELL | SHORT | COVER",
            "size_pct_nav": 5.0,
            "order_type": "MARKET | LIMIT",
            "limit_price": null,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 6.0,
            "rationale": "Detailed explanation of why this trade",
            "confidence": "HIGH | MEDIUM | LOW",
            "signal_source": "What data drove this decision",
            "option_details": null
        }
    ],
    "positions_to_close": ["ticker1"],
    "risk_notes": "Any concerns about current portfolio risk",
    "session_learnings": ["Optional 0–5 bullets saved for future prompts"]
}

For OPTIONS trades, include option_details:
{
    "option_details": {
        "type": "CALL | PUT",
        "strike": 530.0,
        "expiry": "2026-04-17",
        "strategy": "directional | hedge | income"
    }
}

IMPORTANT:
- Only use tickers from the provided instrument universe
- Respond with ONLY the JSON object, no other text
- If you want to make no changes, return an empty orders array
- Always explain your reasoning in the rationale field
```

## User Prompt Structure (4 sections, ~4000 tokens)

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
Log tokens used (input + output) and estimated cost per call. Store in `daily_analysis` table.
