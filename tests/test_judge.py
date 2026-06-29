import json

import pytest

from backend.services.judge import (
    _build_criteria_section,
    _compute_weighted_score,
    parse_turn_verdict_text,
    parse_verdict_text,
)


def test_bare_json():
    text = '{"result": "pass", "reasoning": "All good.", "score": 0.9}'
    v = parse_verdict_text(text)
    assert v.result == "pass"
    assert v.reasoning == "All good."
    assert v.score == 0.9


def test_json_with_markdown_fence():
    text = '```json\n{"result": "fail", "reasoning": "Missed step.", "score": 0.2}\n```'
    v = parse_verdict_text(text)
    assert v.result == "fail"
    assert v.score == 0.2


def test_json_with_prose_around():
    text = (
        "Here's my verdict:\n"
        '{"result": "inconclusive", "reasoning": "Need more data.", "score": 0.5}\n'
        "Thanks!"
    )
    v = parse_verdict_text(text)
    assert v.result == "inconclusive"


def test_score_clamped():
    text = '{"result": "pass", "reasoning": "x", "score": 1.5}'
    v = parse_verdict_text(text)
    assert v.score == 1.0

    text = '{"result": "fail", "reasoning": "x", "score": -1.0}'
    v = parse_verdict_text(text)
    assert v.score == 0.0


def test_non_numeric_score_defaults_to_zero():
    text = '{"result": "pass", "reasoning": "x", "score": "high"}'
    v = parse_verdict_text(text)
    assert v.score == 0.0


def test_result_normalized_case():
    text = '{"result": "PASS", "reasoning": "x", "score": 0.5}'
    v = parse_verdict_text(text)
    assert v.result == "pass"


def test_invalid_result_raises():
    text = '{"result": "maybe", "reasoning": "x", "score": 0.5}'
    with pytest.raises(ValueError):
        parse_verdict_text(text)


def test_no_json_at_all_raises():
    with pytest.raises(ValueError):
        parse_verdict_text("complete nonsense")


def test_empty_string_raises():
    with pytest.raises(ValueError):
        parse_verdict_text("")


# ── Multi-criteria tests ───────────────────────────────────────────────────────

_CRITERIA = [
    {"name": "Answers question", "description": "Bot answers directly", "weight": 0.5},
    {"name": "No deflection", "description": "No support-ticket redirect", "weight": 0.5},
]


def test_parse_turn_with_criteria():
    text = json.dumps({
        "verdict": "fail",
        "need_satisfied": False,
        "reasoning": "Bot deflected.",
        "issues": ["redirected"],
        "strengths": [],
        "suggestion": "Answer directly.",
        "criteria": {
            "Answers question": {"score": 0.8, "reasoning": "Partially answered."},
            "No deflection": {"score": 0.1, "reasoning": "Redirected to support ticket."},
        },
    })
    v = parse_turn_verdict_text(text, eval_criteria=_CRITERIA)
    assert v.result == "fail"
    assert v.criteria_scores["Answers question"]["score"] == 0.8
    assert v.criteria_scores["No deflection"]["score"] == 0.1
    # weighted average: (0.8*0.5 + 0.1*0.5) / 1.0 = 0.45
    assert abs(v.score - 0.45) < 1e-9


def test_weighted_average_normalization():
    # weights don't sum to 1 — should normalize correctly
    criteria = [
        {"name": "A", "description": "", "weight": 4.0},
        {"name": "B", "description": "", "weight": 6.0},
    ]
    scores = {"A": {"score": 1.0, "reasoning": ""}, "B": {"score": 0.0, "reasoning": ""}}
    result = _compute_weighted_score(scores, criteria)
    # expected: (1.0*4 + 0.0*6) / 10 = 0.4
    assert abs(result - 0.4) < 1e-9


def test_missing_criterion_defaults_to_zero():
    text = json.dumps({
        "verdict": "pass",
        "need_satisfied": True,
        "reasoning": "ok",
        "issues": [],
        "strengths": [],
        "suggestion": "None",
        "criteria": {
            "Answers question": {"score": 1.0, "reasoning": "Perfect answer."},
            # "No deflection" intentionally omitted
        },
    })
    v = parse_turn_verdict_text(text, eval_criteria=_CRITERIA)
    assert v.criteria_scores["No deflection"]["score"] == 0.0
    assert v.criteria_scores["No deflection"]["reasoning"] == "(not scored)"
    # weighted average: (1.0*0.5 + 0.0*0.5) / 1.0 = 0.5
    assert abs(v.score - 0.5) < 1e-9


def test_no_criteria_uses_score_field():
    text = '{"verdict": "pass", "reasoning": "Good.", "score": 0.75, "need_satisfied": true, "issues": [], "strengths": [], "suggestion": "None"}'
    v = parse_turn_verdict_text(text, eval_criteria=None)
    assert v.score == 0.75
    assert v.criteria_scores == {}


def test_parse_transcript_verdict_with_criteria():
    text = json.dumps({
        "result": "pass",
        "reasoning": "Overall good.",
        "criteria": {
            "Answers question": {"score": 0.9, "reasoning": "Answered well."},
            "No deflection": {"score": 0.8, "reasoning": "Stayed on topic."},
        },
    })
    v = parse_verdict_text(text, eval_criteria=_CRITERIA)
    assert v.result == "pass"
    assert v.criteria_scores["Answers question"]["score"] == 0.9
    # weighted average: (0.9*0.5 + 0.8*0.5) / 1.0 = 0.85
    assert abs(v.score - 0.85) < 1e-9


def test_build_criteria_section_format():
    output = _build_criteria_section(_CRITERIA)
    assert "Answers question" in output
    assert "No deflection" in output
    assert "0.50" in output  # weight formatted
    assert "Bot answers directly" in output


def test_compute_weighted_score():
    criteria = [
        {"name": "X", "description": "", "weight": 0.6},
        {"name": "Y", "description": "", "weight": 0.4},
    ]
    # basic
    scores = {"X": {"score": 1.0, "reasoning": ""}, "Y": {"score": 0.5, "reasoning": ""}}
    assert abs(_compute_weighted_score(scores, criteria) - 0.8) < 1e-9

    # all zero
    scores_zero = {"X": {"score": 0.0, "reasoning": ""}, "Y": {"score": 0.0, "reasoning": ""}}
    assert _compute_weighted_score(scores_zero, criteria) == 0.0

    # empty scores dict
    assert _compute_weighted_score({}, criteria) == 0.0
