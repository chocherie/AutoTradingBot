"""Portfolio + SQLite persistence."""

from pathlib import Path

import pytest

from src.execution.order import OrderIntent
from src.execution.simulator import PaperSimulator
from src.portfolio import portfolio as portfolio_mod
from src.portfolio.portfolio import Portfolio


@pytest.fixture
def tmp_db(monkeypatch, tmp_path: Path) -> Path:
    db = tmp_path / "t.db"
    monkeypatch.setattr(portfolio_mod, "_db_path", lambda: db)
    return db


def test_open_future_update_stop(tmp_db):
    port = Portfolio()
    port.load_state()
    assert port.get_cash() > 0

    prices = {"ES=F": 5000.0, "NQ=F": 20000.0}
    sim = PaperSimulator()
    ok, msg, ids = sim.execute_intent(
        port,
        OrderIntent(
            ticker="ES=F",
            action="BUY",
            size_pct_nav=5.0,
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            rationale="test open",
            signal_source="test",
        ),
        prices,
        trade_date="2026-03-28",
    )
    assert ok, msg
    assert len(ids) == 1
    op = port.find_open_position("ES=F", long_side=True)
    assert op is not None
    assert op.stop_loss is not None and op.stop_loss < op.entry_price

    port.update_prices({"ES=F": 5100.0})
    prices2 = {"ES=F": 4800.0}
    port.update_prices(prices2)
    hit = port.check_stop_loss_take_profit(prices2)
    assert len(hit) == 1
    assert hit[0][1] == "STOP_LOSS_TRIGGERED"
    pnl = port.close_position(
        hit[0][0].id,
        hit[0][2],
        "2026-03-29",
        exit_reason=hit[0][1],
    )
    assert isinstance(pnl, float)
    assert port.find_open_position("ES=F") is None


def test_second_buy_same_future_merges_into_one_open_row(tmp_db):
    """Regression: two BUY intents same day must not create duplicate OPEN positions."""
    port = Portfolio()
    port.load_state()
    prices = {"BZ=F": 100.0}
    sim = PaperSimulator()
    o1 = OrderIntent(
        ticker="BZ=F",
        action="BUY",
        size_pct_nav=2.0,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
        rationale="add 1",
        signal_source="test",
    )
    ok, msg, ids1 = sim.execute_intent(port, o1, prices, trade_date="2026-04-01")
    assert ok, msg
    leg1 = port.find_open_position("BZ=F", long_side=True)
    assert leg1 is not None
    q1 = leg1.quantity
    o2 = OrderIntent(
        ticker="BZ=F",
        action="BUY",
        size_pct_nav=2.0,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
        rationale="add 2",
        signal_source="test",
    )
    ok2, msg2, ids2 = sim.execute_intent(port, o2, prices, trade_date="2026-04-01")
    assert ok2, msg2
    open_bz = [p for p in port.get_open_positions() if p.ticker == "BZ=F"]
    assert len(open_bz) == 1
    assert ids2 == ids1
    assert open_bz[0].quantity > q1 + 1e-6


def test_min_hold_same_session_day_blocks_close(tmp_db):
    port = Portfolio()
    port.load_state()
    prices = {"ES=F": 5000.0}
    sim = PaperSimulator()
    ok, msg, ids = sim.execute_intent(
        port,
        OrderIntent(
            ticker="ES=F",
            action="BUY",
            size_pct_nav=2.0,
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            rationale="open",
            signal_source="test",
        ),
        prices,
        trade_date="2026-04-01",
    )
    assert ok, msg
    op = port.find_open_position("ES=F", long_side=True)
    assert op is not None and op.id is not None
    with pytest.raises(ValueError, match="Min hold"):
        port.close_position(
            op.id,
            4900.0,
            "2026-04-01",
            exit_reason="test",
        )


def test_etf_round_trip_cash_not_destroyed(tmp_db):
    """Long ETF open debits full notional; close must credit proceeds (not P&L only)."""
    port = Portfolio()
    port.load_state()
    c0 = port.get_cash()
    sim = PaperSimulator()
    prices = {"GLD": 200.0}
    ok, msg, _ = sim.execute_intent(
        port,
        OrderIntent(
            ticker="GLD",
            action="BUY",
            size_pct_nav=1.0,
            stop_loss_pct=5.0,
            take_profit_pct=10.0,
            rationale="open",
            signal_source="test",
        ),
        prices,
        trade_date="2026-03-28",
    )
    assert ok, msg
    assert port.find_open_position("GLD", long_side=True) is not None

    ok2, msg2, _ = sim.execute_intent(
        port,
        OrderIntent(
            ticker="GLD",
            action="SELL",
            size_pct_nav=1.0,
            stop_loss_pct=1.0,
            take_profit_pct=2.0,
            rationale="close",
            signal_source="test",
        ),
        prices,
        trade_date="2026-03-29",
    )
    assert ok2, msg2
    assert port.find_open_position("GLD", long_side=True) is None
    c1 = port.get_cash()
    assert c1 > c0 * 0.99, f"cash impaired vs start: {c0} -> {c1}"
    assert c1 <= c0 + 500.0


def test_reject_oversize(monkeypatch, tmp_path):
    db = tmp_path / "u.db"
    monkeypatch.setattr(portfolio_mod, "_db_path", lambda: db)
    port = Portfolio()
    port.load_state()
    sim = PaperSimulator()
    ok, msg, _ = sim.execute_intent(
        port,
        OrderIntent(
            ticker="ES=F",
            action="BUY",
            size_pct_nav=80.0,
            stop_loss_pct=1.0,
            take_profit_pct=2.0,
            rationale="too big",
        ),
        {"ES=F": 5000.0},
        trade_date="2026-03-28",
    )
    assert not ok
    assert "20%" in msg or "NAV" in msg
