"""Transcript, failed-turns summary, and continue-run rendering."""

from __future__ import annotations

import streamlit as st

from ui.api import api_post
from ui.components.shared import _h, _is_light_theme
from ui.components.turn_card import _render_turn_card


def _render_failed_turns_summary(turns: list[dict], run_id: int | None = None) -> None:
    """Compact red-tinted table of failed turns with clickable anchor links."""
    failed = [t for t in turns if (t.get("turn_verdict") or "").lower() == "fail"]
    if not failed:
        return

    # Theme-aware: bright red-tinted panel on light, deep on dark.
    _light = _is_light_theme()
    _panel_bg   = "#FEF2F2" if _light else "#180A0A"
    _reason_col = "#3C3C3E" if _light else "#CCCCCC"
    _th_col     = "#6E6E73" if _light else "#888"

    anchor_prefix = "turn-" if run_id is not None else "turn-card-"
    rows_html = ""
    for t in failed:
        tn        = t.get("turn_number", "?")
        score     = t.get("turn_score")
        reason    = _h(t.get("turn_reasoning") or "—")
        score_str = f"{score:.2f}" if score is not None else "—"
        rows_html += (
            f'<tr style="border-bottom:1px solid rgba(239,68,68,0.2);">'
            f'<td style="padding:5px 10px 5px 0;width:70px;">'
            f'<a href="#{anchor_prefix}{tn}" style="font-size:0.82rem;font-weight:700;'
            f'color:#EF4444;text-decoration:none;">Turn {tn}</a></td>'
            f'<td style="padding:5px 10px;width:54px;font-size:0.82rem;'
            f'font-weight:700;color:#EF4444;">{score_str}</td>'
            f'<td style="padding:5px 0;font-size:0.82rem;color:{_reason_col};line-height:1.4;">{reason}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<div style="margin:10px 0 14px;background:{_panel_bg};'
        f'border:1px solid rgba(239,68,68,0.45);border-left:4px solid #EF4444;'
        f'border-radius:4px;padding:12px 18px;">'
        f'<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:#EF4444;margin-bottom:10px;">✕ Failed Turns ({len(failed)})</div>'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="border-bottom:1px solid rgba(239,68,68,0.3);">'
        f'<th style="text-align:left;padding:3px 10px 6px 0;font-size:0.65rem;font-weight:700;'
        f'color:{_th_col};text-transform:uppercase;letter-spacing:0.08em;">Turn</th>'
        f'<th style="text-align:left;padding:3px 10px 6px;font-size:0.65rem;font-weight:700;'
        f'color:{_th_col};text-transform:uppercase;letter-spacing:0.08em;">Score</th>'
        f'<th style="text-align:left;padding:3px 0 6px;font-size:0.65rem;font-weight:700;'
        f'color:{_th_col};text-transform:uppercase;letter-spacing:0.08em;">Reasoning</th>'
        f'</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_transcript(
    turns: list[dict],
    endpoint_name: str = "Bot",
    judge_visible: bool = True,
    run_id: int | None = None,
    allow_analyse: bool = False,
    key_prefix: str = "",
) -> None:
    _render_failed_turns_summary(turns, run_id=run_id)
    for t in turns:
        _render_turn_card(
            t,
            endpoint_name=endpoint_name,
            judge_visible=judge_visible,
            rj_state=None,
            run_id=run_id,
            allow_analyse=allow_analyse,
            key_prefix=key_prefix,
        )


def _render_step_controls(run: dict, key_prefix: str) -> None:
    """Step-mode control panel: shown when run.status == 'paused'.

    Displays the pre-generated next question in an editable textarea so the
    tester can review and optionally modify it before sending.
    """
    run_id = run["id"]
    ck_q = f"_step_query_{key_prefix}"

    # Seed the textarea from the backend once per pause; preserves user edits
    # across reruns within the same pause cycle.
    if ck_q not in st.session_state:
        st.session_state[ck_q] = run.get("next_pending_query") or ""

    _light = _is_light_theme()
    _panel_bg    = "#F0F4FF" if _light else "#0D1220"
    _border_col  = "rgba(100,130,220,0.5)"
    _accent_col  = "#7B9FE0"
    _text3       = "#555" if _light else "var(--ct-text3)"

    turns_so_far = run.get("turn_total", 0)
    next_turn_num = turns_so_far + 1

    st.markdown(
        f'<div style="margin:0 0 16px;padding:14px 18px;'
        f'background:{_panel_bg};'
        f'border:1.5px solid {_border_col};'
        f'border-left:4px solid {_accent_col};'
        f'border-radius:6px;">'
        f'<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.13em;'
        f'text-transform:uppercase;color:{_accent_col};margin-bottom:4px;">'
        f'⏸ Paused — awaiting turn {next_turn_num}</div>'
        f'<div style="font-size:0.82rem;color:{_text3};line-height:1.5;">'
        f'Edit the next question below, then click <strong>Send next turn</strong> to '
        f'continue step-by-step, or <strong>Continue (auto)</strong> to run to completion.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    query = st.text_area(
        f"Next question (turn {next_turn_num})",
        key=ck_q,
        height=110,
    )

    btn_step, btn_cont, btn_stop, btn_refresh, _ = st.columns([1.2, 1.6, 0.9, 1.0, 1.3])

    if btn_step.button("▶ Send next turn", key=f"{key_prefix}_step", type="primary"):
        try:
            api_post(f"/runs/{run_id}/step", {"query": query.strip(), "step_mode": True})
            st.session_state.pop(ck_q, None)  # clear so next pause repopulates from backend
            st.rerun()
        except Exception as e:
            st.error(f"Step failed: {e}")

    if btn_cont.button("▶▶ Continue (auto)", key=f"{key_prefix}_cont"):
        try:
            api_post(f"/runs/{run_id}/step", {"query": query.strip(), "step_mode": False})
            st.session_state.pop(ck_q, None)
            st.rerun()
        except Exception as e:
            st.error(f"Continue failed: {e}")

    if btn_stop.button("⏹ Stop", key=f"{key_prefix}_stop_step"):
        try:
            api_post(f"/runs/{run_id}/stop", {})
            st.rerun()
        except Exception as e:
            st.error(f"Stop failed: {e}")

    if btn_refresh.button("↺ Refresh", key=f"{key_prefix}_refresh_step"):
        # Evict cached query so the textarea picks up any updated next_pending_query
        # from the backend (e.g. if it just finished pre-generating).
        st.session_state.pop(ck_q, None)
        st.rerun()


def _render_continue_run_section(run: dict, key_prefix: str) -> None:
    """Inline 'Continue Run' UI shown on Run and History pages for stopped/failed runs."""
    st.subheader("Continue Run")
    st.markdown(
        '<p style="font-size:0.82rem;color:var(--ct-text4);margin:0 0 12px;">'
        'The conversation will resume from where it left off — the existing transcript '
        'is preserved and new turns are appended.</p>',
        unsafe_allow_html=True,
    )

    ck_turns = f"_cont_turns_{key_prefix}"
    col_btn, col_turns, _ = st.columns([1, 1, 4])
    additional_turns = col_turns.number_input(
        "Additional turns",
        min_value=1,
        max_value=50,
        value=st.session_state.get(ck_turns, 5),
        step=1,
        key=ck_turns,
        label_visibility="collapsed",
    )
    col_turns.caption(f"{additional_turns} more turn{'s' if additional_turns != 1 else ''}")

    if col_btn.button("▶ Continue run", key=f"{key_prefix}_cont_btn", type="primary"):
        with st.spinner("Resuming run…"):
            try:
                api_post(
                    f"/runs/{run['id']}/continue",
                    {"additional_turns": int(additional_turns)},
                )
                st.session_state["active_run_id"] = run["id"]
                st.session_state["nav_page"] = "Single Run"
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to continue run: {exc}")
