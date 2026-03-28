"""Finnhub headlines with VADER sentiment aggregation."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, List, Optional, Tuple

import finnhub
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.data.data_cache import get_cached, set_cached
from src.utils.config import load_settings
from src.utils.retry import with_backoff

logger = logging.getLogger(__name__)

ROLLING_STATE_KEY = "finnhub:news:rolling_v1"

_ANALYZER = SentimentIntensityAnalyzer()

# Rough keyword buckets for aggregate_sentiment (headline text)
_EQUITY_PAT = re.compile(
    r"\b(stock|stocks|equity|equities|s&p|nasdaq|dow|earnings|ipo|fed|rates|inflation)\b",
    re.I,
)
_BOND_PAT = re.compile(
    r"\b(bond|treasury|yield|curve|tlt|credit|duration)\b",
    re.I,
)
_CMDTY_PAT = re.compile(
    r"\b(oil|crude|gold|silver|copper|commodity|gas|opec|brent|wti)\b",
    re.I,
)


def _bucket_for(text: str) -> set[str]:
    t = text or ""
    tags: set[str] = set()
    if _EQUITY_PAT.search(t):
        tags.add("equities")
    if _BOND_PAT.search(t):
        tags.add("bonds")
    if _CMDTY_PAT.search(t):
        tags.add("commodities")
    return tags


def _client() -> finnhub.Client:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        raise RuntimeError("FINNHUB_API_KEY is not set")
    return finnhub.Client(api_key=key)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _build_batch_from_finnhub(raw: list, *, max_items: int, ingested_at: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw[: max_items * 3]:
        title = (item.get("headline") or item.get("title") or "").strip()
        if not title:
            continue
        compound = float(_ANALYZER.polarity_scores(title)["compound"])
        ts = item.get("datetime") or item.get("id")
        if ts is not None:
            ts = int(ts)
        rows.append(
            {
                "title": title,
                "source": item.get("source") or "",
                "sentiment": compound,
                "datetime": ts,
                "ingested_at": ingested_at,
            }
        )
        if len(rows) >= max_items:
            break
    return rows


def _aggregate_from_headlines(headlines: list[dict[str, Any]]) -> dict[str, float]:
    agg: dict[str, list[float]] = {"equities": [], "bonds": [], "commodities": [], "overall": []}
    for row in headlines:
        title = row.get("title") or ""
        compound = float(row.get("sentiment", 0.0))
        buckets = _bucket_for(title)
        agg["overall"].append(compound)
        for b in buckets:
            agg[b].append(compound)
    return {
        "equities": _mean(agg["equities"]) if agg["equities"] else _mean(agg["overall"]),
        "bonds": _mean(agg["bonds"]) if agg["bonds"] else _mean(agg["overall"]),
        "commodities": _mean(agg["commodities"]) if agg["commodities"] else _mean(agg["overall"]),
        "overall": _mean(agg["overall"]),
    }


def _retention_filter_batches(
    batches: List[List[dict[str, Any]]],
    retention_cutoff: float,
) -> List[List[dict[str, Any]]]:
    out: List[List[dict[str, Any]]] = []
    for batch in batches:
        nb = [
            h
            for h in batch
            if float(h.get("ingested_at", time.time())) >= retention_cutoff
        ]
        if nb:
            out.append(nb)
    return out


def _dedupe_flatten_newest_first(
    batches: List[List[dict[str, Any]]],
    max_headlines: int,
) -> list[dict[str, Any]]:
    """Batches ordered newest-first; duplicate (title, source) keeps first occurrence (newest)."""
    seen: set[Tuple[str, str]] = set()
    flat: list[dict[str, Any]] = []
    for batch in batches:
        for h in batch:
            key = (h.get("title") or "", h.get("source") or "")
            if key in seen:
                continue
            seen.add(key)
            flat.append(h)
            if len(flat) >= max_headlines:
                return flat
    return flat


def fetch_news_sentiment() -> dict[str, Any]:
    settings = load_settings()
    data_cfg = settings.get("data", {})
    max_per_fetch = int(data_cfg.get("max_news_headlines", 30))
    max_batches = int(data_cfg.get("news_rolling_fetch_batches", 5))
    max_headlines = int(
        data_cfg.get("news_rolling_max_headlines", max_per_fetch * max_batches)
    )
    retention_days = float(data_cfg.get("news_headline_retention_days", 7))
    cooldown_hours = float(data_cfg.get("news_finnhub_cooldown_hours", 0))
    ttl_seconds = max(86400.0, (retention_days + 2.0) * 86400.0)

    now = time.time()
    retention_cutoff = now - retention_days * 86400.0

    state: dict[str, Any] = get_cached(ROLLING_STATE_KEY) or {
        "batches": [],
        "last_fetch_ts": 0.0,
    }
    batches: List[List[dict[str, Any]]] = _retention_filter_batches(
        list(state.get("batches") or []),
        retention_cutoff,
    )
    last_fetch = float(state.get("last_fetch_ts") or 0.0)

    err: Optional[str] = None
    cooldown_active = cooldown_hours > 0 and (now - last_fetch) < (cooldown_hours * 3600.0)

    if not cooldown_active:
        def call() -> list:
            c = _client()
            return c.general_news("general", min_id=0)

        try:
            raw = with_backoff(call, operation="finnhub:general_news")
            new_batch = _build_batch_from_finnhub(
                raw, max_items=max_per_fetch, ingested_at=now
            )
            batches = [new_batch] + batches[: max_batches - 1]
            state["last_fetch_ts"] = now
        except Exception as e:
            logger.error("finnhub_news_failed", extra={"error": str(e)})
            err = str(e)

    flat = _dedupe_flatten_newest_first(batches, max_headlines)
    state["batches"] = batches

    result = {
        "headlines": flat,
        "aggregate_sentiment": _aggregate_from_headlines(flat),
    }
    if err:
        result["error"] = err

    set_cached(ROLLING_STATE_KEY, state, ttl_seconds=ttl_seconds)
    return result
