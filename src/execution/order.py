"""Order and intent models (system spec)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class OrderIntent(BaseModel):
    ticker: str
    action: str
    size_pct_nav: float = Field(ge=0, le=100)
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    stop_loss_pct: float = Field(ge=0)
    take_profit_pct: float = Field(ge=0)
    rationale: str = ""
    confidence: str = "MEDIUM"
    signal_source: str = ""
    option_details: Optional[Dict[str, Any]] = None
