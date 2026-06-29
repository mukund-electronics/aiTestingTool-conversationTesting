"""JSONPath-based extraction of fields from endpoint responses."""

from __future__ import annotations

from typing import Any

from jsonpath_ng.ext import parse as jsonpath_parse


def extract_fields(response: Any, extractors: dict[str, str]) -> dict[str, Any]:
    """Apply each JSONPath expression to ``response`` and return a dict of
    extracted values.

    - If the path matches a single value, store that value directly.
    - If multiple matches, store a list.
    - If no match, the key is omitted from the returned dict.
    - Invalid JSONPath expressions are caught and skipped; the offending
      key gets a ``None`` value so callers can surface the failure to users.
    """
    out: dict[str, Any] = {}
    for name, path in extractors.items():
        try:
            expr = jsonpath_parse(path)
        except Exception:
            out[name] = None
            continue
        matches = [m.value for m in expr.find(response)]
        if not matches:
            continue
        out[name] = matches[0] if len(matches) == 1 else matches
    return out


def is_truthy_end_flag(value: Any) -> bool:
    """Treat the extracted ``end_flag`` permissively: True, "true", "yes",
    "1", 1 all count as the endpoint signaling the end of the conversation."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "done", "end"}
    return bool(value)
