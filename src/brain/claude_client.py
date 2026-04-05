"""Anthropic Messages API wrapper with retries, usage tracking, and optional tools."""

from __future__ import annotations

import logging
import os
import ssl
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import anthropic
import certifi
import httpx

from src.utils.config import load_settings

logger = logging.getLogger(__name__)

# NOTE: Risk caps are also enforced in code from config/settings.yaml — keep wording aligned.
SYSTEM_PROMPT = """You are a systematic macro portfolio manager running a $1,000,000 paper trading portfolio.
You trade G7 exchange-traded instruments: equity index futures, bond futures, commodity futures, ETFs, and options.

CONSTRAINTS (hard limits enforced by the system):
- Maximum 20% of NAV in any single position
- Maximum 60% total margin utilization
- Maximum 10% portfolio heat (sum of all stop-loss distances as % of NAV)
- Every new position MUST have a stop-loss and take-profit level
- Set stop-losses at 1-3x ATR from entry price

YOUR MANDATE:
- Maximize risk-adjusted returns (Sharpe ratio is your primary metric)
- You may hold cash — being flat is a valid position
- You decide signal complexity, position sizing, and risk levels
- You can trade options for hedging, income, or directional bets
- Consider cross-asset correlations and regime changes
- Review PRIOR SESSION LEARNINGS in the user message; apply them when still relevant

TOOLS (optional):
- You may use provided tools to inspect trade history, NAV snapshots, or run safe arithmetic.
- After any tool calls, your FINAL assistant message must still be a single JSON object only.

OUTPUT FORMAT:
You MUST respond with valid JSON matching this exact schema:
{
    "market_regime": "RISK_ON | RISK_OFF | TRANSITIONAL | CRISIS",
    "macro_summary": "Exactly 2-3 sentences: high-level macro assessment only (headline, scannable)",
    "daily_findings": "Multi-paragraph expanded analysis for this session: main takeaways from MARKET DATA, economic indicators, and news; cross-asset and regime read (what changed); key uncertainties or data gaps; intended portfolio posture for today even if orders is empty. Do not paste full per-order rationales here.",
    "orders": [
        {
            "ticker": "ES=F",
            "action": "BUY | SELL | SHORT | COVER",
            "size_pct_nav": 5.0,
            "order_type": "MARKET | LIMIT",
            "limit_price": null,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 6.0,
            "rationale": "Per order: (1) market view and sentiment, (2) research findings from the briefing (prices, indicators, news) that support the trade, (3) the decision, conviction level, and why sizing and stops match conviction.",
            "confidence": "HIGH | MEDIUM | LOW",
            "signal_source": "What data drove this decision",
            "option_details": null
        }
    ],
    "positions_to_close": ["ticker1"],
    "risk_notes": "Sector-level book review: group correlated underlyings into sectors using the SAME bucket labels as ## MARKET DATA in the user message (e.g. bonds, commodities, equity indices, ETFs & options underlyings, FX). Include cash. Quantify where possible (% NAV, margin, notional) and justify each sector exposure and cash versus your stated regime.",
    "session_learnings": [
        "Concrete lesson from today (e.g. risk, data pitfall, execution quirk) for future runs"
    ]
}

For OPTIONS trades, include option_details:
{
    "option_details": {
        "type": "CALL | PUT",
        "strike": 530.0,
        "expiry": "2026-04-17",
        "strategy": "directional | hedge | income"
    }
}

IMPORTANT:
- Only use tickers from the provided instrument universe
- Final reply: ONLY the JSON object, no markdown fences, no commentary (after tools if any)
- If you want to make no changes, return an empty orders array
- macro_summary stays brief; put depth in daily_findings
- risk_notes focuses on sector/cash book and risk; put narrative synthesis in daily_findings
- Every non-empty order must have rationale covering (1) view/sentiment, (2) evidence, (3) decision and conviction vs sizing/stops
- session_learnings: 0–5 short strings; omit or use [] if nothing new to record"""

# When settings.yaml has trading.options_enabled: false
SYSTEM_PROMPT_OPTIONS_DISABLED = """You are a systematic macro portfolio manager running a $1,000,000 paper trading portfolio.
You trade G7 exchange-traded instruments: equity index futures, bond futures, commodity futures, and ETFs (options are OFF for this deployment).

CONSTRAINTS (hard limits enforced by the system):
- Maximum 20% of NAV in any single position
- Maximum 60% total margin utilization
- Maximum 10% portfolio heat (sum of all stop-loss distances as % of NAV)
- Every new position MUST have a stop-loss and take-profit level
- Set stop-losses at 1-3x ATR from entry price

YOUR MANDATE:
- Maximize risk-adjusted returns (Sharpe ratio is your primary metric)
- You may hold cash — being flat is a valid position
- You decide signal complexity, position sizing, and risk levels
- Consider cross-asset correlations and regime changes
- Review PRIOR SESSION LEARNINGS in the user message; apply them when still relevant
- Do NOT propose option trades: every order must have "option_details": null

TOOLS (optional):
- You may use provided tools to inspect trade history, NAV snapshots, or run safe arithmetic.
- After any tool calls, your FINAL assistant message must still be a single JSON object only.

OUTPUT FORMAT:
You MUST respond with valid JSON matching this exact schema:
{
    "market_regime": "RISK_ON | RISK_OFF | TRANSITIONAL | CRISIS",
    "macro_summary": "Exactly 2-3 sentences: high-level macro assessment only (headline, scannable)",
    "daily_findings": "Multi-paragraph expanded analysis for this session: main takeaways from MARKET DATA, economic indicators, and news; cross-asset and regime read (what changed); key uncertainties or data gaps; intended portfolio posture for today even if orders is empty. Do not paste full per-order rationales here.",
    "orders": [
        {
            "ticker": "ES=F",
            "action": "BUY | SELL | SHORT | COVER",
            "size_pct_nav": 5.0,
            "order_type": "MARKET | LIMIT",
            "limit_price": null,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 6.0,
            "rationale": "Per order: (1) market view and sentiment, (2) research findings from the briefing (prices, indicators, news) that support the trade, (3) the decision, conviction level, and why sizing and stops match conviction.",
            "confidence": "HIGH | MEDIUM | LOW",
            "signal_source": "What data drove this decision",
            "option_details": null
        }
    ],
    "positions_to_close": ["ticker1"],
    "risk_notes": "Sector-level book review: group correlated underlyings into sectors using the SAME bucket labels as ## MARKET DATA in the user message (e.g. bonds, commodities, equity indices, ETFs & options underlyings, FX). Include cash. Quantify where possible (% NAV, margin, notional) and justify each sector exposure and cash versus your stated regime.",
    "session_learnings": [
        "Concrete lesson from today (e.g. risk, data pitfall, execution quirk) for future runs"
    ]
}

IMPORTANT:
- Only use tickers from the provided instrument universe
- Final reply: ONLY the JSON object, no markdown fences, no commentary (after tools if any)
- If you want to make no changes, return an empty orders array
- macro_summary stays brief; put depth in daily_findings
- risk_notes focuses on sector/cash book and risk; put narrative synthesis in daily_findings
- Every non-empty order must have rationale covering (1) view/sentiment, (2) evidence, (3) decision and conviction vs sizing/stops
- session_learnings: 0–5 short strings; omit or use [] if nothing new to record"""


def system_prompt_for_settings(settings: Optional[dict] = None) -> str:
    """Full Claude system prompt; respects trading.options_enabled in settings.yaml."""
    settings = settings or load_settings()
    if bool(settings.get("trading", {}).get("options_enabled", True)):
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT_OPTIONS_DISABLED


@dataclass
class ClaudeUsage:
    input_tokens: int
    output_tokens: int
    model: str


def _exception_chain(exc: BaseException, *, max_depth: int = 5) -> str:
    """Join exception types + messages along __cause__ (SDK often hides root SSL errors)."""
    parts: List[str] = []
    cur: Optional[BaseException] = exc
    depth = 0
    while cur is not None and depth < max_depth:
        parts.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__
        depth += 1
    return " <- ".join(parts) if parts else repr(exc)


def _ssl_context_for_anthropic() -> ssl.SSLContext:
    """TLS context for Anthropic API. Prefers truststore (macOS Keychain) on 3.10+, else certifi."""
    override = os.environ.get("SSL_CERT_FILE", "").strip()
    if override:
        return ssl.create_default_context(cafile=override)
    if sys.version_info >= (3, 10):
        try:
            import truststore

            return truststore.ssl_context()
        except Exception:
            logger.debug("truststore not used; falling back to certifi", exc_info=True)
    ca = certifi.where()
    if not os.path.isfile(ca):
        logger.warning(
            "certifi CA bundle missing at %s; install certifi in this venv: pip install certifi",
            ca,
        )
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=ca)


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    # LibreSSL / macOS CLT Python: explicit SSLContext + certifi or truststore (3.10+).
    ctx = _ssl_context_for_anthropic()
    timeout = httpx.Timeout(600.0, connect=120.0)
    http = httpx.Client(verify=ctx, timeout=timeout)
    ca_h = os.environ.get("SSL_CERT_FILE", "").strip() or certifi.where()
    logger.info("anthropic_http_client_initialized", extra={"ssl_ca_hint": ca_h})
    return anthropic.Anthropic(api_key=key, http_client=http)


def _serialize_content_blocks(content: object) -> object:
    """Turn SDK content blocks into API-serializable dicts."""
    if not isinstance(content, list):
        return content
    out: List[Any] = []
    for block in content:
        if hasattr(block, "model_dump"):
            out.append(block.model_dump())
        else:
            out.append(block)
    return out


def _final_text_from_message(msg: object) -> str:
    parts: List[str] = []
    for block in getattr(msg, "content", []) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


def call_claude(
    user_prompt: str,
    *,
    system_prompt: Optional[str] = None,
    settings: Optional[dict] = None,
    tool_context: Optional[Any] = None,
    disable_tools: bool = False,
) -> Tuple[str, ClaudeUsage]:
    """
    Calls Claude with optional tool loop. tool_context must provide a portfolio-backed
    tool executor (see ClaudeToolContext in claude_tools).
    """
    settings = settings or load_settings()
    cfg = settings.get("claude", {})
    model = cfg.get("model", "claude-opus-4-20250514")
    max_tokens = int(cfg.get("max_tokens", 4096))
    temperature = float(cfg.get("temperature", 0.3))
    max_retries = int(cfg.get("max_retries", 3))
    max_tool_rounds = int(cfg.get("tool_loop_max_rounds", 6))
    use_tools = bool(cfg.get("enable_tools", True)) and tool_context is not None and not disable_tools
    delays = [2.0, 8.0, 32.0]

    client = _client()
    sys_text = system_prompt or SYSTEM_PROMPT
    last_err: Optional[Exception] = None

    if use_tools:
        from src.brain.claude_tools import TOOL_DEFINITIONS, tool_dispatcher

        dispatch = tool_dispatcher(tool_context)
        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        total_in = total_out = 0
        for attempt in range(max_retries):
            try:
                for _round in range(max_tool_rounds):
                    msg = client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=sys_text,
                        messages=messages,
                        tools=TOOL_DEFINITIONS,
                    )
                    total_in += int(getattr(msg.usage, "input_tokens", 0) or 0)
                    total_out += int(getattr(msg.usage, "output_tokens", 0) or 0)
                    stop = getattr(msg, "stop_reason", None)
                    if stop == "tool_use":
                        messages.append(
                            {"role": "assistant", "content": _serialize_content_blocks(msg.content)}
                        )
                        tool_blocks = [
                            b
                            for b in (msg.content or [])
                            if getattr(b, "type", None) == "tool_use"
                        ]
                        results: List[Dict[str, Any]] = []
                        for tb in tool_blocks:
                            tid = getattr(tb, "id", "")
                            name = getattr(tb, "name", "")
                            raw_inp = getattr(tb, "input", None) or {}
                            inp = dict(raw_inp) if isinstance(raw_inp, dict) else {}
                            payload = dispatch(name, inp)
                            results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tid,
                                    "content": payload,
                                }
                            )
                        messages.append({"role": "user", "content": results})
                        continue
                    text = _final_text_from_message(msg)
                    return text, ClaudeUsage(total_in, total_out, model)
                raise RuntimeError("claude tool loop exceeded tool_loop_max_rounds")
            except Exception as e:
                last_err = e
                logger.warning(
                    "claude_call_failed",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_chain": _exception_chain(e),
                    },
                )
                if attempt < max_retries - 1:
                    time.sleep(delays[min(attempt, len(delays) - 1)])
        assert last_err is not None
        raise last_err

    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=sys_text,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_blocks: List[str] = []
            for b in msg.content:
                if hasattr(b, "text"):
                    text_blocks.append(b.text)
            text = "".join(text_blocks)
            in_tok = getattr(msg.usage, "input_tokens", 0) or 0
            out_tok = getattr(msg.usage, "output_tokens", 0) or 0
            return text, ClaudeUsage(in_tok, out_tok, model)
        except Exception as e:
            last_err = e
            logger.warning(
                "claude_call_failed",
                extra={
                    "attempt": attempt + 1,
                    "error": str(e),
                    "error_chain": _exception_chain(e),
                },
            )
            if attempt < max_retries - 1:
                time.sleep(delays[min(attempt, len(delays) - 1)])
    assert last_err is not None
    raise last_err


def estimate_cost_usd(usage: ClaudeUsage, settings: Optional[dict] = None) -> float:
    settings = settings or load_settings()
    cfg = settings.get("claude", {})
    in_m = float(cfg.get("pricing_input_per_mtok", 15.0))
    out_m = float(cfg.get("pricing_output_per_mtok", 75.0))
    return (usage.input_tokens / 1_000_000.0) * in_m + (usage.output_tokens / 1_000_000.0) * out_m
