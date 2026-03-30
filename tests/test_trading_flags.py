"""Feature flags in settings (e.g. options_enabled)."""

from pathlib import Path

import pytest

from src.execution.order import OrderIntent
from src.portfolio import portfolio as portfolio_mod
from src.portfolio.portfolio import Portfolio
from src.portfolio.risk import validate_order


@pytest.fixture
def tmp_db(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    monkeypatch.setattr(portfolio_mod, "_db_path", lambda: db)


def test_options_disabled_rejects_option_order(tmp_db):
    port = Portfolio()
    port.load_state()
    prices = {"SPY": 500.0}
    od = {"strike": 500.0, "expiry": "2026-06-20", "option_type": "CALL", "premium": 5.0}
    order = OrderIntent(
        ticker="SPY",
        action="BUY",
        size_pct_nav=2.0,
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        rationale="test",
        option_details=od,
    )
    settings = {"trading": {"options_enabled": False}, "risk": {}}
    ok, msg = validate_order(order, port, prices, settings=settings)
    assert not ok
    assert "disabled" in msg.lower()


def test_options_enabled_allows_validation_to_continue(tmp_db):
    port = Portfolio()
    port.load_state()
    prices = {"SPY": 500.0}
    od = {"strike": 500.0, "expiry": "2026-06-20", "option_type": "CALL", "premium": 5.0}
    order = OrderIntent(
        ticker="SPY",
        action="BUY",
        size_pct_nav=2.0,
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        rationale="test",
        option_details=od,
    )
    settings = {"trading": {"options_enabled": True}, "risk": {}}
    ok, msg = validate_order(order, port, prices, settings=settings)
    assert ok or "Options" not in (msg or "")


def test_system_prompt_switches_when_options_off():
    from src.brain.claude_client import system_prompt_for_settings

    assert "options are OFF" in system_prompt_for_settings(
        {"trading": {"options_enabled": False}}
    )
    assert "equity index futures" in system_prompt_for_settings(
        {"trading": {"options_enabled": True}}
    )
