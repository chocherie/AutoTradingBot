# Risk Management Specification

**Status**: Draft | **Updated**: 2026-03-28

## Overview
Multi-layered risk management: Claude sets per-trade risk, system enforces hard limits.

## Risk Limits

### Per-Position Limits
- **Max position size**: 20% of NAV (notional value)
- **Minimum calendar hold** (`portfolio.min_hold_calendar_days` in `settings.yaml`, default 1): no exit (SELL/COVER, stop/TP, circuit, or `close_position`) until `(exit_session_date - entry_session_date).days >= N`. Set `0` to disable. Live runs use **today’s date in `schedule.timezone`** as the session `as_of`; `--date` uses that string as the session day for backtests.
- **Stop-loss required**: Every position must have a stop-loss price
- **Take-profit required**: Every position must have a take-profit price
- **Stop-loss distance**: Recommended 1-3x ATR from entry

### Portfolio-Level Limits
- **Max margin utilization**: 60% of NAV
- **Max portfolio heat**: 10% of NAV
  - Heat = sum of (|entry_price - stop_loss| * quantity * multiplier) for all positions
  - Represents maximum portfolio loss if all stops are hit simultaneously

### Circuit Breakers
- **Level 1 (15% drawdown)**: Block all new long positions. Claude is informed of restriction.
- **Level 2 (20% drawdown)**: Begin closing largest positions (by notional). Alert operator.
- **Drawdown measured from**: Peak NAV (high-water mark)
- **Reset**: Circuit breakers reset when NAV recovers above threshold

## Order Validation (pre-execution checks)
```python
def validate_order(order, portfolio, prices, *, as_of: str | None, ...) -> tuple[bool, str]:
    # 1. Ticker must exist in instrument universe
    # 2. For SELL/COVER: min-hold vs as_of (session calendar)
    # 3. Resulting position <= 20% NAV
    # 4. Resulting total margin <= 60% NAV
    # 5. Resulting portfolio heat <= 10% NAV
    # 6. Stop-loss and take-profit must be set
    # 7. Circuit breaker check (if drawdown > 15%, no new longs)
    # Returns (valid, rejection_reason)
```

## Stop-Loss / Take-Profit Enforcement
- Checked at the **start** of each daily cycle, before Claude analysis
- Uses **last close price** (not intraday — daily granularity only)
- If stop triggered: close is attempted at stop-loss price; **min-hold** may defer the exit to a later session (warning logged, position stays open)
- If TP triggered: same as stops regarding min-hold
- Successful triggered closures logged as trades with rationale "STOP_LOSS_TRIGGERED" or "TAKE_PROFIT_TRIGGERED"

## Concentration Limits
- Max 3 positions in the same asset class
- Max 40% NAV exposed to any single asset class
- These are soft limits (Claude is instructed, system warns but doesn't block)
