from backend.services.extractor import extract_fields, is_truthy_end_flag


def test_simple_path():
    response = {"data": {"message": "hello"}}
    extracted = extract_fields(response, {"reply": "$.data.message"})
    assert extracted == {"reply": "hello"}


def test_multiple_extractors():
    response = {
        "data": {"message": "hi"},
        "session_id": "abc",
        "is_final": True,
    }
    out = extract_fields(
        response,
        {
            "reply": "$.data.message",
            "session_id": "$.session_id",
            "end_flag": "$.is_final",
        },
    )
    assert out == {"reply": "hi", "session_id": "abc", "end_flag": True}


def test_missing_path_omitted():
    response = {"data": {"message": "hi"}}
    out = extract_fields(response, {"reply": "$.data.message", "missing": "$.does.not.exist"})
    assert out == {"reply": "hi"}
    assert "missing" not in out


def test_invalid_path_marked_none():
    response = {"data": {"message": "hi"}}
    out = extract_fields(response, {"bad": "$$$invalid$$$"})
    assert out["bad"] is None


def test_multiple_matches_returned_as_list():
    response = {"items": [{"v": 1}, {"v": 2}, {"v": 3}]}
    out = extract_fields(response, {"vals": "$.items[*].v"})
    assert out == {"vals": [1, 2, 3]}


def test_end_flag_truthiness():
    assert is_truthy_end_flag(True) is True
    assert is_truthy_end_flag(False) is False
    assert is_truthy_end_flag("true") is True
    assert is_truthy_end_flag("YES") is True
    assert is_truthy_end_flag("1") is True
    assert is_truthy_end_flag(1) is True
    assert is_truthy_end_flag(0) is False
    assert is_truthy_end_flag("") is False
    assert is_truthy_end_flag(None) is False
    assert is_truthy_end_flag("nope") is False
