"""Daily orchestrator: data → stops → Claude → execute → snapshot."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from src.brain.claude_client import ClaudeUsage, call_claude, estimate_cost_usd
from src.brain.claude_tools import ClaudeToolContext
from src.brain.prompt_builder import build_user_prompt
from src.brain.response_parser import REPAIR_SUFFIX, ClaudeDecision, orders_to_intents, parse_claude_response
from src.data.economic_data import fetch_economic_snapshot
from src.data.market_data import fetch_market_snapshot, last_close_prices
from src.data.news_sentiment import fetch_news_sentiment
from src.execution.order import OrderIntent
from src.execution.simulator import PaperSimulator
from src.journal.performance import (
    compute_metrics_from_nav_series,
    load_snapshot_rows,
    next_metrics_for_prompt,
    prior_nav_before,
)
from src.portfolio import risk
from src.portfolio.portfolio import Portfolio
from src.utils.config import load_settings
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _safe_econ(as_of: str) -> Dict[str, Any]:
    try:
        return fetch_economic_snapshot()
    except Exception as e:
        logger.warning("economic_fetch_failed", extra={"error": str(e)})
        return {"as_of": as_of, "series": {}, "error": str(e)}


def _safe_news() -> Dict[str, Any]:
    try:
        return fetch_news_sentiment()
    except Exception as e:
        logger.warning("news_fetch_failed", extra={"error": str(e)})
        return {"headlines": [], "aggregate_sentiment": {}, "error": str(e)}


def _safe_market() -> Dict[str, Any]:
    try:
        return fetch_market_snapshot(options_chains=True)
    except Exception as e:
        logger.error("market_fetch_failed", extra={"error": str(e)})
        return {"tickers": {}, "error": str(e)}


def _close_ticker(
    portfolio: Portfolio,
    sim: PaperSimulator,
    ticker: str,
    prices: Dict[str, float],
    trade_date: str,
    *,
    rationale: str,
) -> None:
    if portfolio.find_open_position(ticker, long_side=True):
        sim.execute_intent(
            portfolio,
            OrderIntent(
                ticker=ticker,
                action="SELL",
                size_pct_nav=0.0,
                stop_loss_pct=1.0,
                take_profit_pct=1.0,
                rationale=rationale,
                signal_source="orchestrator",
            ),
            prices,
            trade_date,
        )
    elif portfolio.find_open_position(ticker, long_side=False):
        sim.execute_intent(
            portfolio,
            OrderIntent(
                ticker=ticker,
                action="COVER",
                size_pct_nav=0.0,
                stop_loss_pct=1.0,
                take_profit_pct=1.0,
                rationale=rationale,
                signal_source="orchestrator",
            ),
            prices,
            trade_date,
        )


def run_daily(as_of: str, *, skip_claude: bool = False) -> None:
    load_dotenv()
    setup_logging()
    settings = load_settings()
    initial = float(settings.get("portfolio", {}).get("initial_capital", 1_000_000.0))

    portfolio = Portfolio()
    portfolio.load_state()
    sim = PaperSimulator(settings=settings)

    market = _safe_market()
    prices = last_close_prices(market)
    if not prices:
        logger.error("no_market_prices_aborting")
        return

    portfolio.update_prices(prices)

    triggered = portfolio.check_stop_loss_take_profit(prices)
    for pos, reason, exit_px in list(triggered):
        if pos.id:
            portfolio.close_position(
                pos.id,
                exit_px,
                as_of,
                rationale="system",
                exit_reason=reason,
                commission=0.0,
                slippage_bps=0.0,
            )
    if triggered:
        portfolio.load_state()

    if risk.circuit_should_halt_close_largest(portfolio, prices):
        for t in risk.tickers_to_close_on_halt(portfolio, prices):
            _close_ticker(portfolio, sim, t, prices, as_of, rationale="circuit_breaker_halt")
        portfolio.load_state()

    econ = _safe_econ(as_of)
    news = _safe_news()

    nav0 = portfolio.get_nav(prices)
    daily_pct, cum_pct, sharpe_hint = next_metrics_for_prompt(as_of, nav0)

    user_prompt = build_user_prompt(
        as_of=as_of,
        portfolio=portfolio,
        prices=prices,
        market=market,
        economic=econ,
        news=news,
        daily_return_pct=daily_pct,
        ytd_return_pct=cum_pct,
        sharpe=sharpe_hint,
    )

    raw_final = ""
    usage_tot = ClaudeUsage(0, 0, str(settings.get("claude", {}).get("model", "")))
    dec: Optional[ClaudeDecision] = None
    err: Optional[str] = None

    if skip_claude:
        dec = ClaudeDecision(
            market_regime="N/A",
            macro_summary="--skip-claude",
            orders=[],
            positions_to_close=[],
            risk_notes="",
            session_learnings=[],
        )
        raw_final = '{"skipped": true}'
    else:
        try:
            tool_ctx = ClaudeToolContext(portfolio=portfolio)
            raw, usage = call_claude(user_prompt, settings=settings, tool_context=tool_ctx)
            raw_final = raw
            usage_tot = usage
            dec, err = parse_claude_response(raw)
            if dec is None:
                raw2, usage2 = call_claude(
                    user_prompt + REPAIR_SUFFIX,
                    settings=settings,
                    tool_context=tool_ctx,
                    disable_tools=True,
                )
                raw_final = raw2
                usage_tot = ClaudeUsage(
                    input_tokens=usage.input_tokens + usage2.input_tokens,
                    output_tokens=usage.output_tokens + usage2.output_tokens,
                    model=usage.model,
                )
                dec, err = parse_claude_response(raw2)
        except Exception as e:
            logger.exception("claude_failed")
            err = str(e)
            dec = None

    cost = estimate_cost_usd(usage_tot, settings) if not skip_claude else 0.0

    if dec:
        portfolio.write_daily_analysis(
            as_of,
            market_regime=dec.market_regime,
            macro_summary=dec.macro_summary,
            risk_notes=(dec.risk_notes or "") + (f" | parse_note: {err}" if err else ""),
            raw_response=raw_final[:200_000],
            input_tokens=usage_tot.input_tokens,
            output_tokens=usage_tot.output_tokens,
            estimated_cost_usd=cost,
        )
    else:
        portfolio.write_daily_analysis(
            as_of,
            market_regime="ERROR",
            macro_summary="",
            risk_notes=err or "unknown",
            raw_response=raw_final[:200_000],
            input_tokens=usage_tot.input_tokens,
            output_tokens=usage_tot.output_tokens,
            estimated_cost_usd=cost,
        )

    if dec is not None and not skip_claude:
        portfolio.append_session_learnings(as_of, dec.session_learnings)

    if dec:
        for t in dec.positions_to_close:
            _close_ticker(
                portfolio,
                sim,
                t,
                prices,
                as_of,
                rationale="claude_positions_to_close",
            )
        for intent in orders_to_intents(dec):
            ok, msg, _ = sim.execute_intent(portfolio, intent, prices, as_of)
            if not ok:
                logger.warning("order_rejected", extra={"ticker": intent.ticker, "reason": msg})

    portfolio.load_state()
    portfolio.update_prices(prices)
    nav_final = portfolio.get_nav(prices)
    prev = prior_nav_before(as_of)
    daily_dec = (nav_final / prev - 1.0) if prev and prev > 0 else None

    hist = load_snapshot_rows()
    navs = [float(r[1]) for r in hist] + [nav_final]
    m = compute_metrics_from_nav_series(navs, initial_nav=initial)

    portfolio.write_snapshot(
        as_of,
        prices,
        daily_return=daily_dec,
        cumulative_return=m.get("cumulative_return"),
        sharpe_ratio=m.get("sharpe_ratio"),
        max_drawdown=m.get("max_drawdown"),
    )

    logger.info(
        "daily_cycle_complete",
        extra={"as_of": as_of, "nav": nav_final, "skip_claude": skip_claude},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoTradingBot daily cycle")
    parser.add_argument("--date", type=str, default=None, help="Trading date YYYY-MM-DD (UTC)")
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Collect data and update snapshot without calling Anthropic",
    )
    args = parser.parse_args()
    as_of = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_daily(as_of, skip_claude=args.skip_claude)


if __name__ == "__main__":
    main()
