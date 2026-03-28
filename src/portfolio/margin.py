"""Initial margin by instrument type (portfolio-engine spec)."""

from __future__ import annotations

from src.portfolio.instrument_registry import InstrumentMeta
from src.portfolio.position import Position

SHORT_OPTION_MARGIN_FRAC = 0.20


def margin_required_usd(
    meta: InstrumentMeta,
    position: Position,
    underlying_price: float,
) -> float:
    px = position.entry_price if position.current_price is None else float(position.current_price)
    if position.instrument_type == "future":
        return abs(position.quantity) * px * meta.multiplier * (meta.margin_pct / 100.0)
    if position.instrument_type == "option":
        if position.direction == "LONG":
            return 0.0
        om = meta.option_contract_multiplier or 100.0
        return abs(position.quantity) * underlying_price * om * SHORT_OPTION_MARGIN_FRAC
    if position.instrument_type == "etf" and position.direction == "SHORT":
        return abs(position.quantity) * px * 0.30
    return 0.0
