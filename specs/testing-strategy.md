# Testing Strategy

**Status**: Draft | **Updated**: 2026-03-28

## Approach
Unit tests per module + one integration test for the full daily cycle.

## Test Coverage

### Data Pipeline
- `test_market_data.py`: Fetch prices for 3 tickers, verify OHLCV structure, verify technical calculations
- `test_economic_data.py`: Fetch 3 FRED series, verify values are numeric
- `test_news_sentiment.py`: Fetch news, verify VADER scores in [-1, 1]
- `test_data_cache.py`: Write/read/expire cycle

### Portfolio Engine
- `test_position.py`: Create futures, options, ETF positions; verify P&L calculation
- `test_portfolio.py`: Add/close positions, verify NAV, margin, cash accounting
- `test_margin.py`: Verify margin calculation for each instrument type

### Execution
- `test_simulator.py`: Fill order, verify slippage applied, commission charged
- `test_order.py`: Order validation (valid/invalid tickers, sizes)

### Claude Brain
- `test_prompt_builder.py`: Build prompt from mock data, verify structure, check token count
- `test_response_parser.py`: Parse valid JSON, handle malformed JSON, validate Pydantic models

### Integration
- `test_daily_cycle.py`: Full pipeline with real APIs (market + FRED + Claude), verify DB writes

## Running Tests
```bash
pytest tests/ -v
pytest tests/test_market_data.py -v  # single module
```
