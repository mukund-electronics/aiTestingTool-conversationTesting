"""cURL command parser and related helpers."""

from __future__ import annotations

import json
import re


def _shell_split(text: str) -> list[str]:
    """Tokenise a shell command line, respecting single/double quotes and backslash escapes."""
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in (" ", "\t"):
            i += 1
        if i >= n:
            break
        tok: list[str] = []
        while i < n and text[i] not in (" ", "\t"):
            c = text[i]
            if c in ('"', "'"):
                q = c
                i += 1
                while i < n and text[i] != q:
                    if text[i] == "\\" and q == '"':
                        i += 1
                        if i < n:
                            tok.append(text[i])
                    else:
                        tok.append(text[i])
                    i += 1
                i += 1
            elif c == "\\":
                i += 1
                if i < n:
                    tok.append(text[i])
                    i += 1
            else:
                tok.append(c)
                i += 1
        if tok:
            tokens.append("".join(tok))
    return tokens


_QUERY_FIELD_NAMES = {
    "message", "query", "text", "input", "prompt", "question",
    "content", "msg", "user_message", "user_query", "utterance",
    "request", "q", "ask",
}


def _is_query_field(key: str) -> bool:
    """True if any word in a snake_case or camelCase field name is a known query-field word."""
    words = set(re.sub(r"([a-z])([A-Z])", r"\1_\2", key).lower().split("_"))
    return bool(words & _QUERY_FIELD_NAMES)


def _inject_user_query_placeholder(body: str) -> tuple[str, str | None]:
    """Try to replace the most likely user-message field with {{user_query}}.

    Returns (modified_body, detected_field_name | None).
    """
    try:
        obj = json.loads(body)
        if not isinstance(obj, dict):
            return body, None
        for key in obj:
            if _is_query_field(key):
                obj[key] = "{{user_query}}"
                return json.dumps(obj, indent=2), key
    except Exception:
        pass
    return body, None


def _parse_curl(text: str) -> dict:
    """Parse a cURL command into endpoint config field values."""
    import base64 as _b64
    import re as _re

    text = _re.sub(r"\\\s*\n\s*", " ", text.strip())
    tokens = _shell_split(text)

    result: dict = {
        "url": "", "http_method": "POST",
        "headers": {}, "request_body": "",
        "auth_type": "none", "auth_value": "",
        "protocol": "http",
    }

    i = 0
    if tokens and tokens[0].lower() == "curl":
        i = 1

    while i < len(tokens):
        t = tokens[i]

        if t in ("-X", "--request") and i + 1 < len(tokens):
            i += 1; result["http_method"] = tokens[i].upper()
        elif t.startswith("-X") and len(t) > 2:
            result["http_method"] = t[2:].upper()
        elif t in ("-H", "--header") and i + 1 < len(tokens):
            i += 1
            k, _, v = tokens[i].partition(":")
            result["headers"][k.strip()] = v.strip()
        elif t in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii") and i + 1 < len(tokens):
            i += 1
            result["request_body"] = tokens[i]
            if result["http_method"] == "GET":
                result["http_method"] = "POST"
        elif t in ("-u", "--user") and i + 1 < len(tokens):
            i += 1
            result["auth_type"] = "basic"
            result["auth_value"] = tokens[i]
        elif t == "--url" and i + 1 < len(tokens):
            i += 1; result["url"] = tokens[i]
        elif t == "--ws" and i + 1 < len(tokens):
            i += 1
            result["url"] = tokens[i].strip("'\"")
            result["protocol"] = "websocket"
        elif t == "<<<" and i + 1 < len(tokens):
            i += 1
            result["request_body"] = tokens[i]
        elif not t.startswith("-") and t != "<<<" and not result["url"]:
            result["url"] = t.strip("'\"")

        i += 1

    # Lift auth out of headers
    for hname in list(result["headers"]):
        if hname.lower() == "authorization":
            v = result["headers"].pop(hname)
            if v.lower().startswith("bearer "):
                result["auth_type"] = "bearer"
                result["auth_value"] = v[7:].strip()
            elif v.lower().startswith("basic "):
                result["auth_type"] = "basic"
                try:
                    result["auth_value"] = _b64.b64decode(v[6:].strip()).decode()
                except Exception:
                    result["auth_value"] = v[6:].strip()
            break

    # Lift common API-key headers
    if result["auth_type"] == "none":
        for hname in list(result["headers"]):
            if hname.lower() in ("x-api-key", "api-key", "apikey", "x-auth-token", "x-access-token"):
                result["auth_type"] = "api_key"
                result["auth_value"] = result["headers"].pop(hname)
                break

    # Drop Content-Type — it's implicit
    for hname in list(result["headers"]):
        if hname.lower() == "content-type":
            del result["headers"][hname]

    return result
