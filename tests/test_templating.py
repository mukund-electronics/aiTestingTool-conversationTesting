import json

import pytest

from backend.services.templating import build_variables, render_template


def test_simple_user_query_substitution():
    template = '{"message": "{{user_query}}"}'
    out = render_template(template, build_variables("hello", "", [], 1))
    assert out == {"message": "hello"}


def test_user_query_with_quotes_and_newlines():
    template = '{"message": "{{user_query}}"}'
    user_query = 'she said "hi"\nthen left'
    out = render_template(template, build_variables(user_query, "", [], 1))
    assert out == {"message": user_query}


def test_session_id_empty_on_turn_one():
    template = '{"msg": "{{user_query}}", "session_id": "{{session_id}}"}'
    out = render_template(template, build_variables("hi", "", [], 1))
    assert out == {"msg": "hi", "session_id": ""}


def test_session_id_populated_later():
    template = '{"msg": "{{user_query}}", "session_id": "{{session_id}}"}'
    out = render_template(template, build_variables("hi", "abc-123", [], 2))
    assert out == {"msg": "hi", "session_id": "abc-123"}


def test_history_substituted_as_json_array():
    template = '{"history": {{history}}, "msg": "{{user_query}}"}'
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    out = render_template(template, build_variables("how are you?", "", history, 2))
    assert out["history"] == history
    assert out["msg"] == "how are you?"


def test_turn_number_substituted_as_int():
    template = '{"n": {{turn_number}}}'
    out = render_template(template, build_variables("x", "", [], 5))
    assert out == {"n": 5}


def test_unknown_placeholder_renders_empty():
    template = '{"msg": "{{user_query}}", "extra": "{{nope}}"}'
    out = render_template(template, build_variables("hi", "", [], 1))
    assert out == {"msg": "hi", "extra": ""}


def test_template_invalid_after_render_raises():
    # If user provides broken JSON, we surface it cleanly.
    template = '{"msg": "{{user_query}}"'  # missing closing brace
    with pytest.raises(ValueError):
        render_template(template, build_variables("hi", "", [], 1))


def test_nested_template():
    template = json.dumps(
        {
            "data": {
                "input": "{{user_query}}",
                "session": "{{session_id}}",
                "meta": {"turn": "placeholder"},
            }
        }
    ).replace('"placeholder"', "{{turn_number}}")
    out = render_template(template, build_variables("ping", "S1", [], 3))
    assert out == {"data": {"input": "ping", "session": "S1", "meta": {"turn": 3}}}
