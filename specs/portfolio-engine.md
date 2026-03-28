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

## Position Lifecycle
1. **Open**: Claude sends OrderIntent → Simulator fills → Position created in DB
2. **Daily Update**: Current prices fetched → unrealized P&L recalculated
3. **Stop/TP Check**: Before Claude runs, check all positions against stops and take-profits
4. **Close**: Either Claude requests close, or stop/TP triggers → realized P&L calculated, status → CLOSED

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
