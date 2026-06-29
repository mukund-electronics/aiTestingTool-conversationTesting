"""Generates a self-contained dark-theme HTML export of a test run."""
from __future__ import annotations

from typing import Any

_VERDICT_BG   = {"pass": "#0D1F12", "fail": "#1F0D0D", "inconclusive": "#1F1A0D"}
_VERDICT_FG   = {"pass": "#22C55E", "fail": "#EF4444", "inconclusive": "#F59E0B"}
_VERDICT_DOT  = {"pass": "#22C55E", "fail": "#EF4444", "inconclusive": "#F59E0B"}
_VERDICT_ICON = {"pass": "✓", "fail": "✕", "inconclusive": "?"}

_STATUS_FG = {
    "running":   "#60A5FA",
    "completed": "#22C55E",
    "failed":    "#EF4444",
    "stopped":   "#F59E0B",
}
_STATUS_BG = {
    "running":   "#1C2030",
    "completed": "#0D1F12",
    "failed":    "#1F0D0D",
    "stopped":   "#1F1A0D",
}

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;600;700&display=swap');

:root {
    --ct-content-font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background: #0D0D0D;
    color: #E8E8E8;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', ui-monospace, monospace;
    font-size: 14px;
    line-height: 1.5;
    padding: 24px;
    max-width: 1200px;
    margin: 0 auto;
}

h1 {
    font-size: 1.4rem;
    font-weight: 700;
    color: #FFFFFF;
    margin-bottom: 6px;
}
h1::before { content: "> "; color: #E87D0D; }

h2 {
    font-size: 0.85rem;
    font-weight: 700;
    color: #E87D0D;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 24px 0 10px;
}

table { border-collapse: collapse; width: 100%; }

ul { list-style: disc; }

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0D0D0D; }
::-webkit-scrollbar-thumb { background: #2A2A2A; border-radius: 3px; }
"""


def _h(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")


def _score_bar(score: float | None) -> str:
    if score is None:
        return ""
    pct = round((score or 0) * 100)
    color = "#22C55E" if pct >= 70 else "#F59E0B" if pct >= 40 else "#EF4444"
    return (
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<div style="flex:1;height:4px;background:#2A2A2A;border-radius:2px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;width:{pct}%;'
        f'background:{color};border-radius:2px;"></div>'
        f'</div>'
        f'<span style="font-size:0.78rem;font-weight:600;color:{color};min-width:32px;">'
        f'{score:.2f}</span>'
        f'</div>'
    )


def _score_bar_threshold(score: float | None, threshold: float = 0.7) -> str:
    if score is None:
        return '<span style="color:#666666">—</span>'
    pct = round((score or 0) * 100)
    tpct = round(threshold * 100)
    color = "#22C55E" if (score or 0) >= threshold else "#EF4444"
    return (
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<div style="flex:1;height:6px;background:#2A2A2A;border-radius:3px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;width:{pct}%;'
        f'background:{color};border-radius:3px;"></div>'
        f'<div style="position:absolute;left:{tpct}%;top:-3px;width:2px;height:12px;'
        f'background:#888888;border-radius:1px;"></div>'
        f'</div>'
        f'<span style="font-size:0.78rem;font-weight:600;color:{color};min-width:32px;">'
        f'{score:.2f}</span>'
        f'</div>'
    )


def _verdict_pill(verdict: str) -> str:
    bg  = _VERDICT_BG.get(verdict, "#1A1A1A")
    fg  = _VERDICT_FG.get(verdict, "#E8E8E8")
    dot = _VERDICT_DOT.get(verdict, "#888888")
    ico = _VERDICT_ICON.get(verdict, "•")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'padding:2px 9px;border-radius:3px;background:{bg};'
        f'color:{fg};font-size:0.76rem;font-weight:600;letter-spacing:0.05em;">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{dot};"></span>'
        f'{ico} {verdict.upper()}'
        f'</span>'
    )


def _render_endpoint_details(ep: Any, session_id: str = "") -> str:
    """Render a developer-facing API request details panel at the top of the export."""
    if ep is None:
        return ""

    import json as _json

    raw_template = ep.request_body_template or ""
    # Substitute the actual session_id so the developer sees what was sent,
    # not the raw {{session_id}} placeholder.
    if session_id:
        raw_template = raw_template.replace("{{session_id}}", session_id)
    try:
        body_obj = _json.loads(raw_template)
        body_pretty = _json.dumps(body_obj, indent=2)
    except Exception:
        body_pretty = raw_template

    _SENSITIVE_KEYS = {"authorization", "x-api-key", "api-key", "api_key", "token", "secret",
                       "x-auth-token", "x-access-token", "x-secret-key"}
    headers_display: dict = {}
    for k, v in (ep.headers or {}).items():
        headers_display[k] = "[hidden]" if k.lower() in _SENSITIVE_KEYS else v

    method_color = {
        "POST":   "#60A5FA",
        "GET":    "#22C55E",
        "PUT":    "#F59E0B",
        "PATCH":  "#A78BFA",
        "DELETE": "#EF4444",
    }.get((ep.http_method or "").upper(), "#E8E8E8")

    protocol_badge = (
        f'<span style="padding:1px 7px;border-radius:3px;background:#1A1A1A;'
        f'border:1px solid #3A3A3A;font-size:0.72rem;font-weight:700;'
        f'color:#A78BFA;letter-spacing:0.06em;">'
        f'{_h((ep.protocol or "http").upper())}</span>'
    )
    method_badge = (
        f'<span style="padding:1px 7px;border-radius:3px;background:#1A1A1A;'
        f'border:1px solid #3A3A3A;font-size:0.72rem;font-weight:700;'
        f'color:{method_color};letter-spacing:0.06em;">'
        f'{_h((ep.http_method or "POST").upper())}</span>'
    )

    url_row = (
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">'
        f'{protocol_badge}{method_badge}'
        f'<span style="font-size:0.97rem;font-weight:700;color:#FFFFFF;'
        f'word-break:break-all;flex:1;">{_h(ep.url or "—")}</span>'
        f'</div>'
    )

    rows: list[str] = []

    def _kv_row(label: str, value: str, value_color: str = "#CCCCCC",
                mono: bool = False) -> str:
        font_style = "font-family:inherit;" if not mono else ""
        return (
            f'<tr style="border-bottom:1px solid #1E1E1E;">'
            f'<td style="padding:5px 14px 5px 0;font-size:0.72rem;font-weight:700;'
            f'color:#666666;text-transform:uppercase;letter-spacing:0.08em;'
            f'white-space:nowrap;vertical-align:top;width:140px;">{_h(label)}</td>'
            f'<td style="padding:5px 0;font-size:0.83rem;{font_style}'
            f'color:{value_color};word-break:break-all;">{value}</td>'
            f'</tr>'
        )

    rows.append(_kv_row("Endpoint Name", _h(ep.name or "—")))
    if session_id:
        rows.append(_kv_row("Session ID", _h(session_id), "#F59E0B"))
    rows.append(_kv_row("Timeout", f"{ep.timeout_seconds}s", "#888888"))
    rows.append(_kv_row("Max Retries", str(ep.max_retries), "#888888"))
    if ep.auth_type and ep.auth_type != "none":
        rows.append(_kv_row("Auth Type", _h(ep.auth_type)))
        rows.append(_kv_row("Auth Value", "[hidden]", "#666666"))

    table_html = (
        f'<table style="width:100%;border-collapse:collapse;margin-bottom:14px;">'
        f'{"".join(rows)}</table>'
    ) if rows else ""

    # Headers
    headers_html = ""
    if headers_display:
        h_rows = ""
        for k, v in headers_display.items():
            v_color = "#666666" if v == "[hidden]" else "#CCCCCC"
            h_rows += (
                f'<tr style="border-bottom:1px solid #1A1A1A;">'
                f'<td style="padding:3px 12px 3px 0;font-size:0.8rem;'
                f'color:#A78BFA;white-space:nowrap;vertical-align:top;">{_h(k)}</td>'
                f'<td style="padding:3px 0;font-size:0.8rem;color:{v_color};'
                f'word-break:break-all;">{_h(str(v))}</td>'
                f'</tr>'
            )
        headers_html = (
            f'<div style="margin-bottom:12px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:#666666;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Headers</div>'
            f'<table style="width:100%;border-collapse:collapse;">{h_rows}</table>'
            f'</div>'
        )

    # Request body template
    body_html = ""
    if body_pretty.strip() and body_pretty.strip() not in ("{}", ""):
        body_html = (
            f'<div style="margin-bottom:12px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:#666666;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">'
            f'Request Body Template</div>'
            f'<div style="background:#0A0A0A;border:1px solid #2A2A2A;border-radius:4px;'
            f'padding:12px 14px;overflow-x:auto;">'
            f'<pre style="margin:0;font-size:0.82rem;color:#4ADE80;'
            f'line-height:1.55;white-space:pre-wrap;word-break:break-all;">'
            f'{_h(body_pretty)}</pre>'
            f'</div></div>'
        )

    # Response extractors
    extractors_html = ""
    extractors = ep.response_extractors or {}
    if extractors:
        ex_rows = ""
        for field, path in extractors.items():
            ex_rows += (
                f'<tr style="border-bottom:1px solid #1A1A1A;">'
                f'<td style="padding:3px 12px 3px 0;font-size:0.8rem;'
                f'color:#F59E0B;white-space:nowrap;">{_h(field)}</td>'
                f'<td style="padding:3px 0;font-size:0.8rem;color:#CCCCCC;">{_h(str(path))}</td>'
                f'</tr>'
            )
        extractors_html = (
            f'<div style="margin-bottom:4px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:#666666;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">'
            f'Response Extractors</div>'
            f'<table style="width:100%;border-collapse:collapse;">{ex_rows}</table>'
            f'</div>'
        )

    return (
        f'<div style="background:#0F1117;border:1px solid #2A2A2A;'
        f'border-left:4px solid #E87D0D;border-radius:6px;'
        f'padding:16px 20px;margin-bottom:18px;">'
        f'<div style="font-size:0.63rem;font-weight:700;color:#E87D0D;'
        f'text-transform:uppercase;letter-spacing:0.12em;margin-bottom:12px;">'
        f'API Request Details</div>'
        f'{url_row}'
        f'{table_html}'
        f'{headers_html}'
        f'{body_html}'
        f'{extractors_html}'
        f'</div>'
    )


def _render_turn_card(t: dict, endpoint_name: str = "Bot") -> str:
    turn_num    = t.get("turn_number", "?")
    user_q      = t.get("user_query") or ""
    reply       = t.get("extracted_reply") or ""
    verdict     = t.get("turn_verdict") or ""
    score       = t.get("turn_score")
    reasoning   = t.get("turn_reasoning") or ""
    analysis    = t.get("turn_analysis") or {}
    error       = t.get("error") or ""
    latency     = t.get("latency_ms") or 0
    status_code = t.get("status_code") or "—"

    _card_failed = verdict == "fail" or bool(error)
    _card_border = "border:2px solid #EF4444;border-left:5px solid #EF4444;" if _card_failed else "border:1px solid #2A2A2A;"
    _card_bg     = "background:#180A0A;" if _card_failed else ""
    _hdr_bg      = "#2D1010" if _card_failed else "#1A1A1A"

    if verdict:
        v_bg  = _VERDICT_BG.get(verdict, "#1A1A1A")
        v_fg  = _VERDICT_FG.get(verdict, "#E8E8E8")
        v_dot = _VERDICT_DOT.get(verdict, "#888888")
        v_ico = _VERDICT_ICON.get(verdict, "•")
        s_str = f"{score:.2f}" if score is not None else "—"
        verdict_badge = (
            f'<span style="display:inline-flex;align-items:center;gap:5px;'
            f'padding:2px 9px;border-radius:3px;background:{v_bg};'
            f'color:{v_fg};font-size:0.72rem;font-weight:700;letter-spacing:0.06em;">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:{v_dot};'
            f'flex-shrink:0;"></span>{v_ico} {verdict.upper()}</span>'
            f'<span style="font-size:0.85rem;font-weight:700;color:{v_fg};margin-left:4px;">'
            f'{s_str}</span>'
        )
    elif score is not None:
        verdict_badge = (
            f'<span style="font-size:0.85rem;font-weight:700;color:#888888;">'
            f'score {score:.2f}</span>'
        )
    else:
        verdict_badge = ""

    header_html = (
        f'<div style="display:flex;align-items:center;gap:10px;padding:8px 14px;'
        f'background:{_hdr_bg};border-bottom:1px solid #2A2A2A;">'
        f'<span style="font-size:0.68rem;font-weight:700;letter-spacing:0.14em;'
        f'color:#E87D0D;min-width:52px;flex-shrink:0;">TURN {turn_num}</span>'
        f'<div style="display:flex;align-items:center;gap:8px;flex:1;">{verdict_badge}</div>'
        f'<span style="font-size:0.7rem;color:#666666;white-space:nowrap;flex-shrink:0;">'
        f'HTTP {_h(str(status_code))} &nbsp;·&nbsp; {latency} ms</span>'
        f'</div>'
    )

    content_style = (
        "font-family:var(--ct-content-font);font-size:1rem;font-weight:700;"
        "line-height:1.65;word-break:break-word;"
    )
    _USER_C = "#60A5FA"   # blue  — matches --ct-user-text
    _BOT_C  = "#4ADE80"   # green — matches --ct-bot-text
    _USER_BG = "#0A1628"
    _BOT_BG  = "#091A0F"

    user_content = (
        f'<div style="{content_style}color:{_USER_C};">{_h(user_q)}</div>'
        if user_q else
        '<em style="font-size:0.85rem;color:#666666;">empty</em>'
    )
    bot_content = (
        f'<div style="{content_style}color:{_BOT_C};">{_h(reply)}</div>'
        if reply else
        '<em style="font-size:0.85rem;color:#666666;">no reply extracted</em>'
    )

    ep_label = _h(endpoint_name).upper()
    body_html = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;">'
        f'<div style="padding:14px 18px;border-right:1px solid #2A2A2A;'
        f'background:{_USER_BG};border-left:3px solid {_USER_C};">'
        f'<div style="font-size:0.63rem;font-weight:700;letter-spacing:0.14em;'
        f'color:{_USER_C};margin-bottom:10px;">USER</div>'
        f'{user_content}</div>'
        f'<div style="padding:14px 18px;background:{_BOT_BG};border-left:3px solid {_BOT_C};">'
        f'<div style="font-size:0.63rem;font-weight:700;letter-spacing:0.14em;'
        f'color:{_BOT_C};margin-bottom:10px;">{ep_label}</div>'
        f'{bot_content}</div>'
        f'</div>'
    )

    judge_inner = ""
    if score is not None:
        judge_inner += f'<div style="max-width:280px;margin-bottom:8px;">{_score_bar(score)}</div>'

    if reasoning:
        judge_inner += (
            f'<p style="margin:0 0 8px;font-size:0.85rem;color:#CCCCCC;line-height:1.55;">'
            f'{_h(reasoning)}</p>'
        )

    need       = analysis.get("need_satisfied")
    strengths  = analysis.get("strengths") or []
    issues     = analysis.get("issues") or []
    suggestion = (analysis.get("suggestion") or "").strip()

    if need is not None:
        ns_color = "#22C55E" if need else "#EF4444"
        ns_label = "Need satisfied" if need else "Need not satisfied"
        judge_inner += (
            f'<div style="margin:4px 0 8px;font-size:0.8rem;color:{ns_color};font-weight:500;">'
            f'{"●" if need else "○"} {ns_label}</div>'
        )

    if strengths or issues:
        cols_html = ""
        if strengths:
            items = "".join(
                f'<li style="margin:2px 0;color:#22C55E;font-size:0.82rem;">{_h(s)}</li>'
                for s in strengths
            )
            cols_html += (
                f'<div><div style="font-size:0.63rem;font-weight:700;color:#666666;'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;">Strengths</div>'
                f'<ul style="margin:0;padding-left:14px;">{items}</ul></div>'
            )
        if issues:
            items = "".join(
                f'<li style="margin:2px 0;color:#EF4444;font-size:0.82rem;">{_h(i)}</li>'
                for i in issues
            )
            cols_html += (
                f'<div><div style="font-size:0.63rem;font-weight:700;color:#666666;'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;">Issues</div>'
                f'<ul style="margin:0;padding-left:14px;">{items}</ul></div>'
            )
        judge_inner += (
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:6px 0;">'
            f'{cols_html}</div>'
        )

    if suggestion and suggestion.lower() not in ("none", "n/a", ""):
        judge_inner += (
            f'<div style="margin:6px 0;padding:7px 11px;background:#1A1A1A;'
            f'border-left:3px solid #E87D0D;border-radius:3px;">'
            f'<span style="font-size:0.68rem;font-weight:700;color:#E87D0D;'
            f'text-transform:uppercase;letter-spacing:0.08em;margin-right:6px;">Suggestion</span>'
            f'<span style="font-size:0.83rem;color:#CCCCCC;">{_h(suggestion)}</span></div>'
        )

    criteria_scores = analysis.get("criteria_scores") or {}
    if criteria_scores:
        rows = ""
        for cname, cdata in criteria_scores.items():
            cscore  = cdata.get("score", 0.0)
            creason = cdata.get("reasoning", "")
            rows += (
                f'<tr style="border-top:1px solid #1E1E1E;">'
                f'<td style="padding:5px 10px 5px 0;font-size:0.8rem;font-weight:600;'
                f'color:#E8E8E8;white-space:nowrap;width:130px;">{_h(cname)}</td>'
                f'<td style="padding:5px 14px 5px 0;width:180px;">{_score_bar(cscore)}</td>'
                f'<td style="padding:5px 0;font-size:0.78rem;color:#888888;'
                f'line-height:1.4;">{_h(creason)}</td>'
                f'</tr>'
            )
        judge_inner += (
            f'<div style="margin-top:10px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:#666666;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Criteria</div>'
            f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'
            f'</div>'
        )

    judge_html = ""
    if judge_inner:
        judge_html = (
            f'<div style="padding:12px 16px;border-top:1px solid #2A2A2A;background:#151515;">'
            f'<div style="font-size:0.63rem;font-weight:700;letter-spacing:0.14em;'
            f'color:#666666;text-transform:uppercase;margin-bottom:10px;">Judge</div>'
            f'{judge_inner}'
            f'</div>'
        )

    error_html = ""
    if error:
        error_html = (
            f'<div style="padding:8px 16px;border-top:1px solid #2A2A2A;'
            f'background:#1F0D0D;color:#DC2626;font-size:0.82rem;">⚠ {_h(error)}</div>'
        )

    return (
        f'<div style="{_card_border}{_card_bg}border-radius:6px;'
        f'overflow:hidden;margin-bottom:10px;">'
        f'{header_html}{body_html}{judge_html}{error_html}'
        f'</div>'
    )


def _render_conclusion_html(data: dict) -> str:
    """Return an HTML string for the conclusion report (mirrors app.py _render_conclusion)."""
    if not data or data.get("_parse_error"):
        return ""

    acc: list[str] = [
        '<div style="background:#151515;border:1px solid #2A2A2A;border-radius:6px;'
        'padding:18px 22px;margin-top:10px;">'
    ]

    def _sec(label: str, icon: str = "") -> str:
        prefix = f"{icon}&nbsp;&nbsp;" if icon else ""
        return (
            f'<div style="font-size:0.68rem;font-weight:700;color:#666666;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin:18px 0 6px;">'
            f'{prefix}{label}</div>'
        )

    def _para(text: str) -> str:
        return (
            f'<p style="font-size:0.88rem;color:#CCCCCC;line-height:1.6;margin:0 0 6px;">'
            f'{_h(text)}</p>'
        )

    def _ul(items: list, color: str = "#CCCCCC") -> str:
        return '<ul style="margin:0;padding-left:16px;">' + "".join(
            f'<li style="font-size:0.85rem;color:{color};margin:3px 0;line-height:1.5;">'
            f'{_h(str(i))}</li>' for i in items
        ) + "</ul>"

    if data.get("executive_summary"):
        acc.append(
            f'<div style="padding:12px 16px;background:#1A1A1A;border-left:4px solid #E87D0D;'
            f'border-radius:3px;margin-bottom:16px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:#E87D0D;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Executive Summary</div>'
            f'{_para(data["executive_summary"])}</div>'
        )

    if data.get("behavior_overview"):
        acc.append(_sec("Overall Behaviour", "◈"))
        acc.append(_para(data["behavior_overview"]))

    strong   = data.get("strong_points") or []
    failures = data.get("failures") or []
    if strong or failures:
        sev_c = {"critical": "#EF4444", "major": "#F59E0B", "minor": "#888888"}
        cols  = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:10px 0;">'
        if strong:
            cols += (
                f'<div><div style="font-size:0.63rem;font-weight:700;color:#22C55E;'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Strong Points</div>'
                f'{_ul(strong, "#22C55E")}</div>'
            )
        else:
            cols += "<div></div>"
        if failures:
            f_li = "".join(
                f'<li style="margin:4px 0;font-size:0.85rem;color:#CCCCCC;line-height:1.5;">'
                f'<span style="font-size:0.7rem;font-weight:700;'
                f'color:{sev_c.get(f.get("severity","minor"),"#888888")};'
                f'text-transform:uppercase;margin-right:4px;">'
                f'[T{f.get("turn","?")} {f.get("severity","minor")}]</span>'
                f'{_h(f.get("description",""))}</li>'
                for f in failures
            )
            cols += (
                f'<div><div style="font-size:0.63rem;font-weight:700;color:#EF4444;'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Failures</div>'
                f'<ul style="margin:0;padding-left:16px;">{f_li}</ul></div>'
            )
        acc.append(cols + "</div>")

    hallucinations = data.get("hallucinations") or []
    acc.append(_sec("Hallucinations / Fabrications", "⚠"))
    if hallucinations:
        h_li = "".join(
            f'<li style="margin:6px 0;font-size:0.85rem;line-height:1.5;">'
            f'<span style="color:#E87D0D;font-weight:600;">Turn {h.get("turn","?")}:</span> '
            f'<span style="color:#CCCCCC;">{_h(h.get("claimed",""))}</span>'
            + (f'<br><span style="font-size:0.78rem;color:#888888;">{_h(h.get("issue",""))}</span>'
               if h.get("issue") else "")
            + "</li>"
            for h in hallucinations
        )
        acc.append(f'<ul style="margin:0;padding-left:16px;">{h_li}</ul>')
    else:
        acc.append('<span style="font-size:0.85rem;color:#22C55E;">None detected.</span>')

    off_track = data.get("off_track") or []
    if off_track:
        acc.append(_sec("Off-Track Responses", "↗"))
        ot_li = "".join(
            f'<li style="margin:4px 0;font-size:0.85rem;color:#CCCCCC;line-height:1.5;">'
            f'<span style="color:#E87D0D;font-weight:600;">Turn {ot.get("turn","?")}:</span> '
            f'{_h(ot.get("description",""))}</li>'
            for ot in off_track
        )
        acc.append(f'<ul style="margin:0;padding-left:16px;">{ot_li}</ul>')

    for key, label, icon in [
        ("consistency_analysis",  "Consistency",          "≡"),
        ("communication_quality", "Communication Quality", "✦"),
        ("task_completion",       "Task Completion",       "✓"),
        ("user_experience",       "User Experience",       "👤"),
    ]:
        if data.get(key):
            acc.append(_sec(label, icon))
            acc.append(_para(data[key]))

    if data.get("factual_concerns"):
        acc.append(_sec("Factual Concerns", "?"))
        acc.append(_ul(data["factual_concerns"], "#F59E0B"))

    if data.get("critical_issues"):
        acc.append(_sec("Critical Issues", "✕"))
        acc.append(_ul(data["critical_issues"], "#EF4444"))

    if data.get("recommendations"):
        acc.append(_sec("Recommendations", "→"))
        acc.append(_ul(data["recommendations"], "#60A5FA"))

    if data.get("conclusion"):
        acc.append(
            f'<div style="margin-top:18px;padding:12px 16px;background:#1A1A1A;'
            f'border-left:4px solid #E87D0D;border-radius:3px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:#E87D0D;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Conclusion</div>'
            f'{_para(data["conclusion"])}</div>'
        )

    acc.append("</div>")
    return "\n".join(acc)


def render_run_html(
    run_id: int,
    run_name: str | None,
    run: Any,
    tc: Any,
    ep: Any,
    turns: list[Any],
    tester: str | None = None,
) -> str:
    status = run.status or "—"
    verdict = run.verdict or ""
    score = run.verdict_score
    run_analysis = run.run_analysis or {}
    ep_name = ep.name if ep else "Bot"
    tc_name = tc.name if tc else "—"

    title = run_name or f"Run {run_id}"
    from datetime import timezone as _tz, timedelta as _td
    _IST = _tz(_td(hours=5, minutes=30))
    def _to_ist(dt: Any) -> str:
        if dt is None:
            return "—"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        return dt.astimezone(_IST).strftime("%Y-%m-%d %H:%M:%S IST")
    started  = _to_ist(run.started_at)
    finished = _to_ist(run.finished_at)

    s_bg = _STATUS_BG.get(status, "#1A1A1A")
    s_fg = _STATUS_FG.get(status, "#E8E8E8")
    status_pill = (
        f'<span style="padding:2px 10px;border-radius:3px;background:{s_bg};'
        f'color:{s_fg};font-weight:600;font-size:0.78rem;letter-spacing:0.05em;">'
        f'{status.upper()}</span>'
    )
    verdict_pill_html = _verdict_pill(verdict) if verdict else '<span style="color:#666666">—</span>'
    score_html = _score_bar_threshold(score) if score is not None else '<span style="color:#666666">—</span>'
    tokens = run.total_tokens or 0
    cost   = run.total_cost_usd or 0.0

    summary_html = (
        f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;'
        f'background:#151515;border:1px solid #2A2A2A;border-radius:4px;'
        f'padding:14px 18px;margin-bottom:14px;">'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:#666666;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Status</div>'
        f'{status_pill}</div>'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:#666666;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Verdict</div>'
        f'{verdict_pill_html}</div>'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:#666666;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Score</div>'
        f'{score_html}</div>'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:#666666;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Tokens</div>'
        f'<span style="font-size:1rem;font-weight:700;color:#E8E8E8;">{tokens:,}</span></div>'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:#666666;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Cost (USD)</div>'
        f'<span style="font-size:1rem;font-weight:700;color:#E8E8E8;">${cost:.4f}</span></div>'
        f'</div>'
    )

    reasoning_html = ""
    if run.verdict_reasoning:
        reasoning_html = (
            f'<div style="padding:10px 14px;background:#151515;border-radius:3px;'
            f'border-left:3px solid #E87D0D;font-size:0.88rem;color:#CCCCCC;margin:8px 0 14px;">'
            f'{_h(run.verdict_reasoning)}</div>'
        )

    criteria_summary_html = ""
    if run_analysis:
        rows_html = ""
        for cname, cdata in run_analysis.items():
            ts    = cdata.get("transcript_score")
            avg_t = cdata.get("avg_turn_score")
            tr    = cdata.get("transcript_reasoning", "")
            wt    = cdata.get("weight", 0)
            turn_scores = cdata.get("turn_scores") or []
            avg_text = f"{avg_t:.2f}" if avg_t is not None else "—"
            spark = " ".join(
                ("▲" if s >= 0.7 else "▼" if s < 0.4 else "◆") for s in turn_scores
            ) if turn_scores else "—"
            ts_html = _score_bar(ts) if ts is not None else "—"
            rows_html += (
                f'<tr style="border-bottom:1px solid #1E1E1E;">'
                f'<td style="padding:6px 8px 6px 0;font-size:0.83rem;font-weight:600;'
                f'color:#E8E8E8;white-space:nowrap;">{_h(cname)}'
                f'<span style="margin-left:6px;font-size:0.7rem;font-weight:400;'
                f'color:#666666;">w:{wt:.2f}</span></td>'
                f'<td style="padding:6px 12px;min-width:130px;">{ts_html}</td>'
                f'<td style="padding:6px 8px;font-size:0.76rem;color:#888888;white-space:nowrap;">'
                f'avg/turn: {avg_text}  {spark}</td>'
                f'<td style="padding:6px 0;font-size:0.78rem;color:#888888;">{_h(tr)}</td>'
                f'</tr>'
            )
        criteria_summary_html = (
            f'<div style="margin:0 0 14px;background:#151515;border:1px solid #2A2A2A;'
            f'border-radius:4px;padding:14px;">'
            f'<div style="font-size:0.7rem;font-weight:600;color:#666666;'
            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">'
            f'Per-Criterion Summary</div>'
            f'<table style="width:100%;border-collapse:collapse;">{rows_html}</table>'
            f'</div>'
        )

    meta_html = (
        f'<div style="margin-bottom:16px;padding:10px 14px;background:#151515;'
        f'border:1px solid #2A2A2A;border-radius:4px;font-size:0.82rem;">'
        f'<span style="color:#666666;">Test case: </span>'
        f'<span style="color:#CCCCCC;">{_h(tc_name)}</span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<span style="color:#666666;">Endpoint: </span>'
        f'<span style="color:#CCCCCC;">{_h(ep_name)}</span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<span style="color:#666666;">Started: </span>'
        f'<span style="color:#CCCCCC;">{started}</span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<span style="color:#666666;">Finished: </span>'
        f'<span style="color:#CCCCCC;">{finished}</span>'
        + (
            f'&nbsp;&nbsp;·&nbsp;&nbsp;'
            f'<span style="color:#666666;">Tester: </span>'
            f'<span style="color:#CCCCCC;">{_h(tester)}</span>'
            if tester else ""
        )
        + '</div>'
    )

    # ── Failed turns summary ─────────────────────────────────────────────────
    failed_turns = [t for t in turns if (getattr(t, "turn_verdict", None) or "").lower() == "fail"]
    failed_turns_html = ""
    if failed_turns:
        rows = ""
        for t in failed_turns:
            n      = t.turn_number
            score  = t.turn_score
            reason = t.turn_reasoning or "—"
            s_str  = f"{score:.2f}" if score is not None else "—"
            rows += (
                f'<tr style="border-bottom:1px solid rgba(239,68,68,0.2);">'
                f'<td style="padding:5px 10px 5px 0;font-size:0.78rem;font-weight:700;'
                f'color:#EF4444;white-space:nowrap;width:70px;">Turn {n}</td>'
                f'<td style="padding:5px 10px 5px 0;font-size:0.78rem;font-weight:700;'
                f'color:#EF4444;white-space:nowrap;width:48px;">{s_str}</td>'
                f'<td style="padding:5px 0;font-size:0.82rem;color:#CCCCCC;line-height:1.4;">'
                f'{_h(reason)}</td>'
                f'</tr>'
            )
        failed_turns_html = (
            f'<div style="margin:10px 0 14px;background:#180A0A;'
            f'border:1px solid rgba(239,68,68,0.45);border-left:4px solid #EF4444;'
            f'border-radius:4px;padding:12px 16px;">'
            f'<div style="font-size:0.68rem;font-weight:700;color:#EF4444;'
            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">'
            f'✕ Failed Turns ({len(failed_turns)})</div>'
            f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'
            f'</div>'
        )

    turns_html = "".join(
        _render_turn_card(
            {
                "turn_number":    t.turn_number,
                "user_query":     t.user_query,
                "extracted_reply": t.extracted_reply,
                "turn_verdict":   t.turn_verdict,
                "turn_score":     t.turn_score,
                "turn_reasoning": t.turn_reasoning,
                "turn_analysis":  t.turn_analysis or {},
                "error":          t.error,
                "latency_ms":     t.latency_ms,
                "status_code":    t.status_code,
            },
            endpoint_name=ep_name,
        )
        for t in turns
    )

    conclusion_html = ""
    if getattr(run, "conclusion", None):
        conclusion_html = f'<h2>Conclusion</h2>{_render_conclusion_html(run.conclusion)}'

    import re as _re
    def _slug(s: str | None) -> str:
        return _re.sub(r"\s+", "_", (s or "").strip()) or "unknown"
    run_session_id = f"{_slug(tc_name)}-{_slug(run_name or f'Run {run_id}')}-{run_id}"

    endpoint_details_html = _render_endpoint_details(ep, session_id=run_session_id)

    body = (
        f'<h1>{_h(title)}</h1>'
        f'{endpoint_details_html}'
        f'{meta_html}'
        f'<h2>Run Summary</h2>'
        f'{summary_html}'
        f'{reasoning_html}'
        f'{criteria_summary_html}'
        f'{failed_turns_html}'
        f'<h2>Transcript</h2>'
        f'{turns_html}'
        f'{conclusion_html}'
    )

    escaped_title = _h(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escaped_title} — conv-tester</title>
<style>
{_CSS}
</style>
</head>
<body>
{body}
</body>
</html>"""
