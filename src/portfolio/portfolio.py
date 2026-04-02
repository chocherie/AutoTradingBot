"""Portfolio state, NAV, SQLite persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.portfolio.hold_rules import min_hold_exit_blocked
from src.portfolio.instrument_registry import InstrumentMeta, build_registry, resolve_fx_to_usd
from src.portfolio.margin import margin_required_usd
from src.portfolio.position import Position
from src.utils.config import load_settings
from src.utils.paths import project_root


def _db_path() -> Path:
    settings = load_settings()
    rel = settings.get("database", {}).get("path", "storage/trading_bot.db")
    return project_root() / Path(rel)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.Connection(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS portfolio_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cash REAL NOT NULL,
            peak_nav REAL NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS positions (
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
            entry_notional_usd REAL,
            exit_notional_usd REAL,
            option_type TEXT,
            strike REAL,
            expiry TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER,
            ticker TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            commission REAL DEFAULT 0,
            slippage_bps REAL DEFAULT 0,
            trade_date TEXT NOT NULL,
            rationale TEXT,
            exit_reason TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (position_id) REFERENCES positions(id)
        );
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
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
        CREATE TABLE IF NOT EXISTS daily_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            market_regime TEXT,
            macro_summary TEXT,
            risk_notes TEXT,
            raw_response TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            estimated_cost_usd REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS claude_session_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT NOT NULL,
            lesson TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    _migrate_schema(conn)
    conn.commit()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(trades)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "confidence" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN confidence TEXT")
    if "signal_source" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN signal_source TEXT")

    pcols = {str(r[1]) for r in conn.execute("PRAGMA table_info(positions)").fetchall()}
    if "entry_notional_usd" not in pcols:
        conn.execute("ALTER TABLE positions ADD COLUMN entry_notional_usd REAL")
    if "exit_notional_usd" not in pcols:
        conn.execute("ALTER TABLE positions ADD COLUMN exit_notional_usd REAL")


class Portfolio:
    """In-memory view backed by SQLite."""

    def __init__(self) -> None:
        self._cash: float = 0.0
        self._peak_nav: float = 0.0
        self._positions: List[Position] = []
        self._loaded: bool = False

    def _conn(self) -> sqlite3.Connection:
        c = _connect()
        ensure_schema(c)
        return c

    def load_state(self) -> None:
        settings = load_settings()
        init_cash = float(settings.get("portfolio", {}).get("initial_capital", 1_000_000.0))
        with self._conn() as conn:
            row = conn.execute("SELECT cash, peak_nav FROM portfolio_meta WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO portfolio_meta (id, cash, peak_nav) VALUES (1, ?, ?)",
                    (init_cash, init_cash),
                )
                conn.commit()
                self._cash = init_cash
                self._peak_nav = init_cash
            else:
                self._cash = float(row["cash"])
                self._peak_nav = float(row["peak_nav"])
            rows = conn.execute(
                "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY id"
            ).fetchall()
            self._positions = [Position.from_row(r) for r in rows]
        self._loaded = True
        self._refresh_peak()

    def _persist_meta(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE portfolio_meta SET cash = ?, peak_nav = ?,
                   updated_at = datetime('now') WHERE id = 1""",
                (self._cash, self._peak_nav),
            )
            conn.commit()

    def save_open_positions_snapshot(self) -> None:
        """Rewrite OPEN rows from memory (rare; normally use add/close paths)."""
        with self._conn() as conn:
            for p in self._positions:
                if p.id is None:
                    continue
                conn.execute(
                    """UPDATE positions SET
                    current_price=?, unrealized_pnl=?, margin_required=?,
                    notional_value=? WHERE id=?""",
                    (
                        p.current_price,
                        p.unrealized_pnl,
                        p.margin_required,
                        p.notional_value,
                        p.id,
                    ),
                )
            conn.commit()

    def get_cash(self) -> float:
        return self._cash

    def get_positions(self) -> List[Position]:
        return list(self._positions)

    def get_open_positions(self) -> List[Position]:
        return [p for p in self._positions if p.status == "OPEN"]

    def get_nav(self, prices: Dict[str, float]) -> float:
        reg = build_registry()
        total = self._cash
        for p in self.get_open_positions():
            meta = reg.get(p.ticker)
            if not meta:
                continue
            total += p.market_value(meta, prices)
        return total

    def _refresh_peak(self, prices: Optional[Dict[str, float]] = None) -> None:
        if prices is None:
            prices = {}
        nav = self.get_nav(prices) if prices else self._cash
        if nav > self._peak_nav:
            self._peak_nav = nav
            self._persist_meta()

    def drawdown_pct(self, prices: Dict[str, float]) -> float:
        nav = self.get_nav(prices)
        if self._peak_nav <= 0:
            return 0.0
        return max(0.0, (self._peak_nav - nav) / self._peak_nav * 100.0)

    def circuit_warn_active(self, prices: Dict[str, float], warn_dd: float) -> bool:
        return self.drawdown_pct(prices) >= warn_dd

    def total_margin_used(self, prices: Dict[str, float]) -> float:
        reg = build_registry()
        s = 0.0
        for p in self.get_open_positions():
            meta = reg.get(p.ticker)
            if not meta:
                continue
            u = prices.get(p.ticker) or p.entry_price
            s += margin_required_usd(meta, p, u)
        return s

    def total_margin_used_ex_new(
        self,
        prices: Dict[str, float],
        exclude_ticker: Optional[str] = None,
    ) -> float:
        reg = build_registry()
        s = 0.0
        for p in self.get_open_positions():
            if exclude_ticker and p.ticker == exclude_ticker:
                continue
            meta = reg.get(p.ticker)
            if not meta:
                continue
            u = prices.get(p.ticker) or p.entry_price
            s += margin_required_usd(meta, p, u)
        return s

    def total_heat_usd_ex_new(
        self,
        prices: Dict[str, float],
        exclude_ticker: Optional[str] = None,
    ) -> float:
        reg = build_registry()
        s = 0.0
        for p in self.get_open_positions():
            if exclude_ticker and p.ticker == exclude_ticker:
                continue
            meta = reg.get(p.ticker)
            if not meta:
                continue
            s += p.heat_risk_usd(meta, prices)
        return s

    def find_open_position(self, ticker: str, *, long_side: bool = True) -> Optional[Position]:
        want = "LONG" if long_side else "SHORT"
        for p in self.get_open_positions():
            if p.ticker == ticker and p.direction == want:
                return p
        return None

    def get_margin_utilization(self, prices: Dict[str, float]) -> float:
        nav = self.get_nav(prices)
        if nav <= 0:
            return 0.0
        return (self.total_margin_used(prices) / nav) * 100.0

    def update_prices(self, prices: Dict[str, float]) -> None:
        reg = build_registry()
        with self._conn() as conn:
            for p in self.get_open_positions():
                px = prices.get(p.ticker)
                if px is None:
                    continue
                meta = reg.get(p.ticker)
                if meta:
                    p.current_price = float(px)
                    p.unrealized_pnl = p.unrealized_from_prices(meta, prices)
                    under = float(px)
                    p.margin_required = margin_required_usd(meta, p, under)
                    fx = resolve_fx_to_usd(meta, prices)
                    if p.instrument_type == "future":
                        p.notional_value = abs(p.quantity * px * meta.multiplier)
                    elif p.instrument_type == "option":
                        om = meta.option_contract_multiplier or 100.0
                        p.notional_value = abs(p.quantity * px * om)
                    else:
                        p.notional_value = abs(p.quantity * px * fx)
                    if p.id:
                        conn.execute(
                            """UPDATE positions SET current_price=?, unrealized_pnl=?,
                            margin_required=?, notional_value=? WHERE id=?""",
                            (
                                p.current_price,
                                p.unrealized_pnl,
                                p.margin_required,
                                p.notional_value,
                                p.id,
                            ),
                        )
            conn.commit()
        self._refresh_peak(prices)

    def check_stop_loss_take_profit(
        self,
        prices: Dict[str, float],
    ) -> List[Tuple[Position, str, float]]:
        """Positions triggered at last close; close at stop/tp price (no extra slippage)."""
        triggered: List[Tuple[Position, str, float]] = []
        for p in self.get_open_positions():
            px = prices.get(p.ticker)
            if px is None or p.stop_loss is None or p.take_profit is None:
                continue
            px = float(px)
            if p.direction == "LONG":
                if px <= p.stop_loss:
                    triggered.append((p, "STOP_LOSS_TRIGGERED", float(p.stop_loss)))
                elif px >= p.take_profit:
                    triggered.append((p, "TAKE_PROFIT_TRIGGERED", float(p.take_profit)))
            else:
                if px >= p.stop_loss:
                    triggered.append((p, "STOP_LOSS_TRIGGERED", float(p.stop_loss)))
                elif px <= p.take_profit:
                    triggered.append((p, "TAKE_PROFIT_TRIGGERED", float(p.take_profit)))
        return triggered

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_date: str,
        *,
        rationale: str = "",
        exit_reason: str = "MANUAL",
        commission: float = 0.0,
        slippage_bps: float = 0.0,
    ) -> float:
        """Realize P&L, update cash, mark CLOSED. Returns realized P&L net of exit commission."""
        reg = build_registry()
        target: Optional[Position] = None
        for p in self._positions:
            if p.id == position_id and p.status == "OPEN":
                target = p
                break
        if target is None:
            raise ValueError(f"No open position id={position_id}")

        meta = reg.get(target.ticker)
        if meta is None:
            raise ValueError(f"Unknown ticker {target.ticker}")

        blocked = min_hold_exit_blocked(target.entry_date, exit_date, load_settings())
        if blocked:
            raise ValueError(blocked)

        fx = resolve_fx_to_usd(meta, {target.ticker: exit_price})
        realized = 0.0
        if target.instrument_type == "future":
            if target.direction == "LONG":
                realized = (exit_price - target.entry_price) * target.quantity * meta.multiplier
            else:
                realized = (target.entry_price - exit_price) * target.quantity * meta.multiplier
        elif target.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            if target.direction == "LONG":
                realized = (exit_price - target.entry_price) * target.quantity * om
            else:
                realized = (target.entry_price - exit_price) * target.quantity * om
        else:
            if target.direction == "LONG":
                realized = (exit_price - target.entry_price) * target.quantity * fx
            else:
                realized = (target.entry_price - exit_price) * target.quantity * fx

        realized -= commission

        if target.instrument_type == "future":
            exit_notional_usd = abs(target.quantity * exit_price * meta.multiplier)
        elif target.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            exit_notional_usd = abs(target.quantity * exit_price * om)
        else:
            exit_notional_usd = abs(target.quantity * exit_price * fx)

        # Cash: futures/options-on-margin only move cash by P&L (opening paid commissions only).
        # Spot longs pay full notional on add_position; closing must credit sale proceeds, not P&L only.
        # Spot shorts receive proceeds on open; closing must debit cover cost + exit commission.
        if target.instrument_type == "future":
            self._cash += realized
        elif target.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            if target.direction == "LONG":
                self._cash += exit_price * target.quantity * om - commission
            else:
                self._cash -= exit_price * target.quantity * om + commission
        else:
            if target.direction == "LONG":
                self._cash += exit_price * target.quantity * fx - commission
            else:
                self._cash -= exit_price * target.quantity * fx + commission

        with self._conn() as conn:
            conn.execute(
                """UPDATE positions SET status='CLOSED', exit_price=?, exit_date=?,
                realized_pnl=?, exit_notional_usd=? WHERE id=?""",
                (exit_price, exit_date, realized, exit_notional_usd, position_id),
            )
            conn.execute(
                """INSERT INTO trades (position_id, ticker, instrument_type, action,
                quantity, price, commission, slippage_bps, trade_date, rationale, exit_reason,
                confidence, signal_source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    position_id,
                    target.ticker,
                    target.instrument_type,
                    "CLOSE",
                    target.quantity,
                    exit_price,
                    commission,
                    slippage_bps,
                    exit_date,
                    rationale,
                    exit_reason,
                    None,
                    None,
                ),
            )
            conn.commit()

        target.status = "CLOSED"
        target.exit_price = exit_price
        target.exit_date = exit_date
        target.realized_pnl = realized
        self._positions = [x for x in self._positions if not (x.id == position_id and x.status == "CLOSED")]
        self._persist_meta()
        return realized

    def add_position(
        self,
        pos: Position,
        *,
        trade_date: str,
        commission: float = 0.0,
        slippage_bps: float = 0.0,
        action: str = "OPEN",
        rationale: str = "",
        underlying_for_margin: Optional[float] = None,
        confidence: Optional[str] = None,
        signal_source: Optional[str] = None,
    ) -> int:
        """Insert OPEN position and deduct opening cash impacts. Returns new id."""
        reg = build_registry()
        meta = reg.get(pos.ticker)
        if meta is None:
            raise ValueError(f"Unknown ticker {pos.ticker}")

        fx = resolve_fx_to_usd(meta, {pos.ticker: pos.entry_price})
        opening_cash_delta = -commission
        if pos.instrument_type == "future":
            pass
        elif pos.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            if pos.direction == "LONG":
                opening_cash_delta -= pos.entry_price * pos.quantity * om
            else:
                opening_cash_delta += pos.entry_price * pos.quantity * om
        else:
            if pos.direction == "LONG":
                opening_cash_delta -= pos.entry_price * pos.quantity * fx
            else:
                opening_cash_delta += pos.entry_price * pos.quantity * fx

        self._cash += opening_cash_delta
        u_px = underlying_for_margin if underlying_for_margin is not None else pos.entry_price
        pos.margin_required = margin_required_usd(meta, pos, u_px)
        if pos.instrument_type == "future":
            pos.notional_value = abs(pos.quantity * pos.entry_price * meta.multiplier)
        elif pos.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            pos.notional_value = abs(pos.quantity * pos.entry_price * om)
        else:
            pos.notional_value = abs(pos.quantity * pos.entry_price * fx)

        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO positions (
                ticker, asset_class, instrument_type, direction, quantity,
                entry_price, entry_date, current_price, unrealized_pnl,
                stop_loss, take_profit, status, margin_required, notional_value,
                entry_notional_usd, option_type, strike, expiry) VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pos.ticker,
                    pos.asset_class,
                    pos.instrument_type,
                    pos.direction,
                    pos.quantity,
                    pos.entry_price,
                    trade_date,
                    pos.current_price,
                    pos.unrealized_pnl,
                    pos.stop_loss,
                    pos.take_profit,
                    "OPEN",
                    pos.margin_required,
                    pos.notional_value,
                    pos.notional_value,
                    pos.option_type,
                    pos.strike,
                    pos.expiry,
                ),
            )
            pid = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO trades (position_id, ticker, instrument_type, action,
                quantity, price, commission, slippage_bps, trade_date, rationale, exit_reason,
                confidence, signal_source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid,
                    pos.ticker,
                    pos.instrument_type,
                    action,
                    pos.quantity,
                    pos.entry_price,
                    commission,
                    slippage_bps,
                    trade_date,
                    rationale,
                    "",
                    confidence,
                    signal_source,
                ),
            )
            conn.commit()

        pos.id = pid
        self._positions.append(pos)
        self._persist_meta()
        return pid

    def merge_add_to_open(
        self,
        position_id: int,
        add_quantity: float,
        add_entry_price: float,
        trade_date: str,
        commission: float,
        slippage_bps: float,
        action: str,
        rationale: str,
        prices: Dict[str, float],
        *,
        new_stop_loss: float,
        new_take_profit: float,
        confidence: Optional[str] = None,
        signal_source: Optional[str] = None,
    ) -> int:
        """Increase size of an open leg (VWAP entry). Opening cash impact is incremental only."""
        target = next(
            (p for p in self._positions if p.id == position_id and p.status == "OPEN"),
            None,
        )
        if target is None:
            raise ValueError(f"No open position id={position_id}")

        reg = build_registry()
        meta = reg.get(target.ticker)
        if meta is None:
            raise ValueError(f"Unknown ticker {target.ticker}")

        old_q = target.quantity
        old_px = target.entry_price
        new_q = old_q + add_quantity
        new_entry = (old_q * old_px + add_quantity * add_entry_price) / new_q

        fx = resolve_fx_to_usd(meta, prices)
        opening_cash_delta = -commission
        if target.instrument_type == "future":
            pass
        elif target.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            if target.direction == "LONG":
                opening_cash_delta -= add_entry_price * add_quantity * om
            else:
                opening_cash_delta += add_entry_price * add_quantity * om
        else:
            if target.direction == "LONG":
                opening_cash_delta -= add_entry_price * add_quantity * fx
            else:
                opening_cash_delta += add_entry_price * add_quantity * fx

        self._cash += opening_cash_delta

        target.quantity = new_q
        target.entry_price = new_entry
        target.stop_loss = new_stop_loss
        target.take_profit = new_take_profit
        u_px = float(prices.get(target.ticker, add_entry_price))
        target.margin_required = margin_required_usd(meta, target, u_px)
        if target.instrument_type == "future":
            target.notional_value = abs(new_q * new_entry * meta.multiplier)
        elif target.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            target.notional_value = abs(new_q * new_entry * om)
        else:
            target.notional_value = abs(new_q * new_entry * fx)

        mark = prices.get(target.ticker)
        if mark is not None:
            target.current_price = float(mark)
            target.unrealized_pnl = target.unrealized_from_prices(meta, prices)

        with self._conn() as conn:
            conn.execute(
                """UPDATE positions SET quantity=?, entry_price=?, current_price=?,
                unrealized_pnl=?, stop_loss=?, take_profit=?,
                margin_required=?, notional_value=?, entry_notional_usd=?
                WHERE id=? AND status='OPEN'""",
                (
                    target.quantity,
                    target.entry_price,
                    target.current_price,
                    target.unrealized_pnl,
                    target.stop_loss,
                    target.take_profit,
                    target.margin_required,
                    target.notional_value,
                    target.notional_value,
                    position_id,
                ),
            )
            conn.execute(
                """INSERT INTO trades (position_id, ticker, instrument_type, action,
                quantity, price, commission, slippage_bps, trade_date, rationale, exit_reason,
                confidence, signal_source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    position_id,
                    target.ticker,
                    target.instrument_type,
                    action,
                    add_quantity,
                    add_entry_price,
                    commission,
                    slippage_bps,
                    trade_date,
                    rationale,
                    "",
                    confidence,
                    signal_source,
                ),
            )
            conn.commit()

        self._persist_meta()
        return position_id

    def to_summary_dict(self, prices: Dict[str, float]) -> dict:
        nav = self.get_nav(prices)
        return {
            "cash": self._cash,
            "nav": nav,
            "peak_nav": self._peak_nav,
            "drawdown_pct": self.drawdown_pct(prices),
            "margin_utilization_pct": self.get_margin_utilization(prices),
            "open_positions": len(self.get_open_positions()),
        }

    def append_session_learnings(self, session_date: str, lessons: List[str]) -> None:
        """Persist short lessons from the model for future prompts (max per run enforced)."""
        rows: List[str] = []
        for s in lessons or []:
            t = (s or "").strip()
            if not t:
                continue
            t = t[:500]
            rows.append(t)
            if len(rows) >= 12:
                break
        if not rows:
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO claude_session_memory (session_date, lesson) VALUES (?, ?)",
                [(session_date, r) for r in rows],
            )
            conn.commit()

    def fetch_recent_session_learnings(self, limit: int) -> List[str]:
        """Most recent lessons first."""
        if limit <= 0:
            return []
        with self._conn() as conn:
            cur = conn.execute(
                """SELECT lesson FROM claude_session_memory
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            return [str(r["lesson"]) for r in cur.fetchall()]

    def recent_trades_for_tools(self, limit: int) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit), 50))
        with self._conn() as conn:
            cur = conn.execute(
                """SELECT trade_date, ticker, action, quantity, price, rationale, exit_reason
                   FROM trades ORDER BY id DESC LIMIT ?""",
                (lim,),
            )
            return [{k: r[k] for k in r.keys()} for r in cur.fetchall()]

    def recent_nav_snapshots_for_tools(self, limit: int) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit), 120))
        with self._conn() as conn:
            cur = conn.execute(
                """SELECT date, nav, daily_return, cumulative_return, sharpe_ratio, max_drawdown
                   FROM portfolio_snapshots ORDER BY date DESC LIMIT ?""",
                (lim,),
            )
            return [{k: r[k] for k in r.keys()} for r in cur.fetchall()]

    def write_snapshot(
        self,
        as_of: str,
        prices: Dict[str, float],
        *,
        daily_return: Optional[float] = None,
        cumulative_return: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
        max_drawdown: Optional[float] = None,
    ) -> None:
        nav = self.get_nav(prices)
        cash = self._cash
        margin = self.total_margin_used(prices)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO portfolio_snapshots (date, nav, cash, total_margin_used,
                   daily_return, cumulative_return, sharpe_ratio, max_drawdown)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(date) DO UPDATE SET
                   nav=excluded.nav, cash=excluded.cash, total_margin_used=excluded.total_margin_used,
                   daily_return=excluded.daily_return, cumulative_return=excluded.cumulative_return,
                   sharpe_ratio=excluded.sharpe_ratio, max_drawdown=excluded.max_drawdown
                """,
                (
                    as_of,
                    nav,
                    cash,
                    margin,
                    daily_return,
                    cumulative_return,
                    sharpe_ratio,
                    max_drawdown,
                ),
            )
            conn.commit()

    def write_daily_analysis(
        self,
        as_of: str,
        *,
        market_regime: str,
        macro_summary: str,
        risk_notes: str,
        raw_response: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO daily_analysis (date, market_regime, macro_summary, risk_notes,
                   raw_response, input_tokens, output_tokens, estimated_cost_usd)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(date) DO UPDATE SET
                   market_regime=excluded.market_regime,
                   macro_summary=excluded.macro_summary,
                   risk_notes=excluded.risk_notes,
                   raw_response=excluded.raw_response,
                   input_tokens=excluded.input_tokens,
                   output_tokens=excluded.output_tokens,
                   estimated_cost_usd=excluded.estimated_cost_usd
                """,
                (
                    as_of,
                    market_regime,
                    macro_summary,
                    risk_notes,
                    raw_response,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                ),
            )
            conn.commit()
