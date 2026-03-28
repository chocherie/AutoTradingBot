"""Paper fills with slippage and commissions."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.execution.order import OrderIntent
from src.portfolio.instrument_registry import InstrumentMeta, build_registry
from src.portfolio.portfolio import Portfolio
from src.portfolio.position import Position
from src.portfolio import risk
from src.utils.config import load_settings


class PaperSimulator:
    def __init__(self, settings: Optional[dict] = None) -> None:
        self.settings = settings or load_settings()
        ex = self.settings.get("execution", {})
        self.slippage_bps = float(ex.get("slippage_bps", 5.0))
        self.comm_contract = float(ex.get("commission_per_contract", 2.50))
        self.comm_share = float(ex.get("commission_per_share", 0.005))

    def _commission(
        self,
        instrument_type: str,
        quantity: float,
    ) -> float:
        q = abs(quantity)
        if instrument_type in ("future", "option"):
            return q * self.comm_contract
        return q * self.comm_share

    def _fill_price(self, raw: float, action: str) -> float:
        adj = self.slippage_bps / 10000.0
        if action == "BUY":
            return raw * (1.0 + adj)
        if action == "SHORT":
            return raw * (1.0 - adj)
        if action == "SELL":
            return raw * (1.0 - adj)
        if action == "COVER":
            return raw * (1.0 + adj)
        return raw

    def execute_intent(
        self,
        portfolio: Portfolio,
        order: OrderIntent,
        prices: Dict[str, float],
        trade_date: str,
        registry: Optional[Dict[str, InstrumentMeta]] = None,
    ) -> Tuple[bool, str, List[int]]:
        """Validate, fill, persist. Returns (ok, message, affected_position_ids)."""
        registry = registry or build_registry()
        ok, reason = risk.validate_order(
            order, portfolio, prices, registry=registry, settings=self.settings
        )
        if not ok:
            return False, reason, []

        if order.action in ("SELL", "COVER"):
            p = portfolio.find_open_position(
                order.ticker, long_side=(order.action == "SELL")
            )
            if p is None or p.id is None:
                return False, "Position not found", []
            ref = float(prices[order.ticker])
            exit_px = self._fill_price(ref, order.action)
            comm = self._commission(p.instrument_type, p.quantity)
            portfolio.close_position(
                p.id,
                exit_px,
                trade_date,
                rationale=order.rationale,
                exit_reason=order.signal_source or "CLOSE",
                commission=comm,
                slippage_bps=self.slippage_bps,
            )
            return True, "", [p.id]

        meta = registry[order.ticker]
        ref = float(prices[order.ticker])
        prem: Optional[float] = None
        inst_qty_type = meta.instrument_type
        if order.option_details:
            inst_qty_type = "option"
            prem = float(order.option_details.get("premium") or (ref * 0.05))

        nav = portfolio.get_nav(prices)
        qty = risk.estimate_entry_quantity(
            nav=nav,
            size_pct_nav=order.size_pct_nav,
            ref_price=ref,
            meta=meta,
            instrument_type=inst_qty_type,
            option_premium=prem,
        )
        if qty < 1e-9:
            return False, "Zero quantity after sizing", []

        entry_raw = prem if prem is not None else ref
        entry = self._fill_price(entry_raw, order.action)
        stop_px, tp_px = risk.absolute_stops(
            entry=entry,
            action=order.action,
            stop_loss_pct=order.stop_loss_pct,
            take_profit_pct=order.take_profit_pct,
        )
        direction = "LONG" if order.action == "BUY" else "SHORT"
        inst_row = "option" if order.option_details else meta.instrument_type

        pos = Position(
            id=None,
            ticker=order.ticker,
            asset_class=meta.asset_class,
            instrument_type=inst_row,
            direction=direction,
            quantity=qty,
            entry_price=entry,
            entry_date=trade_date,
            current_price=entry,
            unrealized_pnl=0.0,
            stop_loss=stop_px,
            take_profit=tp_px,
            status="OPEN",
            exit_price=None,
            exit_date=None,
            realized_pnl=None,
            margin_required=0.0,
            notional_value=0.0,
            option_type=order.option_details.get("option_type") if order.option_details else None,
            strike=float(order.option_details["strike"]) if order.option_details else None,
            expiry=str(order.option_details["expiry"]) if order.option_details else None,
        )

        comm = self._commission(inst_row, qty)
        um = ref if order.option_details else None
        pid = portfolio.add_position(
            pos,
            trade_date=trade_date,
            commission=comm,
            slippage_bps=self.slippage_bps,
            action=order.action,
            rationale=order.rationale,
            underlying_for_margin=um,
            confidence=order.confidence,
            signal_source=order.signal_source,
        )
        return True, "", [pid]
