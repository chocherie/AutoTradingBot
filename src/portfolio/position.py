"""Position model aligned with SQLite `positions` table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from src.portfolio.instrument_registry import InstrumentMeta, resolve_fx_to_usd


@dataclass
class Position:
    id: Optional[int]
    ticker: str
    asset_class: str
    instrument_type: str
    direction: str
    quantity: float
    entry_price: float
    entry_date: str
    current_price: Optional[float]
    unrealized_pnl: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    status: str
    exit_price: Optional[float]
    exit_date: Optional[str]
    realized_pnl: Optional[float]
    margin_required: float
    notional_value: float
    option_type: Optional[str]
    strike: Optional[float]
    expiry: Optional[str]

    def direction_sign(self) -> int:
        return 1 if self.direction == "LONG" else -1

    def _mark_price(self, prices: Dict[str, float]) -> float:
        """Prefer live feed for this ticker; avoids stale current_price if update_prices skipped a leg."""
        feed = prices.get(self.ticker)
        if feed is not None:
            return float(feed)
        if self.current_price is not None:
            return float(self.current_price)
        return float(self.entry_price)

    def market_value(
        self,
        meta: InstrumentMeta,
        prices: Dict[str, float],
    ) -> float:
        """Mark-to-market USD contribution to NAV (per portfolio-engine spec)."""
        px = self._mark_price(prices)
        fx = resolve_fx_to_usd(meta, prices)
        if self.instrument_type == "future":
            if self.direction == "LONG":
                return (px - self.entry_price) * self.quantity * meta.multiplier
            return (self.entry_price - px) * self.quantity * meta.multiplier
        if self.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            return px * self.quantity * om
        # ETF (long-only supported)
        if self.direction == "LONG":
            return px * self.quantity * fx
        return (self.entry_price - px) * self.quantity * fx

    def unrealized_from_prices(self, meta: InstrumentMeta, prices: Dict[str, float]) -> float:
        px = self._mark_price(prices)
        fx = resolve_fx_to_usd(meta, prices)
        if self.instrument_type == "future":
            if self.direction == "LONG":
                return (px - self.entry_price) * self.quantity * meta.multiplier
            return (self.entry_price - px) * self.quantity * meta.multiplier
        if self.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            return (px - self.entry_price) * self.quantity * om
        if self.direction == "LONG":
            return (px - self.entry_price) * self.quantity * fx
        return (self.entry_price - px) * self.quantity * fx

    def heat_risk_usd(self, meta: InstrumentMeta, prices: Dict[str, float]) -> float:
        """Max loss to stop in USD: |entry - stop| * qty * multiplier (or fx for ETF)."""
        if self.stop_loss is None:
            return 0.0
        fx = resolve_fx_to_usd(meta, prices)
        dist = abs(self.entry_price - self.stop_loss)
        if self.instrument_type == "future":
            return dist * self.quantity * meta.multiplier
        if self.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            return dist * self.quantity * om
        return dist * self.quantity * fx

    @classmethod
    def from_row(cls, row: Any) -> Position:
        def g(key: str, default: Any = None) -> Any:
            try:
                v = row[key]
            except (KeyError, IndexError, TypeError):
                return default
            return v

        def opt_float(k: str) -> Optional[float]:
            v = g(k)
            if v is None:
                return None
            return float(v)

        return cls(
            id=int(g("id", 0)),
            ticker=g("ticker"),
            asset_class=g("asset_class"),
            instrument_type=g("instrument_type"),
            direction=g("direction"),
            quantity=float(g("quantity")),
            entry_price=float(g("entry_price")),
            entry_date=g("entry_date"),
            current_price=opt_float("current_price"),
            unrealized_pnl=float(g("unrealized_pnl") or 0),
            stop_loss=opt_float("stop_loss"),
            take_profit=opt_float("take_profit"),
            status=g("status"),
            exit_price=opt_float("exit_price"),
            exit_date=g("exit_date"),
            realized_pnl=opt_float("realized_pnl"),
            margin_required=float(g("margin_required") or 0),
            notional_value=float(g("notional_value") or 0),
            option_type=g("option_type"),
            strike=opt_float("strike"),
            expiry=g("expiry"),
        )

    def to_insert_tuple(self) -> Tuple:
        return (
            self.ticker,
            self.asset_class,
            self.instrument_type,
            self.direction,
            self.quantity,
            self.entry_price,
            self.entry_date,
            self.current_price,
            self.unrealized_pnl,
            self.stop_loss,
            self.take_profit,
            self.status,
            self.exit_price,
            self.exit_date,
            self.realized_pnl,
            self.margin_required,
            self.notional_value,
            self.option_type,
            self.strike,
            self.expiry,
        )
