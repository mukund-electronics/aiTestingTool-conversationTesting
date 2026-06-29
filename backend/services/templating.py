"""Render request body templates.

The request_body_template is a JSON string that may contain ``{{variable}}``
placeholders inside string values. We substitute placeholders FIRST as text
(treating the template as raw text), then JSON-parse the result so the final
payload is well-formed.

This mirrors the behavior described in the spec: "Templating happens AFTER
JSON parsing of the template, so placeholders work inside string values." We
achieve the same observable result by using a stricter sequence (substitute
text → parse JSON) which is more robust for arbitrary nested structures.

Supported variables:
    - {{user_query}}    -> current user message (string)
    - {{session_id}}    -> string, empty on turn 1
    - {{history}}       -> JSON-serialized OpenAI-style messages array
    - {{turn_number}}   -> integer

Each variable is JSON-encoded when substituted (so quotes/newlines are safe),
but the surrounding quotes are stripped for string substitution into already
quoted positions in the template. The substitution helper handles both
"naked" placeholders (e.g. value of an array field) and "in-string"
placeholders (inside an existing JSON string).
"""

from __future__ import annotations

import json
import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _to_json_fragment(value: Any) -> str:
    """JSON-encode a value (including surrounding quotes for strings)."""
    return json.dumps(value, ensure_ascii=False)


def _to_str_fragment(value: Any) -> str:
    """Convert to a string suitable for substitution inside an existing
    quoted JSON string. Strings are unquoted-escaped; non-strings are
    JSON-stringified then escaped."""
    if isinstance(value, str):
        s = value
    else:
        s = json.dumps(value, ensure_ascii=False)
    # Escape characters that would break the surrounding JSON string.
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def render_template(template: str, variables: dict[str, Any]) -> Any:
    """Render template and return the parsed JSON object.

    Strategy: for each placeholder, decide whether it sits inside a JSON
    string literal (between matching double quotes) or at a "naked" JSON
    value position. In the former case substitute an escaped string
    fragment; in the latter, substitute a full JSON fragment.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            # Leave unknown placeholders empty rather than raising; the
            # caller can validate templates separately.
            return ""
        value = variables[name]
        start = match.start()
        # Heuristic: count unescaped double quotes BEFORE this position. If
        # odd, we're inside a JSON string literal; substitute escaped text.
        # If even, we're at a naked value position; substitute a JSON
        # fragment (so e.g. history -> [...] inline).
        prefix = template[:start]
        # Strip escaped quotes to avoid miscounting.
        unescaped = re.sub(r"\\.", "", prefix)
        quote_count = unescaped.count('"')
        if quote_count % 2 == 1:
            return _to_str_fragment(value)
        return _to_json_fragment(value)

    rendered = _PLACEHOLDER.sub(replace, template)
    try:
        return json.loads(rendered)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Rendered template is not valid JSON: {e.msg}. Rendered text:\n{rendered}"
        ) from e


def build_variables(
    user_query: str,
    session_id: str,
    history: list[dict[str, str]],
    turn_number: int,
) -> dict[str, Any]:
    return {
        "user_query": user_query,
        "session_id": session_id or "",
        "history": history,
        "turn_number": turn_number,
    }
