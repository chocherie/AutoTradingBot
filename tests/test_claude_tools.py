"""Claude tool helpers."""

import pytest

from src.brain.claude_tools import safe_calculator_eval


def test_safe_calculator_basic():
    assert safe_calculator_eval("2 + 3 * 4") == 14.0
    assert safe_calculator_eval("(1_000_000 * 0.05) / 100") == 500.0


def test_safe_calculator_rejects_names():
    with pytest.raises(ValueError):
        safe_calculator_eval("nav * 2")


def test_safe_calculator_empty():
    with pytest.raises(ValueError):
        safe_calculator_eval("")
