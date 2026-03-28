"""Anthropic tool definitions + handlers (portfolio journal, safe arithmetic)."""

from __future__ import annotations

import ast
import json
import operator as op
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.portfolio.portfolio import Portfolio

# Anthropic Messages API tool schema (see Anthropic docs / SDK ToolUnionParam)
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "get_recent_trades",
        "description": (
            "Fetch recent paper executions from the trade journal (most recent first). "
            "Use when you need concrete fill history beyond the summary in the prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of trades to return (default 15, max 50)",
                }
            },
        },
    },
    {
        "name": "get_nav_history",
        "description": (
            "Fetch recent daily portfolio snapshots: NAV, daily/cumulative return, "
            "Sharpe and max drawdown as stored after each run."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of snapshot rows (default 21, max 120)",
                }
            },
        },
    },
    {
        "name": "safe_calculator",
        "description": (
            "Evaluate a numeric expression using only + - * / parentheses and decimal numbers "
            "(e.g. position sizing or risk checks). No variables or functions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": 'Arithmetic expression like "1_000_000 * 0.05 / 4500"',
                }
            },
            "required": ["expression"],
        },
    },
]


_ops = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def safe_calculator_eval(expr: str) -> float:
    """Limited eval: numbers and + - * / only (no names, no calls)."""
    cleaned = (expr or "").strip().replace("_", "")
    if not cleaned:
        raise ValueError("empty expression")
    if len(cleaned) > 80:
        raise ValueError("expression too long")
    tree = ast.parse(cleaned, mode="eval")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError("only numeric constants allowed")
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ops:
            return float(_ops[type(node.op)](_eval(node.operand)))
        if isinstance(node, ast.BinOp) and type(node.op) in _ops:
            return float(_ops[type(node.op)](_eval(node.left), _eval(node.right)))
        raise ValueError("unsupported syntax")

    return float(_eval(tree))


@dataclass
class ClaudeToolContext:
    portfolio: Portfolio


def run_claude_tool(
    name: str,
    tool_input: Optional[Dict[str, Any]],
    ctx: ClaudeToolContext,
) -> str:
    inp = tool_input or {}
    try:
        if name == "get_recent_trades":
            lim = int(inp.get("limit") or 15)
            rows = ctx.portfolio.recent_trades_for_tools(lim)
            return json.dumps({"trades": rows}, default=str)
        if name == "get_nav_history":
            lim = int(inp.get("limit") or 21)
            rows = ctx.portfolio.recent_nav_snapshots_for_tools(lim)
            return json.dumps({"snapshots": rows}, default=str)
        if name == "safe_calculator":
            expr = str(inp.get("expression") or "")
            value = safe_calculator_eval(expr)
            return json.dumps({"expression": expr, "value": value})
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool {name}"})


def tool_dispatcher(ctx: ClaudeToolContext) -> Callable[[str, Dict[str, Any]], str]:
    def _dispatch(name: str, inp: Dict[str, Any]) -> str:
        return run_claude_tool(name, inp, ctx)

    return _dispatch
