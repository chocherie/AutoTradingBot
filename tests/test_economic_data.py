"""FRED integration (skipped without API key)."""

import os

import pytest

from src.data import economic_data


@pytest.mark.skipif(not os.environ.get("FRED_API_KEY"), reason="FRED_API_KEY not set")
def test_fetch_economic_snapshot_smoke():
    out = economic_data.fetch_economic_snapshot()
    assert "series" in out
    assert "DGS10" in out["series"]
    assert "latest" in out["series"]["DGS10"]
