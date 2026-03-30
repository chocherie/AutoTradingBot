"""Minimum calendar hold before exits."""

from src.portfolio.hold_rules import min_hold_calendar_days, min_hold_exit_blocked


def test_min_hold_blocks_same_day():
    settings = {
        "portfolio": {"min_hold_calendar_days": 1},
        "schedule": {"timezone": "America/New_York"},
    }
    msg = min_hold_exit_blocked("2026-03-30", "2026-03-30", settings)
    assert msg is not None
    assert "Min hold" in msg


def test_min_hold_allows_next_calendar_day():
    settings = {
        "portfolio": {"min_hold_calendar_days": 1},
        "schedule": {"timezone": "America/New_York"},
    }
    assert min_hold_exit_blocked("2026-03-30", "2026-03-31", settings) is None


def test_min_hold_disabled():
    settings = {
        "portfolio": {"min_hold_calendar_days": 0},
        "schedule": {},
    }
    assert min_hold_exit_blocked("2026-03-30", "2026-03-30", settings) is None


def test_min_hold_default_from_settings_shape():
    assert min_hold_calendar_days({"portfolio": {}}) == 1
