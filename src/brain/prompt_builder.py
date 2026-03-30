"""Assemble the daily user prompt: DAILY PIPELINE preamble + claude-brain data sections."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.portfolio.instrument_registry import InstrumentMeta, build_registry
from src.portfolio.portfolio import Portfolio
from src.utils.config import load_settings


def _fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def _section_daily_pipeline() -> str:
    """Context from docs/user-guide-trading-decisions.md — what already ran before this prompt."""
    return "\n".join(
        [
            "## DAILY PIPELINE (already executed before you; execution order after your reply)",
            "1. Prices were refreshed and the portfolio state below reflects the current book.",
            "2. Stops and take-profits: any hit levels were closed automatically (you were not consulted).",
            "3. Severe drawdown: if NAV breached `circuit_breaker_halt` in settings, the system force-closed "
            "largest positions to reduce risk (automatic).",
            "4. This briefing — portfolio, market stats, economic indicators, news — was built for you.",
            "5. You respond once with JSON: `market_regime`, `macro_summary`, `orders`, "
            "`positions_to_close`, `risk_notes`, and optional `session_learnings`.",
            "6. After your reply, **`positions_to_close` is applied first** (flatten those tickers: "
            "sell longs / cover shorts, rationale `claude_positions_to_close`); then `orders` are validated and filled.",
            "",
            "Machine rails run first; your plan is then checked against the real book and risk limits.",
        ]
    )


def _section_portfolio(
    as_of: str,
    portfolio: Portfolio,
    prices: Dict[str, float],
    *,
    daily_return_pct: Optional[float],
    ytd_return_pct: Optional[float],
    sharpe: Optional[float],
) -> str:
    summary = portfolio.to_summary_dict(prices)
    nav = summary["nav"]
    cash = summary["cash"]
    mu = summary["margin_utilization_pct"]

    dr = f"{daily_return_pct:.2f}%" if daily_return_pct is not None else "n/a"
    ytd = f"{ytd_return_pct:.2f}%" if ytd_return_pct is not None else "n/a"
    sh = f"{sharpe:.2f}" if sharpe is not None else "n/a"

    st = load_settings()
    mh = int(st.get("portfolio", {}).get("min_hold_calendar_days", 1) or 0)
    tz_ref = st.get("schedule", {}).get("timezone", "America/New_York")

    lines = [
        f"## PORTFOLIO STATE (as of {as_of})",
        f"NAV: {_fmt_money(nav)} | Cash: {_fmt_money(cash)} | Margin Used: {mu:.1f}% | "
        f"Daily Return: {dr} | YTD Return: {ytd} | Sharpe: {sh}",
    ]
    if mh > 0:
        lines.append(
            f"**Min hold:** {mh} session calendar day(s) before any exit (stops/Claude/circuit); "
            f"live session date uses `{tz_ref}`."
        )
    lines.extend(
        [
            "",
            "OPEN POSITIONS:",
            "| Ticker | Dir | Qty | Entry | Current | Unrealized P&L | Stop | TP |",
            "|--------|-----|-----|-------|---------|----------------|------|----|",
        ]
    )
    reg = build_registry()
    for p in portfolio.get_open_positions():
        meta = reg.get(p.ticker)
        name = meta.name if meta else p.ticker
        cur = p.current_price if p.current_price is not None else p.entry_price
        u_px = prices.get(p.ticker) or cur
        if meta:
            upnl = p.unrealized_from_prices(meta, prices)
        else:
            upnl = p.unrealized_pnl
        sl = f"{p.stop_loss:.4g}" if p.stop_loss is not None else ""
        tp = f"{p.take_profit:.4g}" if p.take_profit is not None else ""
        lines.append(
            f"| {p.ticker} | {p.direction} | {p.quantity:.4g} | {p.entry_price:.4g} | {float(u_px):.4g} | "
            f"{upnl:,.0f} | {sl} | {tp} |"
        )
    if len(portfolio.get_open_positions()) == 0:
        lines.append("| (none) | | | | | | | |")
    lines.append("")
    lines.append(f"Instrument names (reference): use tickers exactly as listed in MARKET DATA.")
    return "\n".join(lines)


def _bucket_for_ticker(ticker: str, reg: Dict[str, InstrumentMeta]) -> str:
    if "=X" in ticker.upper():
        return "FX RATES"
    meta = reg.get(ticker)
    if not meta:
        return "OTHER"
    if meta.instrument_type == "future":
        if meta.asset_class == "bond":
            return "BONDS"
        if meta.asset_class == "commodity":
            return "COMMODITIES"
        return "EQUITY INDICES (futures & index-linked)"
    return "ETFs & OPTIONS UNDERLYINGS"


def _group_market_rows(market: Dict[str, Any]) -> Dict[str, List[tuple]]:
    reg = build_registry()
    groups: Dict[str, List[tuple]] = {}
    tickers_map = market.get("tickers") or {}
    for ticker, row in tickers_map.items():
        if "error" in row:
            continue
        key = _bucket_for_ticker(ticker, reg)
        if key == "OTHER":
            key = "ETFs & OPTIONS UNDERLYINGS"
        last = row.get("last_close")
        ch5 = row.get("change_5d_pct")
        sma20 = row.get("sma_20")
        sma50 = row.get("sma_50")
        rsi = row.get("rsi_14")
        atr = row.get("atr_14")
        groups.setdefault(key, []).append((ticker, last, ch5, sma20, sma50, rsi, atr))
    return groups


def _section_market(market: Dict[str, Any]) -> str:
    lines = ["## MARKET DATA"]
    groups = _group_market_rows(market)
    for title, rows in groups.items():
        if not rows:
            continue
        lines.append(title)
        lines.append("| Ticker | Last | 5D Chg% | SMA20 | SMA50 | RSI | ATR |")
        lines.append("|--------|------|---------|-------|-------|-----|-----|")
        for t, last, ch5, s20, s50, rsi, atr in sorted(rows, key=lambda x: x[0]):
            lines.append(
                f"| {t} | {last} | {ch5} | {s20} | {s50} | {rsi} | {atr} |"
            )
        lines.append("")
    lines.append("## INSTRUMENT UNIVERSE (valid tickers)")
    reg = build_registry()
    lines.append(", ".join(sorted(reg.keys())))
    return "\n".join(lines)


def _section_economic(econ: Dict[str, Any]) -> str:
    lines = ["## ECONOMIC INDICATORS", "| ID | Label | Current | Previous | As-of |", "|----|-------|---------|----------|-------|"]
    series = econ.get("series") or {}
    for sid, row in series.items():
        lines.append(
            f"| {sid} | {row.get('label', '')} | {row.get('latest')} | {row.get('prior')} | {row.get('latest_date') or ''} |"
        )
    return "\n".join(lines)


def _section_news(news: Dict[str, Any]) -> str:
    settings = load_settings()
    cap = int(settings.get("data", {}).get("news_prompt_headlines_max", 150))
    agg = news.get("aggregate_sentiment") or {}
    lines = [
        "## NEWS & SENTIMENT",
        f"Overall: {agg.get('overall', 0):.2f} | Equities: {agg.get('equities', 0):.2f} | "
        f"Bonds: {agg.get('bonds', 0):.2f} | Commodities: {agg.get('commodities', 0):.2f}",
        "",
        "Top Headlines:",
    ]
    for i, h in enumerate((news.get("headlines") or [])[:cap], 1):
        lines.append(
            f"{i}. [sentiment: {h.get('sentiment', 0):.2f}] {h.get('title', '')} ({h.get('source', '')})"
        )
    if news.get("error"):
        lines.append(f"(partial/error: {news['error']})")
    return "\n".join(lines)


def _section_prior_learnings(portfolio: Portfolio, limit: int) -> str:
    if limit <= 0:
        return ""
    bullets = portfolio.fetch_recent_session_learnings(limit)
    if not bullets:
        return ""
    lines = [
        "## PRIOR SESSION LEARNINGS",
        "Notes saved from earlier runs (newest first). Discard if no longer relevant.",
        "",
    ]
    for i, lesson in enumerate(bullets, 1):
        lines.append(f"{i}. {lesson}")
    lines.append("")
    return "\n".join(lines)


def build_user_prompt(
    *,
    as_of: str,
    portfolio: Portfolio,
    prices: Dict[str, float],
    market: Dict[str, Any],
    economic: Dict[str, Any],
    news: Dict[str, Any],
    daily_return_pct: Optional[float] = None,
    ytd_return_pct: Optional[float] = None,
    sharpe: Optional[float] = None,
) -> str:
    mem_n = int(load_settings().get("claude", {}).get("session_memory_prompt_lines", 40))
    learn_block = _section_prior_learnings(portfolio, mem_n)
    parts = [
        _section_daily_pipeline(),
        _section_portfolio(
            as_of,
            portfolio,
            prices,
            daily_return_pct=daily_return_pct,
            ytd_return_pct=ytd_return_pct,
            sharpe=sharpe,
        ),
    ]
    if learn_block:
        parts.append(learn_block)
    parts.extend(
        [
            _section_market(market),
            _section_economic(economic),
            _section_news(news),
        ]
    )
    return "\n\n".join(parts)
