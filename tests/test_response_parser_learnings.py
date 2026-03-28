"""Claude decision session_learnings field."""

import json

from src.brain.response_parser import ClaudeDecision


def test_session_learnings_coerce_string():
    raw = {
        "market_regime": "RISK_ON",
        "macro_summary": "x",
        "orders": [],
        "positions_to_close": [],
        "risk_notes": "",
        "session_learnings": "single string",
    }
    d = ClaudeDecision.model_validate(raw)
    assert d.session_learnings == ["single string"]


def test_session_learnings_list():
    blob = json.dumps(
        {
            "market_regime": "RISK_ON",
            "macro_summary": "x",
            "orders": [],
            "positions_to_close": [],
            "risk_notes": "",
            "session_learnings": ["a", "b"],
        }
    )
    d = ClaudeDecision.model_validate_json(blob)
    assert d.session_learnings == ["a", "b"]
