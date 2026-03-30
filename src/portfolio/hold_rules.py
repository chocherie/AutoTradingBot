"""Calendar minimum-hold rules (session dates vs schedule timezone calendar)."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional


def min_hold_calendar_days(settings: Dict[str, Any]) -> int:
    """0 = disabled. Default 1 when key omitted."""
    raw = settings.get("portfolio", {}).get("min_hold_calendar_days", 1)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 1


def min_hold_exit_blocked(
    entry_date: str,
    exit_date: str,
    settings: Dict[str, Any],
) -> Optional[str]:
    """
    If closing violates min hold, return human-readable reason; else None.
    Compares YYYY-MM-DD calendar dates (session dates — align runs with schedule.timezone).
    """
    mc = min_hold_calendar_days(settings)
    if mc <= 0:
        return None
    try:
        ed = date.fromisoformat(str(entry_date)[:10])
        xd = date.fromisoformat(str(exit_date)[:10])
    except ValueError:
        return None
    if (xd - ed).days < mc:
        tz = str(settings.get("schedule", {}).get("timezone", "America/New_York"))
        return (
            f"Min hold {mc} calendar day(s) in session calendar (ref TZ {tz}); "
            f"opened {ed.isoformat()}, cannot close on {xd.isoformat()}"
        )
    return None
