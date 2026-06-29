"""Shared HTML rendering helpers, color maps, and utility functions."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from ui.api import api_get


# ── Utility helpers ───────────────────────────────────────────────────────────

def _is_light_theme() -> bool:
    """True when the user has selected the light theme (Settings → Appearance)."""
    return st.session_state.get("_theme", "dark") == "light"


def _find(items: list[dict], idx: Any) -> dict:
    for it in items:
        if it["id"] == idx:
            return it
    return {}


def _h(s: str) -> str:
    """Minimal HTML escape for user-supplied text inserted into f-string HTML."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")


def _html_table(headers: list[str], rows: list[list]) -> str:
    """Render a simple HTML table. Uses the theme's global thead/tbody styling so
    it adapts to light/dark automatically (unlike st.dataframe, whose canvas grid
    ignores our CSS). Cell values are stringified and HTML-escaped."""
    head = "".join(
        f'<th style="text-align:left;padding:6px 12px 6px 0;">{_h(h)}</th>' for h in headers
    )
    body = ""
    for r in rows:
        cells = "".join(
            f'<td style="padding:6px 12px 6px 0;">{_h(str(c))}</td>' for c in r
        )
        body += f"<tr>{cells}</tr>"
    return (
        '<table style="width:100%;border-collapse:collapse;margin-bottom:10px;">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    )


def _stop_detail(run: dict, turns: list[dict]) -> str | None:
    """Return the human-readable detail behind a run's stop, if any."""
    sr = run.get("stop_reason")
    if not sr or not turns:
        return None
    if sr in ("simulator_error", "endpoint_error"):
        for t in reversed(turns):
            err = t.get("error") or ""
            if err:
                detail = err
                for prefix in ("simulator_error: ", "endpoint_error: ", "template_error: "):
                    if detail.startswith(prefix):
                        detail = detail[len(prefix):]
                        break
                return detail
    return None


def _build_extractors(reply_path: str, extra_json: str) -> dict[str, str]:
    try:
        extra = json.loads(extra_json or "{}")
    except json.JSONDecodeError:
        extra = {}
    extra["reply"] = reply_path
    return extra


def _run_extraction(response: Any, extractors: dict[str, str]) -> dict[str, Any]:
    """Run JSONPath extractors against a sample response dict."""
    from jsonpath_ng.ext import parse as jp_parse
    out: dict[str, Any] = {}
    for name, path in extractors.items():
        if not path:
            continue
        try:
            matches = [m.value for m in jp_parse(path).find(response)]
            if matches:
                out[name] = matches[0] if len(matches) == 1 else matches
        except Exception as e:
            out[name] = f"<error: {e}>"
    return out


# ── Color / status maps ───────────────────────────────────────────────────────

_STATUS_COLOR = {
    "running":   ("var(--ct-pill-run)",  "#60A5FA"),
    "completed": ("var(--ct-pill-pass)", "#22C55E"),
    "failed":    ("var(--ct-pill-fail)", "#EF4444"),
    "stopped":   ("var(--ct-pill-inc)",  "#F59E0B"),
    "paused":    ("rgba(100,130,220,0.12)", "#7B9FE0"),
}

_STOP_REASON_LABEL: dict[str, str] = {
    "endpoint_error":         "Endpoint returned an error",
    "endpoint_signaled_end":  "Endpoint signaled end of conversation",
    "goal_achieved":          "Goal achieved — simulator marked conversation complete",
    "max_turns":              "Maximum turns reached",
    "cost_cap":               "Cost cap reached",
    "user_stopped":           "Stopped by user",
    "simulator_error":        "Simulator failed to generate follow-up question",
    "judge_error":            "Judge analysis failed (conversation completed)",
    "step_pause":             "Paused in step mode — awaiting next question",
}

_STOP_REASON_STYLE: dict[str, tuple[str, str]] = {
    "endpoint_error":        ("rgba(239,68,68,0.10)",  "#EF4444"),
    "simulator_error":       ("rgba(239,68,68,0.10)",  "#EF4444"),
    "user_stopped":          ("rgba(232,125,13,0.10)", "#E87D0D"),
    "cost_cap":              ("rgba(232,125,13,0.10)", "#E87D0D"),
    "endpoint_signaled_end": ("rgba(34,197,94,0.10)",  "#22C55E"),
    "goal_achieved":         ("rgba(34,197,94,0.10)",  "#22C55E"),
    "max_turns":             ("rgba(96,165,250,0.10)", "#60A5FA"),
    "judge_error":           ("rgba(232,125,13,0.10)", "#E87D0D"),
    "step_pause":            ("rgba(100,130,220,0.10)", "#7B9FE0"),
}

_VERDICT_BG   = {"pass": "var(--ct-pill-pass)", "fail": "var(--ct-pill-fail)", "inconclusive": "var(--ct-pill-inc)"}
_VERDICT_FG   = {"pass": "#22C55E", "fail": "#EF4444", "inconclusive": "#F59E0B"}
_VERDICT_DOT  = {"pass": "#22C55E", "fail": "#EF4444", "inconclusive": "#F59E0B"}
_VERDICT_ICON = {"pass": "✓", "fail": "✕", "inconclusive": "?"}


# ── HTML rendering helpers ────────────────────────────────────────────────────

def _run_status_html(status: str) -> str:
    _map = {
        "running":   ("#1C2030", "#4A6FA5", "#6B9BD2"),
        "completed": ("#0D1F12", "#2D7A3A", "#4CAF50"),
        "failed":    ("#1F0D0D", "#A53A3A", "#EF5350"),
        "stopped":   ("#1A1A1A", "#555555", "#999999"),
    }
    bg, border, color = _map.get(status, ("#1A1A1A", "#555555", "#999999"))
    return (
        f'<div style="padding-top:4px;">'
        f'<span style="display:inline-block;padding:2px 7px;border-radius:3px;'
        f'background:{bg};border:1px solid {border};color:{color};'
        f'font-size:0.68rem;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;">{status}</span></div>'
    )


def _verdict_score_html(verdict: str | None, score: float | None) -> str:
    if not verdict:
        return '<div style="padding-top:4px;color:var(--ct-text5);font-size:0.78rem;">—</div>'
    _map = {
        "pass":         ("#4CAF50", "#0D1F12"),
        "fail":         ("#EF5350", "#1F0D0D"),
        "inconclusive": ("#FFA726", "#1F1A0D"),
    }
    color, bg = _map.get(verdict.lower(), ("#999999", "#1A1A1A"))
    score_str = f" &nbsp;{score:.2f}" if score is not None else ""
    return (
        f'<div style="padding-top:4px;">'
        f'<span style="display:inline-block;padding:2px 7px;border-radius:3px;'
        f'background:{bg};border:1px solid {color};color:{color};'
        f'font-size:0.68rem;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;">{verdict.upper()}</span>'
        f'<span style="font-size:0.78rem;color:var(--ct-text4);margin-left:5px;">{score_str}</span>'
        f'</div>'
    )


def _score_bar_html(score: float | None) -> str:
    if score is None:
        return ""
    pct = round((score or 0) * 100)
    color = "#22C55E" if pct >= 70 else "#F59E0B" if pct >= 40 else "#EF4444"
    return (
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<div style="flex:1;height:5px;background:var(--ct-border);border-radius:2px;overflow:hidden;">'
        f'<div style="width:{pct}%;height:100%;background:{color};border-radius:2px;"></div>'
        f'</div>'
        f'<span style="font-size:0.78rem;font-weight:600;color:{color};min-width:32px;">{score:.2f}</span>'
        f'</div>'
    )


def _score_bar_with_threshold_html(score: float | None, threshold: float = 0.7) -> str:
    if score is None:
        return '<span style="color:#666666">—</span>'
    pct = round((score or 0) * 100)
    tpct = round(threshold * 100)
    color = "#22C55E" if (score or 0) >= threshold else "#EF4444"
    return (
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<div style="flex:1;height:7px;background:var(--ct-border);border-radius:2px;'
        f'overflow:visible;position:relative;">'
        f'<div style="width:{pct}%;height:100%;background:{color};border-radius:2px;"></div>'
        f'<div style="position:absolute;top:-3px;left:{tpct}%;width:2px;height:13px;'
        f'background:var(--ct-text3);border-radius:1px;" title="Pass threshold {threshold:.0%}"></div>'
        f'</div>'
        f'<span style="font-size:0.88rem;font-weight:700;color:{color};min-width:36px;">'
        f'{score:.2f}</span>'
        f'</div>'
    )


def _verdict_pill(verdict: str) -> str:
    bg  = _VERDICT_BG.get(verdict, "var(--ct-surface2)")
    fg  = _VERDICT_FG.get(verdict, "var(--ct-text)")
    dot = _VERDICT_DOT.get(verdict, "var(--ct-text4)")
    ico = _VERDICT_ICON.get(verdict, "•")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'padding:2px 9px;border-radius:3px;background:{bg};'
        f'color:{fg};font-size:0.76rem;font-weight:600;letter-spacing:0.05em;">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{dot};"></span>'
        f'{ico} {verdict.upper()}'
        f'</span>'
    )


# ── Run-table helpers (shared by Batch Results and History) ────────────────────

# Preset colours a tester can use to mark a run. "None" clears the marker.
# Keys are shown in the dropdown; values are the stored/applied hex (6-digit).
_MARKER_COLORS: dict[str, str] = {
    "None":   "",
    "Red":    "#EF4444",
    "Orange": "#F59E0B",
    "Green":  "#22C55E",
    "Blue":   "#3B82F6",
    "Purple": "#A855F7",
}


def _table_header(labels: list[str], cols_w: list[float] | None = None) -> None:
    cols = st.columns(cols_w or [1] * len(labels))
    for col, lbl in zip(cols, labels):
        col.markdown(
            f'<div style="font-size:0.70rem;font-weight:700;letter-spacing:0.08em;'
            f'text-transform:uppercase;color:var(--ct-text4);padding-bottom:3px;">{lbl}</div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<hr style="margin:2px 0 8px;border-color:var(--ct-border);">',
        unsafe_allow_html=True,
    )


def _cell(
    text: str,
    size: str = "0.87rem",
    weight: str = "400",
    color: str = "var(--ct-text)",
) -> str:
    return (
        f'<div style="padding-top:5px;font-size:{size};'
        f'font-weight:{weight};color:{color};">{text}</div>'
    )


def _tint(inner_html: str, tint: str | None) -> str:
    """Wrap a cell's HTML in a light background wash for marked rows.

    `tint` is an 8-digit hex (colour + alpha) or None. The negative margins let
    adjacent cells' washes butt together so the row reads as one coloured band.
    """
    if not tint:
        return inner_html
    return (
        f'<div style="background:{tint};border-radius:3px;'
        f'padding:2px 6px;margin:-2px -4px;min-height:30px;">{inner_html}</div>'
    )


def _passfail_pill(label: str, color: str) -> str:
    """Small pill used by the turn-level Result rollup column.

    `color` must be a full 6-digit hex (e.g. "#EF4444") — the alpha suffixes
    below are concatenated onto it for the tint and border.
    """
    return (
        f'<div style="padding-top:3px;">'
        f'<span style="display:inline-block;padding:2px 9px;border-radius:3px;'
        f'background:{color}1a;border:1px solid {color}55;'
        f'color:{color} !important;font-size:0.68rem;font-weight:700;'
        f'letter-spacing:0.05em;text-transform:uppercase;">{label}</span></div>'
    )


def _status_pill(status: str) -> str:
    """Theme-aware run-status pill (mirrors _verdict_pill).

    Uses the shared, theme-aware _STATUS_COLOR map so the background is a light
    tint in the light theme and a dark tint in the dark theme. The `!important`
    on the text colour keeps it from being flattened by the light theme's global
    dark-text rule.
    """
    bg, accent = _STATUS_COLOR.get(status, ("var(--ct-surface2)", "var(--ct-text4)"))
    return (
        f'<div style="padding-top:3px;">'
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'padding:2px 9px;border-radius:3px;background:{bg};'
        f'border:1px solid {accent}40;'
        f'color:{accent} !important;font-size:0.68rem;font-weight:700;'
        f'letter-spacing:0.05em;text-transform:uppercase;">'
        f'<span style="width:7px;height:7px;border-radius:50%;'
        f'background:{accent};flex-shrink:0;"></span>'
        f'{status}</span></div>'
    )


def _turn_breakdown_cell(turn_total: int, turn_failed: int, turn_has_verdict: bool, tint: str | None) -> str:
    """The 'Turn ✓/✗' cell: blank until at least one turn has a verdict, then
    shows success (= total − failed) and failed counts. Shared by both tables."""
    if not turn_has_verdict:
        return _tint(_cell("", size="0.83rem"), tint)
    passed = turn_total - turn_failed
    return _tint(
        '<div style="padding-top:5px;font-size:0.83rem;font-weight:600;">'
        f'<span style="color:#16A34A;">✓{passed}</span>&nbsp;&nbsp;'
        f'<span style="color:#EF4444;">✗{turn_failed}</span></div>', tint)


def _turn_result_cell(turn_total: int, turn_failed: int, turn_has_verdict: bool, tint: str | None) -> str:
    """The 'Result' rollup cell: FAILED if any turn failed, else PASS — blank
    until at least one turn has a verdict."""
    if not turn_has_verdict:
        return _tint(_cell("", size="0.83rem"), tint)
    if turn_failed > 0:
        return _tint(_passfail_pill("Failed", "#EF4444"), tint)
    return _tint(_passfail_pill("Pass", "#22C55E"), tint)


def _row_tint(run: dict) -> str | None:
    """8-digit-hex tint for a run row based on its marker_color, or None."""
    marker = run.get("marker_color") or ""
    return f"{marker}26" if marker else None  # ~15% alpha


def _render_run_marker_controls(col_done, col_mark, run: dict, rid: int, key_prefix: str) -> None:
    """Render the tester's 'Reviewed' checkbox and colour-marker dropdown for a
    run row, persisting changes via PATCH /runs/{id}. Shared by Batch Results and
    History so both behave identically. Triggers a rerun after a change."""
    from ui.api import api_patch

    rev_now = bool(run.get("reviewed", False))
    rev_key = f"_rev_{key_prefix}_{rid}"
    if rev_key not in st.session_state:
        st.session_state[rev_key] = rev_now
    checked = col_done.checkbox("reviewed", key=rev_key, label_visibility="collapsed")
    if checked != rev_now:
        try:
            api_patch(f"/runs/{rid}", {"reviewed": checked})
        except Exception as e:
            st.warning(f"Couldn't save reviewed flag: {e}")
        st.rerun()

    marker = run.get("marker_color") or ""
    col_key = f"_clr_{key_prefix}_{rid}"
    cur_name = next((nm for nm, hx in _MARKER_COLORS.items() if hx == marker), "None")
    if col_key not in st.session_state:
        st.session_state[col_key] = cur_name
    chosen = col_mark.selectbox(
        "mark", list(_MARKER_COLORS.keys()), key=col_key, label_visibility="collapsed",
    )
    new_color = _MARKER_COLORS[chosen]
    if new_color != marker:
        try:
            api_patch(f"/runs/{rid}", {"marker_color": new_color})
        except Exception as e:
            st.warning(f"Couldn't save colour marker: {e}")
        st.rerun()
