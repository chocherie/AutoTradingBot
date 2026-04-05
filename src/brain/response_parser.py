"""Extract and validate Claude JSON into ClaudeDecision + OrderIntent mapping."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

from src.execution.order import OrderIntent
from src.portfolio.instrument_registry import build_registry, tradeable_tickers

logger = logging.getLogger(__name__)


class OptionDetailsParse(BaseModel):
    type: Optional[str] = None
    option_type: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[str] = None
    strategy: Optional[str] = None

    def to_execution_dict(self) -> Dict[str, Any]:
        ot = self.option_type or self.type or "CALL"
        return {
            "option_type": ot,
            "strike": float(self.strike or 0.0),
            "expiry": str(self.expiry or ""),
            "strategy": self.strategy,
        }


class ParsedOrder(BaseModel):
    ticker: str
    action: str
    size_pct_nav: float = Field(default=0, ge=0, le=100)
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    stop_loss_pct: float = Field(ge=0)
    take_profit_pct: float = Field(ge=0)
    rationale: str = ""
    confidence: str = "MEDIUM"
    signal_source: str = ""
    option_details: Optional[Dict[str, Any]] = None

    @field_validator("action")
    @classmethod
    def norm_action(cls, v: str) -> str:
        return v.strip().upper()


class ClaudeDecision(BaseModel):
    market_regime: str
    macro_summary: str
    daily_findings: str = ""
    orders: List[ParsedOrder] = Field(default_factory=list)
    positions_to_close: List[str] = Field(default_factory=list)
    risk_notes: str = ""
    session_learnings: List[str] = Field(default_factory=list)

    @field_validator("daily_findings", mode="before")
    @classmethod
    def _coerce_daily_findings(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip() if isinstance(v, str) else str(v)

    @field_validator("session_learnings", mode="before")
    @classmethod
    def _coerce_learnings(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            return [s] if s else []
        if isinstance(v, list):
            out: List[str] = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
            return out
        return []


def extract_json_object(text: str) -> str:
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return t[start : end + 1]


def parse_claude_response(
    raw_text: str,
    *,
    repair_retry_text: Optional[str] = None,
) -> Tuple[Optional[ClaudeDecision], Optional[str]]:
    """
    Parse model output. If repair_retry_text is provided and first parse fails,
    does not auto-retry here — caller should call Claude again with repair instruction.
    Returns (decision, error_message).
    """
    try:
        blob = extract_json_object(raw_text)
        data = json.loads(blob)
        dec = ClaudeDecision.model_validate(data)
    except Exception as e:
        logger.warning("parse_claude_response_failed", extra={"error": str(e)})
        return None, str(e)

    universe = tradeable_tickers(build_registry())
    bad_orders = [o.ticker for o in dec.orders if o.ticker not in universe]
    if bad_orders:
        msg = f"Tickers not in universe: {bad_orders}"
        logger.warning(msg)
        return None, msg
    bad_close = [t for t in dec.positions_to_close if t not in universe]
    if bad_close:
        return None, f"positions_to_close tickers invalid: {bad_close}"

    return dec, None


def orders_to_intents(decision: ClaudeDecision) -> List[OrderIntent]:
    out: List[OrderIntent] = []
    for o in decision.orders:
        od = None
        if o.option_details:
            raw = dict(o.option_details)
            if "type" in raw and "option_type" not in raw:
                raw["option_type"] = raw["type"]
            try:
                op = OptionDetailsParse.model_validate(raw)
                od = op.to_execution_dict()
            except Exception:
                od = {
                    "option_type": str(raw.get("type") or raw.get("option_type") or "CALL"),
                    "strike": float(raw.get("strike", 0)),
                    "expiry": str(raw.get("expiry", "")),
                }
        out.append(
            OrderIntent(
                ticker=o.ticker,
                action=o.action,
                size_pct_nav=o.size_pct_nav,
                order_type=o.order_type,
                limit_price=o.limit_price,
                stop_loss_pct=o.stop_loss_pct,
                take_profit_pct=o.take_profit_pct,
                rationale=o.rationale,
                confidence=o.confidence,
                signal_source=o.signal_source,
                option_details=od,
            )
        )
    return out


REPAIR_SUFFIX = (
    "\n\nYour previous reply was not valid JSON. Reply again with ONLY a single JSON object "
    "matching the schema, no markdown, no commentary."
)
