"""Turn card rendering with colour pickers and action buttons."""

from __future__ import annotations

import json

import streamlit as st

from ui.api import api_patch
from ui.components.shared import (
    _VERDICT_BG,
    _VERDICT_DOT,
    _VERDICT_FG,
    _VERDICT_ICON,
    _h,
    _is_light_theme,
    _score_bar_html,
)

# Dark-theme conversation-card palette (bright text on a deep tinted background).
_CARD_COLORS: dict[str, dict[str, str]] = {
    "green":  {"text": "#4ADE80", "bg": "#091A0F", "border": "#4ADE80"},
    "blue":   {"text": "#60A5FA", "bg": "#0A1628", "border": "#60A5FA"},
    "red":    {"text": "#F87171", "bg": "#1F0A0A", "border": "#F87171"},
    "yellow": {"text": "#FACC15", "bg": "#1A1500", "border": "#FACC15"},
    "white":  {"text": "#F0F0F0", "bg": "#1A1A1A", "border": "#C0C0C0"},
    "violet": {"text": "#A78BFA", "bg": "#130A28", "border": "#A78BFA"},
    "orange": {"text": "#FB923C", "bg": "#1F1000", "border": "#FB923C"},
    "cyan":   {"text": "#22D3EE", "bg": "#051A1F", "border": "#22D3EE"},
}

# Light-theme palette: darker, readable text on a soft tinted background so the
# request/response cards stay bright in the light theme.
_CARD_COLORS_LIGHT: dict[str, dict[str, str]] = {
    "green":  {"text": "#15803D", "bg": "#F0FDF4", "border": "#16A34A"},
    "blue":   {"text": "#1D4ED8", "bg": "#EFF6FF", "border": "#2563EB"},
    "red":    {"text": "#DC2626", "bg": "#FEF2F2", "border": "#DC2626"},
    "yellow": {"text": "#B45309", "bg": "#FEFCE8", "border": "#CA8A04"},
    "white":  {"text": "#1D1D1F", "bg": "#F4F4F5", "border": "#9CA3AF"},
    "violet": {"text": "#7C3AED", "bg": "#F5F3FF", "border": "#7C3AED"},
    "orange": {"text": "#C2410C", "bg": "#FFF7ED", "border": "#EA580C"},
    "cyan":   {"text": "#0E7490", "bg": "#ECFEFF", "border": "#0891B2"},
}

_COLOR_ORDER = ["green", "blue", "red", "yellow", "white", "violet", "orange", "cyan"]
_COLOR_EMOJI = {
    "green": "🟢", "blue": "🔵", "red": "🔴", "yellow": "🟡",
    "white": "⬜", "violet": "🟣", "orange": "🟠", "cyan": "🔷",
}


def _consume_color_query_params() -> None:
    """Detect colour query-params, apply to session state, then rerun."""
    qp = st.query_params
    to_apply: dict[str, str] = {}
    to_delete: list[str] = []
    for key in list(qp.keys()):
        if not (key.startswith("_qc_") or key.startswith("_ac_")):
            continue
        parts = key.split("_")   # ["", "qc"/"ac", rid, tn]
        if len(parts) != 4:
            continue
        try:
            rid = int(parts[2])
            tn  = int(parts[3])
        except ValueError:
            continue
        val = qp[key]
        if val not in _CARD_COLORS:
            continue
        col = parts[1]
        ss_key = f"_user_color_{rid}_{tn}" if col == "qc" else f"_card_color_{rid}_{tn}"
        to_apply[ss_key] = val
        to_delete.append(key)

    if to_apply:
        for sk, sv in to_apply.items():
            st.session_state[sk] = sv
        for key in to_delete:
            del qp[key]
        st.rerun()


def _render_turn_card(
    t: dict,
    endpoint_name: str = "Bot",
    judge_visible: bool = True,
    rj_state: str | None = None,
    run_id: int | None = None,
    allow_analyse: bool = False,
    key_prefix: str = "",
) -> None:
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

    # ── Header verdict badge ──────────────────────────────────────────────────
    if rj_state == "judging":
        verdict_badge = (
            '<span style="display:inline-flex;align-items:center;gap:6px;'
            'padding:2px 10px;border-radius:3px;background:rgba(232,125,13,0.12);'
            'color:#E87D0D;font-size:0.72rem;font-weight:700;letter-spacing:0.06em;">'
            '<span style="width:6px;height:6px;border-radius:50%;background:#E87D0D;'
            'animation:rj-pulse 1s ease-in-out infinite;flex-shrink:0;"></span>'
            'JUDGING...</span>'
        )
    elif rj_state == "pending":
        verdict_badge = (
            '<span style="display:inline-flex;align-items:center;gap:6px;'
            'padding:2px 10px;border-radius:3px;background:var(--ct-surface2);'
            'color:var(--ct-text5);font-size:0.72rem;font-weight:700;letter-spacing:0.06em;">'
            '<span style="width:6px;height:6px;border-radius:50%;border:1px solid var(--ct-text5);'
            'flex-shrink:0;"></span>PENDING</span>'
        )
    elif verdict:
        v_bg  = _VERDICT_BG.get(verdict, "var(--ct-surface2)")
        v_fg  = _VERDICT_FG.get(verdict, "var(--ct-text)")
        v_dot = _VERDICT_DOT.get(verdict, "var(--ct-text4)")
        v_ico = _VERDICT_ICON.get(verdict, "•")
        s_str = f"{score:.2f}" if score is not None else "—"
        verdict_badge = (
            f'<span style="display:inline-flex;align-items:center;gap:5px;'
            f'padding:2px 9px;border-radius:3px;background:{v_bg};'
            f'color:{v_fg};font-size:0.72rem;font-weight:700;letter-spacing:0.06em;">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:{v_dot};'
            f'flex-shrink:0;"></span>{v_ico} {verdict.upper()}</span>'
            f'<span style="font-size:0.85rem;font-weight:700;color:{v_fg};">{s_str}</span>'
        )
    elif score is not None:
        verdict_badge = (
            f'<span style="font-size:0.85rem;font-weight:700;color:var(--ct-text4);">'
            f'score {score:.2f}</span>'
        )
    else:
        verdict_badge = ""

    # ── Colour tags ───────────────────────────────────────────────────────────
    _kp = f"{key_prefix}_" if key_prefix else ""
    _user_color_key = f"_user_color_{_kp}{run_id}_{turn_num}" if run_id is not None else None
    _bot_color_key  = f"_card_color_{_kp}{run_id}_{turn_num}" if run_id is not None else None
    _user_tag = st.session_state.get(_user_color_key, "blue")  if _user_color_key else "blue"
    _bot_tag  = st.session_state.get(_bot_color_key,  "green") if _bot_color_key  else "green"
    _light = _is_light_theme()
    _palette = _CARD_COLORS_LIGHT if _light else _CARD_COLORS
    _uc = _palette.get(_user_tag, _palette["blue"])
    _bc = _palette.get(_bot_tag,  _palette["green"])
    user_text_color = _uc["text"]; user_bg_color = _uc["bg"]; user_border_color = _uc["border"]
    bot_text_color  = _bc["text"]; bot_bg_color  = _bc["bg"]; bot_border_color  = _bc["border"]

    # ── Header colour indicator dots ──────────────────────────────────────────
    if run_id is not None:
        _q_dot = _CARD_COLORS[_user_tag]["text"]
        _a_dot = _CARD_COLORS[_bot_tag]["text"]
        _lbl_strong = "rgba(0,0,0,0.45)" if _light else "rgba(255,255,255,0.28)"
        _lbl_faint  = "rgba(0,0,0,0.25)" if _light else "rgba(255,255,255,0.15)"
        _hdr_color_indicator = (
            f'<div style="display:flex;align-items:center;gap:4px;flex-shrink:0;margin:0 4px;">'
            f'<span style="width:7px;height:7px;border-radius:50%;background:{_q_dot};" title="Q: {_user_tag}"></span>'
            f'<span style="font-size:0.58rem;color:{_lbl_strong};font-weight:600;">Q</span>'
            f'<span style="font-size:0.58rem;color:{_lbl_faint};margin:0 1px;">·</span>'
            f'<span style="font-size:0.58rem;color:{_lbl_strong};font-weight:600;">A</span>'
            f'<span style="width:7px;height:7px;border-radius:50%;background:{_a_dot};" title="A: {_bot_tag}"></span>'
            f'</div>'
        )
    else:
        _hdr_color_indicator = ""

    # ── Fail / error visual state ─────────────────────────────────────────────
    _card_failed = verdict == "fail" or bool(error)
    _fail_hdr_bg  = "#FEE2E2" if _light else "#2D1010"
    _fail_card_bg = "#FEF2F2" if _light else "#180A0A"
    _hdr_bg      = _fail_hdr_bg if _card_failed else "var(--ct-surface2)"
    _card_border = (
        "border:2px solid #EF4444;border-left:5px solid #EF4444;"
        if _card_failed else
        "border:1px solid var(--ct-border);"
    )
    _card_bg = f"background:{_fail_card_bg};" if _card_failed else ""

    header_html = (
        f'<div style="display:flex;align-items:center;gap:10px;padding:8px 14px;'
        f'background:{_hdr_bg};border-bottom:1px solid var(--ct-border);">'
        f'<span style="font-size:0.68rem;font-weight:700;letter-spacing:0.14em;'
        f'color:var(--ct-accent);min-width:52px;flex-shrink:0;">TURN {turn_num}</span>'
        f'<div style="display:flex;align-items:center;gap:8px;flex:1;">{verdict_badge}</div>'
        f'{_hdr_color_indicator}'
        f'<span style="font-size:0.7rem;color:var(--ct-text5);white-space:nowrap;flex-shrink:0;">'
        f'HTTP {status_code} &nbsp;·&nbsp; {latency} ms</span>'
        f'</div>'
    )

    # ── Two-column conversation ───────────────────────────────────────────────
    content_style = (
        f'font-family:var(--ct-content-font);font-size:1rem;font-weight:700;'
        f'line-height:1.65;word-break:break-word;'
    )
    user_content = (
        f'<div style="{content_style}color:{user_text_color};">{_h(user_q)}</div>'
        if user_q else
        f'<em style="font-size:0.85rem;color:var(--ct-text5);">empty</em>'
    )
    bot_content = (
        f'<div style="{content_style}color:{bot_text_color};">{_h(reply)}</div>'
        if reply else
        f'<em style="font-size:0.85rem;color:var(--ct-text5);">no reply extracted</em>'
    )

    ep_label = _h(endpoint_name).upper()
    body_html = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;">'
        f'<div style="padding:14px 18px;border-right:1px solid var(--ct-border);'
        f'background:{user_bg_color};border-left:3px solid {user_border_color};">'
        f'<div style="font-size:0.63rem;font-weight:700;letter-spacing:0.14em;'
        f'color:{user_text_color};margin-bottom:10px;">USER</div>'
        f'{user_content}</div>'
        f'<div style="padding:14px 18px;background:{bot_bg_color};'
        f'border-left:3px solid {bot_border_color};">'
        f'<div style="font-size:0.63rem;font-weight:700;letter-spacing:0.14em;'
        f'color:{bot_text_color};margin-bottom:10px;">{ep_label}</div>'
        f'{bot_content}</div>'
        f'</div>'
    )

    # ── Judge section ─────────────────────────────────────────────────────────
    judge_inner = ""

    if judge_visible and rj_state not in ("pending", "judging"):
        if score is not None:
            judge_inner += (
                f'<div style="max-width:280px;margin-bottom:8px;">'
                f'{_score_bar_html(score)}</div>'
            )

        if reasoning:
            judge_inner += (
                f'<p style="margin:0 0 8px;font-size:0.85rem;color:var(--ct-text2);'
                f'line-height:1.55;">{_h(reasoning)}</p>'
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
                    f'<div><div style="font-size:0.63rem;font-weight:700;color:var(--ct-text5);'
                    f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;">Strengths</div>'
                    f'<ul style="margin:0;padding-left:14px;">{items}</ul></div>'
                )
            if issues:
                items = "".join(
                    f'<li style="margin:2px 0;color:#EF4444;font-size:0.82rem;">{_h(i)}</li>'
                    for i in issues
                )
                cols_html += (
                    f'<div><div style="font-size:0.63rem;font-weight:700;color:var(--ct-text5);'
                    f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;">Issues</div>'
                    f'<ul style="margin:0;padding-left:14px;">{items}</ul></div>'
                )
            judge_inner += (
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:6px 0;">'
                f'{cols_html}</div>'
            )

        if suggestion and suggestion.lower() not in ("none", "n/a", ""):
            judge_inner += (
                f'<div style="margin:6px 0;padding:7px 11px;background:var(--ct-surface2);'
                f'border-left:3px solid var(--ct-accent);border-radius:3px;">'
                f'<span style="font-size:0.68rem;font-weight:700;color:var(--ct-accent);'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-right:6px;">Suggestion</span>'
                f'<span style="font-size:0.83rem;color:var(--ct-text2);">{_h(suggestion)}</span></div>'
            )

        criteria_scores = analysis.get("criteria_scores") or {}
        if criteria_scores:
            rows = ""
            for cname, cdata in criteria_scores.items():
                cscore  = cdata.get("score", 0.0)
                creason = cdata.get("reasoning", "")
                rows += (
                    f'<tr style="border-top:1px solid var(--ct-border2);">'
                    f'<td style="padding:5px 10px 5px 0;font-size:0.8rem;font-weight:600;'
                    f'color:var(--ct-text);white-space:nowrap;width:130px;">{_h(cname)}</td>'
                    f'<td style="padding:5px 14px 5px 0;width:180px;">{_score_bar_html(cscore)}</td>'
                    f'<td style="padding:5px 0;font-size:0.78rem;color:var(--ct-text4);'
                    f'line-height:1.4;">{_h(creason)}</td>'
                    f'</tr>'
                )
            judge_inner += (
                f'<div style="margin-top:10px;">'
                f'<div style="font-size:0.63rem;font-weight:700;color:var(--ct-text5);'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Criteria</div>'
                f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'
                f'</div>'
            )

    judge_html = ""
    if judge_inner:
        judge_html = (
            f'<div style="padding:12px 16px;border-top:1px solid var(--ct-border);'
            f'background:var(--ct-surface);">'
            f'<div style="font-size:0.63rem;font-weight:700;letter-spacing:0.14em;'
            f'color:var(--ct-text5);text-transform:uppercase;margin-bottom:10px;">Judge</div>'
            f'{judge_inner}'
            f'</div>'
        )

    # ── Error bar ─────────────────────────────────────────────────────────────
    error_html = ""
    if error:
        error_html = (
            f'<div style="padding:8px 16px;border-top:1px solid var(--ct-border);'
            f'background:var(--ct-pill-fail);color:#DC2626;font-size:0.82rem;">'
            f'⚠ {_h(error)}</div>'
        )

    # ── Assemble card ─────────────────────────────────────────────────────────
    _anchor_id = f"turn-{turn_num}" if run_id is not None else f"turn-card-{turn_num}"
    st.markdown(
        f'<div id="{_anchor_id}" style="{_card_border}{_card_bg}border-radius:6px;'
        f'overflow:hidden;margin-bottom:2px;">'
        f'{header_html}'
        f'{body_html}{judge_html}{error_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Colour pickers + Mark Failed + Analyse button ─────────────────────────
    if run_id is not None:
        _ta_key      = f"_ta_loading_{_kp}{run_id}_{turn_num}"
        _mf_key      = f"_mf_loading_{_kp}{run_id}_{turn_num}"
        show_analyse = allow_analyse and bool(t.get("extracted_reply"))

        _q_emoji = _COLOR_EMOJI[_user_tag]
        _a_emoji = _COLOR_EMOJI[_bot_tag]
        has_verdict = bool(verdict)
        btn_label   = "🔍 Re-analyse" if has_verdict else "🔍 Analyse with AI"

        is_manual_fail = (verdict == "fail" and t.get("turn_score") is None
                          and t.get("turn_reasoning") == "Manually marked by user")
        fail_btn_label = "✕ Clear fail" if is_manual_fail else "✕ Mark failed"

        if show_analyse:
            _cc_q, _cc_a, _cc_gap, _cc_fail, _cc_analyse = st.columns([1, 1, 4, 2, 2], gap="small")
        else:
            _cc_q, _cc_a, _cc_gap, _cc_fail = st.columns([1, 1, 6, 2], gap="small")
            _cc_analyse = None

        with _cc_q.popover(f"{_q_emoji} Q", use_container_width=True):
            st.caption("Question colour")
            _pc = st.columns(4, gap="small")
            for _ci, _c in enumerate(_COLOR_ORDER):
                if _pc[_ci % 4].button(
                    _COLOR_EMOJI[_c],
                    key=f"_qpick_{_kp}{run_id}_{turn_num}_{_c}",
                    help=_c.capitalize(),
                    use_container_width=True,
                    type="primary" if _c == _user_tag else "secondary",
                ):
                    st.session_state[f"_user_color_{_kp}{run_id}_{turn_num}"] = _c
                    st.rerun()

        with _cc_a.popover(f"A {_a_emoji}", use_container_width=True):
            st.caption("Answer colour")
            _pc = st.columns(4, gap="small")
            for _ci, _c in enumerate(_COLOR_ORDER):
                if _pc[_ci % 4].button(
                    _COLOR_EMOJI[_c],
                    key=f"_apick_{_kp}{run_id}_{turn_num}_{_c}",
                    help=_c.capitalize(),
                    use_container_width=True,
                    type="primary" if _c == _bot_tag else "secondary",
                ):
                    st.session_state[f"_card_color_{_kp}{run_id}_{turn_num}"] = _c
                    st.rerun()

        if _cc_fail.button(
            fail_btn_label,
            key=f"_mf_btn_{_kp}{run_id}_{turn_num}",
            type="secondary",
            use_container_width=True,
        ):
            st.session_state[_mf_key] = True

        if st.session_state.get(_mf_key):
            with st.spinner("Updating turn verdict…"):
                try:
                    new_verdict = None if is_manual_fail else "fail"
                    api_patch(
                        f"/runs/{run_id}/turns/{turn_num}/verdict",
                        {"verdict": new_verdict},
                    )
                    st.session_state.pop(_mf_key, None)
                    st.rerun()
                except Exception as _exc:
                    st.session_state.pop(_mf_key, None)
                    st.error(f"Failed to update verdict: {_exc}")

        if _cc_analyse is not None:
            if _cc_analyse.button(btn_label, key=f"_ta_btn_{_kp}{run_id}_{turn_num}", type="secondary"):
                st.session_state[_ta_key] = True

        if st.session_state.get(_ta_key):
            with st.spinner("Analysing turn with AI judge…"):
                try:
                    from ui.api import api_post
                    api_post(f"/runs/{run_id}/turns/{turn_num}/judge", {})
                    st.session_state.pop(_ta_key, None)
                    st.rerun()
                except Exception as _exc:
                    st.session_state.pop(_ta_key, None)
                    st.error(f"Analysis failed: {_exc}")

    with st.expander(f"Turn {turn_num} — raw request / response / extracted fields"):
        st.markdown("**Request payload**")
        st.code(json.dumps(t.get("raw_request_payload") or {}, indent=2), language="json")
        st.markdown("**Response payload**")
        st.code(json.dumps(t.get("raw_response_payload") or {}, indent=2), language="json")
        st.markdown("**Extracted fields**")
        st.code(json.dumps(t.get("extracted_fields") or {}, indent=2), language="json")
