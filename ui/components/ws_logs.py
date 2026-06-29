"""WebSocket traffic log panel for the run page."""

from __future__ import annotations

import streamlit as st

from ui.api import api_delete, api_get
from ui.components.shared import _is_light_theme

# ── visual config ─────────────────────────────────────────────────────────────

_DIR_CONFIG = {
    #  dir        arrow   label       color (dark)  color (light)
    "out":   ("→", "OUT",   "#E87D0D", "#C05C00"),
    "in":    ("←", "IN",    "#22C55E", "#16803B"),
    "event": ("⚡", "EVT",   "#7B9FE0", "#3B5FBD"),
}

_KIND_COLOR_DARK = {
    "connect":    "#22C55E",
    "disconnect": "#EF4444",
    "reconnect":  "#F59E0B",
    "ping":       "#888888",
    "pong":       "#666666",
    "error":      "#EF4444",
    "discard":    "#B45309",  # amber — welcome frames silently dropped
    "message":    None,   # inherits direction colour
}
_KIND_COLOR_LIGHT = {
    "connect":    "#16803B",
    "disconnect": "#B91C1C",
    "reconnect":  "#D97706",
    "ping":       "#999999",
    "pong":       "#AAAAAA",
    "error":      "#B91C1C",
    "discard":    "#92400E",  # amber — welcome frames silently dropped
    "message":    None,
}


def _entry_html(entry: dict, light: bool) -> str:
    dir_ = entry.get("dir", "event")
    kind = entry.get("kind", "message")
    ts   = entry.get("ts",  "")
    body = entry.get("body", "")

    arrow, label, dc, lc = _DIR_CONFIG.get(dir_, ("·", "???", "#888", "#888"))
    dir_color = lc if light else dc

    kind_map  = _KIND_COLOR_LIGHT if light else _KIND_COLOR_DARK
    body_color = kind_map.get(kind) or dir_color

    ts_color    = "#999" if light else "#666"
    label_color = dir_color

    # Escape HTML special chars in body
    safe_body = (body
                 .replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))

    return (
        f'<div style="margin:0;padding:1px 0;line-height:1.45;white-space:pre-wrap;'
        f'word-break:break-all;font-size:0.76rem;">'
        f'<span style="color:{ts_color};">{ts}</span> '
        f'<span style="color:{label_color};font-weight:700;">{arrow} {label:3s}</span> '
        f'<span style="color:{body_color};">{safe_body}</span>'
        f'</div>'
    )


def render_ws_logs_panel(run_id: int, *, key_prefix: str = "ws_logs") -> None:
    """Expandable terminal-style WebSocket log panel for *run_id*."""
    light = _is_light_theme()

    # ── fetch ─────────────────────────────────────────────────────────────────
    try:
        entries: list[dict] = api_get(f"/runs/{run_id}/ws-logs")
    except Exception as exc:
        st.caption(f"Could not load WS logs: {exc}")
        return

    # ── header row ────────────────────────────────────────────────────────────
    h_col, clr_col = st.columns([5, 1])
    count = len(entries)
    h_col.markdown(
        f'<span style="font-size:0.78rem;color:{"#555" if light else "#888"};">'
        f'{count} entr{"y" if count == 1 else "ies"}'
        f'</span>',
        unsafe_allow_html=True,
    )
    if clr_col.button("Clear", key=f"{key_prefix}_clear", help="Discard all log entries"):
        try:
            api_delete(f"/runs/{run_id}/ws-logs")
        except Exception:
            pass
        st.rerun()

    if not entries:
        st.caption("No WebSocket traffic recorded yet.")
        return

    # ── build terminal view ───────────────────────────────────────────────────
    bg  = "#F8F9FA" if light else "#0A0A0A"
    bdr = "#D0D0D0" if light else "#222"

    rows_html = "\n".join(_entry_html(e, light) for e in entries)

    st.markdown(
        f'<div style="'
        f'background:{bg};'
        f'border:1px solid {bdr};'
        f'border-radius:6px;'
        f'padding:10px 14px;'
        f'max-height:380px;'
        f'overflow-y:auto;'
        f'font-family:"JetBrains Mono","Fira Code","Cascadia Code",ui-monospace,monospace;'
        f'">'
        f'{rows_html}'
        f'<div id="ws-log-bottom"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
