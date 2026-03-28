"""Lookup table from `instruments.yaml` for margin and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.utils.config import load_instruments

_CATEGORY_ASSET_TYPE: Dict[str, tuple[str, str]] = {
    "equity_index_futures": ("equity_index", "future"),
    "equity_index_etfs": ("equity_index", "etf"),
    "bond_futures": ("bond", "future"),
    "bond_etfs": ("bond", "etf"),
    "commodity_futures": ("commodity", "future"),
}


@dataclass
class InstrumentMeta:
    ticker: str
    name: str
    asset_class: str
    instrument_type: str  # future | etf
    multiplier: float = 1.0
    margin_pct: float = 0.0
    currency: str = "USD"
    fx_ticker: Optional[str] = None
    option_contract_multiplier: Optional[float] = None


def resolve_fx_to_usd(meta: InstrumentMeta, prices: Dict[str, float]) -> float:
    """USD value multiplier for one unit of local price (share in local currency)."""
    if meta.currency == "USD":
        return 1.0
    if not meta.fx_ticker:
        return 1.0
    rate = prices.get(meta.fx_ticker)
    if rate is None or rate <= 0:
        return 1.0
    r = float(rate)
    if meta.currency in ("GBP", "EUR"):
        return r
    if meta.currency == "CAD":
        return 1.0 / r
    if meta.currency == "JPY":
        return 1.0 / r
    return r


def build_registry(raw: Optional[Dict[str, Any]] = None) -> Dict[str, InstrumentMeta]:
    data = raw or load_instruments()
    out: Dict[str, InstrumentMeta] = {}

    ordered_cats = [
        "equity_index_futures",
        "equity_index_etfs",
        "bond_futures",
        "bond_etfs",
        "commodity_futures",
    ]
    for cat in ordered_cats:
        asset_class, inst_type = _CATEGORY_ASSET_TYPE[cat]
        for row in data.get(cat) or []:
            t = row.get("ticker")
            if not t:
                continue
            mult = float(row.get("multiplier", 1 if inst_type == "etf" else 50))
            margin_pct = float(row.get("margin_pct", 0.0))
            existing = out.get(t)
            out[t] = InstrumentMeta(
                ticker=t,
                name=row.get("name", t),
                asset_class=asset_class,
                instrument_type=inst_type,
                multiplier=mult,
                margin_pct=margin_pct,
                currency=row.get("currency", "USD"),
                fx_ticker=row.get("fx_ticker"),
                option_contract_multiplier=existing.option_contract_multiplier
                if existing
                else None,
            )

    for row in data.get("options_underlyings") or []:
        t = row.get("ticker")
        if not t:
            continue
        om = float(row.get("multiplier", 100))
        existing = out.get(t)
        if existing:
            existing.option_contract_multiplier = om
        else:
            out[t] = InstrumentMeta(
                ticker=t,
                name=row.get("name", t),
                asset_class=_infer_asset_class_from_ticker(t, row),
                instrument_type="etf",
                multiplier=1.0,
                margin_pct=0.0,
                currency=row.get("currency", "USD"),
                fx_ticker=row.get("fx_ticker"),
                option_contract_multiplier=om,
            )
    return out


def _infer_asset_class_from_ticker(t: str, row: Dict[str, Any]) -> str:
    if t in ("TLT",):
        return "bond"
    if t in ("GLD", "USO"):
        return "commodity"
    return "equity_index"


def tradeable_tickers(registry: Dict[str, InstrumentMeta]) -> frozenset[str]:
    return frozenset(registry.keys())
