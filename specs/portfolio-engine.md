# Portfolio Engine Specification

**Status**: Draft | **Updated**: 2026-03-28

## Overview
Manages all portfolio state: positions, cash, NAV, margin. Handles futures (with contract multipliers), options (with Greeks), and ETFs. Persists to SQLite.

## NAV Calculation
```
NAV = cash + sum(position.market_value for all open positions)

For futures:
  market_value = unrealized_pnl = (current_price - entry_price) * quantity * multiplier * direction_sign

For ETFs:
  market_value = current_price * quantity * fx_rate

For options:
  market_value = current_price * quantity * multiplier  (premium-based)
```

**Persistence / reconciliation**: Closing a position updates `positions` and inserts a `trades` row in the **same SQLite transaction** as `portfolio_meta.cash` (and the same for new opens / merge-adds). If cash were committed separately, a crash could leave a CLOSED ETF leg with **sale proceeds never credited** to cash while NAV (`get_nav`) drops the position line — producing nonsense like “NAV − cash collapsed but the ETF was profitable.”

**ETF close vs NAV − cash**: Long ETF adds **`exit × qty − commission`** to cash and removes **`last_mark × qty`** from the position sum. Total NAV moves by roughly **`(exit − last_mark) × qty`** (plus fees), not by −full notional. Do not attribute a drop in **`NAV − cash`** alone to “losing the ETF” without noting proceeds moved into **`cash`**.

**Daily return when snapshot dates have gaps**: `prior_nav_before` uses the latest snapshot **strictly before** `as_of`. Missing calendar days make `daily_return` span multiple sessions; interpret accordingly.

## Position Lifecycle
1. **Open / add**: Claude sends OrderIntent → Simulator fills → new **OPEN** row **or** incremental **BUY**/**SHORT** into an existing open leg (same ticker, direction, and instrument identity; VWAP entry, one row).
2. **Daily Update**: Current prices fetched → unrealized P&L recalculated
3. **Stop/TP Check**: Before Claude runs, check all positions against stops and take-profits
4. **Close**: Either Claude requests close, or stop/TP triggers → realized P&L calculated, status → CLOSED

## Cash settlement on close
- **Futures**: Opening debits opening commission only; **`_cash`** on close changes by full **realized** MTM (`(exit-entry) × qty × multiplier`, net of exit commission).
- **ETFs / spot**: Opening debits **full notional** (long) or credits **short-sale proceeds** (short). Closing **long** credits **`exit × qty × fx − exit commission`** (sale proceeds). Closing **short** debits **`exit × qty × fx + exit commission`** (cover + fee).
- **Options**: Same cash pattern as notional: long pays premium on open / receives on close; short receives premium on open / pays on close. **`realized_pnl`** stored on the row remains economic P&L net of **exit** commission (opening commission was already applied on open).

## Margin Calculation
```
For futures:
  margin = quantity * current_price * multiplier * margin_pct

For options (long):
  margin = 0 (premium already paid from cash)

For options (short):
  margin = quantity * underlying_price * multiplier * 0.20  (simplified)

For ETFs:
  margin = 0 (fully paid)

Total margin utilization = sum(all margins) / NAV * 100
```

## Options Greeks (Black-Scholes approximation)
Calculated for display and risk assessment:
- **Delta**: rate of change of option price vs underlying
- **Gamma**: rate of change of delta
- **Theta**: time decay per day
- **Vega**: sensitivity to implied volatility
- Uses `scipy.stats.norm` for cumulative distribution

## Portfolio State Methods
```python
class Portfolio:
    def load_state(self) -> None          # Load from SQLite
    def save_state(self) -> None          # Persist to SQLite
    def get_nav(self) -> float            # Current NAV
    def get_cash(self) -> float
    def get_positions(self) -> list[Position]
    def get_open_positions(self) -> list[Position]
    def add_position(self, position: Position) -> None
    def close_position(self, position_id: int, exit_price: float, exit_date: str) -> float  # returns realized P&L
    def update_prices(self, prices: dict[str, float]) -> None
    def check_stop_loss_take_profit(self, prices: dict[str, float]) -> list[Position]  # returns triggered positions
    def get_margin_used(self) -> float
    def get_margin_utilization(self) -> float  # as percentage of NAV
    def to_summary_dict(self) -> dict     # For prompt builder
```

## Database Tables

### positions
```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_date TEXT NOT NULL,
    current_price REAL,
    unrealized_pnl REAL DEFAULT 0,
    stop_loss REAL,
    take_profit REAL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    exit_price REAL,
    exit_date TEXT,
    realized_pnl REAL,
    margin_required REAL DEFAULT 0,
    notional_value REAL DEFAULT 0,
    option_type TEXT,
    strike REAL,
    expiry TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### portfolio_snapshots
```sql
CREATE TABLE portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT UNIQUE NOT NULL,
    nav REAL NOT NULL,
    cash REAL NOT NULL,
    total_margin_used REAL NOT NULL,
    daily_return REAL,
    cumulative_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```
