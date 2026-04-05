"""Claude JSON parsing."""

from src.brain.response_parser import parse_claude_response


def test_parse_valid_json():
    text = """
Here is the decision:
```json
{
  "market_regime": "RISK_ON",
  "macro_summary": "Test macro",
  "orders": [],
  "positions_to_close": [],
  "risk_notes": "none"
}
```
"""
    dec, err = parse_claude_response(text)
    assert err is None
    assert dec is not None
    assert dec.market_regime == "RISK_ON"
    assert dec.orders == []


def test_parse_raw_object():
    raw = '{"market_regime":"TRANSITIONAL","macro_summary":"x","orders":[],"positions_to_close":[],"risk_notes":""}'
    dec, err = parse_claude_response(raw)
    assert err is None and dec is not None
    assert dec.daily_findings == ""


def test_parse_daily_findings():
    raw = (
        '{"market_regime":"RISK_ON","macro_summary":"m","daily_findings":"Line1\\nLine2",'
        '"orders":[],"positions_to_close":[],"risk_notes":""}'
    )
    dec, err = parse_claude_response(raw)
    assert err is None and dec is not None
    assert dec.daily_findings == "Line1\nLine2"
