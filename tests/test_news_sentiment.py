"""News + VADER (skipped without API key)."""

import os

import pytest

from src.data import news_sentiment


@pytest.mark.skipif(not os.environ.get("FINNHUB_API_KEY"), reason="FINNHUB_API_KEY not set")
def test_fetch_news_sentiment_smoke():
    out = news_sentiment.fetch_news_sentiment()
    for k in ("equities", "bonds", "commodities", "overall"):
        assert k in out["aggregate_sentiment"]
        assert -1.0 <= out["aggregate_sentiment"][k] <= 1.0


def test_bucket_tags():
    tags = news_sentiment._bucket_for("Oil prices surge on OPEC cut")
    assert "commodities" in tags
