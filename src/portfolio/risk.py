"""Hard risk limits and order validation (risk-management spec)."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from src.execution.order import OrderIntent
from src.portfolio.hold_rules import min_hold_exit_blocked
from src.portfolio.instrument_registry import InstrumentMeta, build_registry, resolve_fx_to_usd
from src.portfolio.margin import margin_required_usd
from src.portfolio.portfolio import Portfolio
from src.portfolio.position import Position
from src.utils.config import load_settings


def estimate_entry_quantity(
    *,
    nav: float,
    size_pct_nav: float,
    ref_price: float,
    meta: InstrumentMeta,
    instrument_type: str,
    option_premium: Optional[float] = None,
) -> float:
    """Target quantity for a new leg at `ref_price` (underlying for options)."""
    if ref_price <= 0 or nav <= 0:
        return 0.0
    notion = nav * (size_pct_nav / 100.0)
    if instrument_type == "future":
        per_contract = ref_price * meta.multiplier
        return max(0.0, notion / max(per_contract, 1e-9))
    if instrument_type == "option":
        prem = option_premium if option_premium is not None else ref_price * 0.05
        om = meta.option_contract_multiplier or 100.0
        per_contract = prem * om
        q = int(notion // max(per_contract, 1e-6))
        return float(max(1, q))
    return notion / ref_price


def absolute_stops(
    *,
    entry: float,
    action: str,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> Tuple[float, float]:
    """Absolute stop and take-profit prices. Percent inputs are whole numbers (2 => 2%)."""
    sl_r = stop_loss_pct / 100.0
    tp_r = take_profit_pct / 100.0
    if action == "BUY":
        return entry * (1.0 - sl_r), entry * (1.0 + tp_r)
    if action == "SHORT":
        return entry * (1.0 + sl_r), entry * (1.0 - tp_r)
    raise ValueError(f"absolute_stops only for opening actions, got {action}")


def portfolio_heat_pct(portfolio: Portfolio, prices: Dict[str, float]) -> float:
    nav = portfolio.get_nav(prices)
    if nav <= 0:
        return 0.0
    reg = build_registry()
    total = 0.0
    for p in portfolio.get_open_positions():
        meta = reg.get(p.ticker)
        if not meta:
            continue
        total += p.heat_risk_usd(meta, prices)
    return (total / nav) * 100.0


def positions_can_merge(existing: Position, order: OrderIntent) -> bool:
    """True if an incremental BUY/SHORT should add to `existing` instead of opening a second row."""
    if order.action == "BUY" and existing.direction != "LONG":
        return False
    if order.action == "SHORT" and existing.direction != "SHORT":
        return False
    if order.ticker != existing.ticker:
        return False
    if order.option_details:
        if existing.instrument_type != "option":
            return False
        od = order.option_details
        if existing.strike is None or existing.expiry is None or not existing.option_type:
            return False
        if float(od["strike"]) != float(existing.strike):
            return False
        if str(od["expiry"]) != str(existing.expiry):
            return False
        if od.get("option_type") != existing.option_type:
            return False
        return True
    if existing.instrument_type == "option":
        return False
    return True


def positions_by_asset_class(portfolio: Portfolio) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in portfolio.get_open_positions():
        counts[p.asset_class] = counts.get(p.asset_class, 0) + 1
    return counts


def validate_order(
    order: OrderIntent,
    portfolio: Portfolio,
    prices: Dict[str, float],
    *,
    as_of: Optional[str] = None,
    registry: Optional[Dict[str, InstrumentMeta]] = None,
    settings: Optional[dict] = None,
    merge_into: Optional[Position] = None,
) -> Tuple[bool, str]:
    """Pre-trade checks. Returns (ok, reason).

    If ``merge_into`` is set, limits are checked against the combined leg (existing + add)
    instead of the add alone (pyramiding into the same open position).
    """
    settings = settings or load_settings()
    registry = registry or build_registry()
    risk = settings.get("risk", {})
    max_pos_pct = float(risk.get("max_position_pct", 20.0))
    max_margin_pct = float(risk.get("max_margin_utilization", 60.0))
    max_heat_pct = float(risk.get("max_portfolio_heat", 10.0))
    warn_dd = float(risk.get("circuit_breaker_warn", 15.0))

    meta = registry.get(order.ticker)
    if meta is None:
        return False, f"Unknown ticker {order.ticker}"

    ref = prices.get(order.ticker)
    if ref is None or ref <= 0:
        return False, f"No price for {order.ticker}"

    nav = portfolio.get_nav(prices)
    if nav <= 0:
        return False, "NAV is non-positive"

    if order.action in ("SELL", "COVER"):
        op = portfolio.find_open_position(order.ticker, long_side=(order.action == "SELL"))
        if not op:
            return False, f"No matching open position for {order.action} {order.ticker}"
        if as_of is not None:
            blocked = min_hold_exit_blocked(op.entry_date, as_of, settings)
            if blocked:
                return False, blocked
        return True, ""

    if order.action == "BUY":
        if portfolio.circuit_warn_active(prices, warn_dd):
            return False, f"Circuit breaker: drawdown >= {warn_dd}% blocks new longs"

    if order.stop_loss_pct <= 0 or order.take_profit_pct <= 0:
        return False, "stop_loss_pct and take_profit_pct must be positive"

    opts_on = bool(settings.get("trading", {}).get("options_enabled", True))
    if order.option_details and not opts_on:
        return False, "Options trading is disabled (trading.options_enabled: false in settings.yaml)"

    if order.option_details:
        if order.action != "BUY":
            return False, "Long options only (BUY) in paper v1"
        for k in ("strike", "expiry", "option_type"):
            if k not in order.option_details:
                return False, f"option_details missing {k}"

    if order.action == "SHORT" and meta.instrument_type not in ("future", "etf"):
        return False, "SHORT only supported on futures or ETFs in paper mode"

    inst_for_qty = meta.instrument_type
    prem: Optional[float] = None
    if order.option_details:
        inst_for_qty = "option"
        prem = float(order.option_details.get("premium") or (ref * 0.05))

    qty = estimate_entry_quantity(
        nav=nav,
        size_pct_nav=order.size_pct_nav,
        ref_price=ref,
        meta=meta,
        instrument_type=inst_for_qty,
        option_premium=prem,
    )
    if qty <= 0:
        return False, "Zero quantity after sizing"

    entry_guess = prem if prem is not None else ref

    direction = "LONG" if order.action == "BUY" else "SHORT"
    asset_class = meta.asset_class
    instrument_type_row = meta.instrument_type
    om = meta.option_contract_multiplier or 100.0
    if order.option_details:
        instrument_type_row = "option"

    if merge_into is not None:
        if merge_into.id is None:
            return False, "merge_into position must be persisted"
        if not positions_can_merge(merge_into, order):
            return False, "Order is not eligible to merge into existing position"
        comb_qty = merge_into.quantity + qty
        comb_entry = (
            merge_into.quantity * merge_into.entry_price + qty * entry_guess
        ) / comb_qty
        try:
            stop_px, tp_px = absolute_stops(
                entry=comb_entry,
                action=order.action,
                stop_loss_pct=order.stop_loss_pct,
                take_profit_pct=order.take_profit_pct,
            )
        except ValueError as e:
            return False, str(e)
        proposed = Position(
            id=None,
            ticker=order.ticker,
            asset_class=asset_class,
            instrument_type=instrument_type_row,
            direction=direction,
            quantity=comb_qty,
            entry_price=comb_entry,
            entry_date="",
            current_price=comb_entry,
            unrealized_pnl=0.0,
            stop_loss=stop_px,
            take_profit=tp_px,
            status="OPEN",
            exit_price=None,
            exit_date=None,
            realized_pnl=None,
            margin_required=0.0,
            notional_value=0.0,
            option_type=merge_into.option_type,
            strike=merge_into.strike,
            expiry=merge_into.expiry,
        )
    else:
        try:
            stop_px, tp_px = absolute_stops(
                entry=entry_guess,
                action=order.action,
                stop_loss_pct=order.stop_loss_pct,
                take_profit_pct=order.take_profit_pct,
            )
        except ValueError as e:
            return False, str(e)

        proposed = Position(
            id=None,
            ticker=order.ticker,
            asset_class=asset_class,
            instrument_type=instrument_type_row,
            direction=direction,
            quantity=qty,
            entry_price=entry_guess,
            entry_date="",
            current_price=entry_guess,
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

    fx = resolve_fx_to_usd(meta, prices)
    if instrument_type_row == "future":
        notional = abs(qty * entry_guess * meta.multiplier)
    elif instrument_type_row == "option":
        notional = abs(qty * entry_guess * om)
    else:
        notional = abs(qty * entry_guess * fx)

    proposed.notional_value = notional
    proposed.margin_required = margin_required_usd(meta, proposed, ref)

    if (notional / nav) * 100.0 > max_pos_pct + 1e-6:
        return False, f"Position would exceed {max_pos_pct}% NAV (notional {(notional/nav)*100:.2f}%)"

    other_margin = portfolio.total_margin_used_ex_new(prices, exclude_ticker=order.ticker)
    new_margin = other_margin + proposed.margin_required
    if (new_margin / nav) * 100.0 > max_margin_pct + 1e-6:
        return False, f"Margin utilization would exceed {max_margin_pct}%"

    other_heat = portfolio.total_heat_usd_ex_new(prices, exclude_ticker=order.ticker)
    new_heat = other_heat + proposed.heat_risk_usd(meta, prices)
    if (new_heat / nav) * 100.0 > max_heat_pct + 1e-6:
        return False, f"Portfolio heat would exceed {max_heat_pct}% NAV"

    return True, ""


def circuit_should_halt_close_largest(
    portfolio: Portfolio,
    prices: Dict[str, float],
) -> bool:
    settings = load_settings()
    halt_dd = float(settings.get("risk", {}).get("circuit_breaker_halt", 20.0))
    return portfolio.drawdown_pct(prices) >= halt_dd


def tickers_to_close_on_halt(
    portfolio: Portfolio,
    prices: Dict[str, float],
    max_positions: int = 3,
) -> List[str]:
    """Largest open legs by notional (for Level-2 circuit)."""
    reg = build_registry()
    scored: List[Tuple[float, str]] = []
    for p in portfolio.get_open_positions():
        meta = reg.get(p.ticker)
        if not meta:
            continue
        px = prices.get(p.ticker) or p.entry_price
        if p.instrument_type == "future":
            n = abs(p.quantity * px * meta.multiplier)
        elif p.instrument_type == "option":
            om = meta.option_contract_multiplier or 100.0
            n = abs(p.quantity * px * om)
        else:
            fx = resolve_fx_to_usd(meta, prices)
            n = abs(p.quantity * px * fx)
        scored.append((n, p.ticker))
    scored.sort(reverse=True)
    seen: Set[str] = set()
    out: List[str] = []
    for _n, t in scored:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_positions:
            break
    return out
