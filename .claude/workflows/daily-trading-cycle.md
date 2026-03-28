# Workflow: Daily Trading Cycle

Runtime pipeline executed once per trading day at 17:00 ET.

## Steps

### 1. Data Collection (parallel)
- `MarketDataCollector.fetch_all()` — prices + technicals for all instruments
- `EconomicDataCollector.fetch_indicators()` — FRED macro data
- `NewsSentimentCollector.fetch_news()` — headlines + VADER scores

### 2. Portfolio Load + Stop/TP Check
- `Portfolio.load_state()` — load from SQLite
- `Portfolio.check_stop_loss_take_profit(current_prices)` — auto-close triggered positions

### 3. Prompt Assembly
- `PromptBuilder.build(market_data, economic_data, news, portfolio)` — 4-section prompt

### 4. Claude Analysis
- `ClaudeClient.analyze(system_prompt, user_prompt)` — call Opus
- `ResponseParser.parse(raw_json)` — validate into `ClaudeDecision`
- Store prompt + response in `daily_analysis` table

### 5. Order Execution
- For each `OrderIntent`: validate against risk limits → simulate fill
- For each `positions_to_close`: close at current price

### 6. Record & Report
- Log trades to `trades` table with rationale
- Update all position prices and unrealized P&L
- Snapshot NAV, returns, Sharpe to `portfolio_snapshots`
- Write daily summary to log file

## Error Recovery
- If data collection fails partially: continue with available data, note gaps in prompt
- If Claude API fails: enforce stops only, no new trades
- If order validation fails: reject order, log reason, continue with remaining orders
