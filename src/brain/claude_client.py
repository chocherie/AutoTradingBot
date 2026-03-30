"""Anthropic Messages API wrapper with retries, usage tracking, and optional tools."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import anthropic

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
    "macro_summary": "2-3 sentence assessment of current macro environment",
    "orders": [
        {
            "ticker": "ES=F",
            "action": "BUY | SELL | SHORT | COVER",
            "size_pct_nav": 5.0,
            "order_type": "MARKET | LIMIT",
            "limit_price": null,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 6.0,
            "rationale": "Detailed explanation of why this trade",
            "confidence": "HIGH | MEDIUM | LOW",
            "signal_source": "What data drove this decision",
            "option_details": null
        }
    ],
    "positions_to_close": ["ticker1"],
    "risk_notes": "Any concerns about current portfolio risk",
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
- Always explain your reasoning in the rationale field on orders
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
    "macro_summary": "2-3 sentence assessment of current macro environment",
    "orders": [
        {
            "ticker": "ES=F",
            "action": "BUY | SELL | SHORT | COVER",
            "size_pct_nav": 5.0,
            "order_type": "MARKET | LIMIT",
            "limit_price": null,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 6.0,
            "rationale": "Detailed explanation of why this trade",
            "confidence": "HIGH | MEDIUM | LOW",
            "signal_source": "What data drove this decision",
            "option_details": null
        }
    ],
    "positions_to_close": ["ticker1"],
    "risk_notes": "Any concerns about current portfolio risk",
    "session_learnings": [
        "Concrete lesson from today (e.g. risk, data pitfall, execution quirk) for future runs"
    ]
}

IMPORTANT:
- Only use tickers from the provided instrument universe
- Final reply: ONLY the JSON object, no markdown fences, no commentary (after tools if any)
- If you want to make no changes, return an empty orders array
- Always explain your reasoning in the rationale field on orders
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


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=key)


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
                    extra={"attempt": attempt + 1, "error": str(e)},
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
                extra={"attempt": attempt + 1, "error": str(e)},
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
