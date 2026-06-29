"""Run page — launch and monitor a test run."""

from __future__ import annotations

import time

import streamlit as st

from ui.api import api_get, api_post
from ui.components.conclusion import _render_conclusion_section
from ui.components.run_summary import _render_run_summary
from ui.components.shared import _find, _stop_detail
from ui.components.transcript import (
    _render_continue_run_section,
    _render_step_controls,
    _render_transcript,
)
from ui.components.ws_logs import render_ws_logs_panel


def page_run() -> None:
    try:
        tcs  = api_get("/test-cases")
        eps  = api_get("/endpoint-configs")
        llms = api_get("/llm-configs")
    except Exception as e:
        st.error(f"Failed to load configs: {e}")
        return

    if not tcs:
        st.warning("No test cases yet — create one in **Configs → Test Cases**.")
        return
    if not eps:
        st.warning("No endpoint configs yet — create one in **Configs → Endpoints**.")
        return
    if not llms:
        st.warning("No LLM configs yet — create one in **Configs → LLMs**.")
        return

    sim_llms   = [l for l in llms if l["role"] in ("simulator", "either")]
    judge_llms = [l for l in llms if l["role"] in ("judge", "either")]

    if not sim_llms:
        st.warning("No LLM with role 'simulator' or 'either'. Edit an LLM config.")
        return
    if not judge_llms:
        st.warning("No LLM with role 'judge' or 'either'. Edit an LLM config.")
        return

    run_name = st.text_input("Run name _*_", placeholder="e.g. Smoke test v2")

    c1, c2 = st.columns(2)
    tc_id    = c1.selectbox("Test case",    [t["id"] for t in tcs],
                             format_func=lambda i: _find(tcs, i)["name"])
    ep_id    = c1.selectbox("Endpoint",     [e["id"] for e in eps],
                             format_func=lambda i: _find(eps, i)["name"])
    sim_id   = c2.selectbox("Simulator LLM (generates user messages)",
                             [l["id"] for l in sim_llms],
                             format_func=lambda i: _find(sim_llms, i)["name"])
    judge_id = c2.selectbox("Judge LLM (evaluates the transcript at the end)",
                             [l["id"] for l in judge_llms],
                             format_func=lambda i: _find(judge_llms, i)["name"])

    with st.expander("Override judge rules for this run (optional)"):
        st.markdown(
            '<p style="font-size:0.82rem;color:var(--ct-text4);margin:0 0 6px;">Replaces the test case\'s '
            '<em>success criteria</em> only for this run — the original is not modified. '
            'Leave blank to use the test case criteria.</p>',
            unsafe_allow_html=True,
        )
        judge_override = st.text_area(
            "Judge rules override",
            placeholder="e.g. The assistant must always respond in under 20 words.",
            height=100,
            label_visibility="collapsed",
        )
        st.markdown(
            '<p style="font-size:0.78rem;color:var(--ct-text5);margin:4px 0 0;">'
            '💡 Tip: once a run completes, you can also re-judge its transcript with new rules '
            'from the <strong>History</strong> tab — no need to re-run the endpoint.</p>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="margin:20px 0 6px;padding:14px 18px;'
        'background:rgba(232,125,13,0.08);'
        'border:1.5px solid rgba(232,125,13,0.5);'
        'border-radius:8px;">'
        '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.13em;'
        'color:#E87D0D;text-transform:uppercase;margin-bottom:5px;">🤖 AI Analysis</div>'
        '<div style="font-size:0.88rem;color:var(--ct-text3);line-height:1.6;">'
        'When <strong style="color:var(--ct-text);">ON</strong>, each turn and the full '
        'transcript are scored by the judge LLM after the run. '
        'Switch <strong style="color:var(--ct-text);">OFF</strong> for faster/cheaper runs '
        'where you only need the raw conversation transcript — no AI scoring.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    enable_judge = st.toggle("Enable AI judge analysis", value=False)

    st.markdown(
        '<div style="margin:12px 0 6px;padding:14px 18px;'
        'background:rgba(100,130,220,0.06);'
        'border:1.5px solid rgba(100,130,220,0.35);'
        'border-radius:8px;">'
        '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.13em;'
        'color:#7B9FE0;text-transform:uppercase;margin-bottom:5px;">⏸ Step Mode</div>'
        '<div style="font-size:0.88rem;color:var(--ct-text3);line-height:1.6;">'
        'When <strong style="color:var(--ct-text);">ON</strong>, the run pauses after every '
        'turn so you can review the bot\'s response and edit the next question before sending. '
        'Switch <strong style="color:var(--ct-text);">OFF</strong> for fully automatic '
        'multi-turn execution.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    enable_step_mode = st.toggle("Enable step mode (pause after every turn)", value=False)

    _sel_ep = _find(eps, ep_id)
    ws_connect_delay: float = 2.0
    if _sel_ep.get("protocol") == "websocket":
        st.markdown(
            '<div style="margin:12px 0 6px;padding:14px 18px;'
            'background:rgba(34,197,94,0.05);'
            'border:1.5px solid rgba(34,197,94,0.35);'
            'border-radius:8px;">'
            '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.13em;'
            'color:#22C55E;text-transform:uppercase;margin-bottom:5px;">🔌 WebSocket Connect Delay</div>'
            '<div style="font-size:0.88rem;color:var(--ct-text3);line-height:1.6;">'
            'Seconds to wait after connecting before sending the first message. '
            'Gives the server time to send any welcome frames that should be ignored.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        ws_connect_delay = st.number_input(
            "Connect delay (seconds)",
            min_value=0.0, max_value=30.0, value=2.0, step=0.5,
            label_visibility="collapsed",
            key="_run_ws_delay",
        )

    if st.button("▶ Start run", type="primary"):
        if not run_name.strip():
            st.error("Please enter a run name before starting.")
        else:
            try:
                payload: dict = {
                    "name": run_name.strip(),
                    "test_case_id": tc_id, "endpoint_config_id": ep_id,
                    "simulator_llm_id": sim_id, "judge_llm_id": judge_id,
                    "skip_judge": not enable_judge,
                    "step_mode": enable_step_mode,
                    "ws_connect_delay_sec": ws_connect_delay,
                }
                if judge_override.strip():
                    payload["judge_criteria_override"] = judge_override.strip()
                run = api_post("/runs", payload)
                st.session_state["active_run_id"] = run["id"]
                st.success(f"Started run #{run['id']}")
            except Exception as e:
                st.error(f"Failed to start: {e}")

    run_id = st.session_state.get("active_run_id")
    if not run_id:
        return

    st.markdown("---")

    try:
        run   = api_get(f"/runs/{run_id}")
        turns = api_get(f"/runs/{run_id}/turns")
    except Exception as e:
        st.error(f"Poll failed: {e}")
        return

    _run_display_name = run.get("name") or f"Run #{run_id}"
    st.subheader(_run_display_name)

    placeholder = st.empty()
    ep_name = _find(eps, run.get("endpoint_config_id")).get("name", "Bot")
    is_running = run["status"] == "running"
    is_paused  = run["status"] == "paused"

    stop_col, clear_col, refresh_col, _, judge_col = st.columns([1, 1, 0.8, 2.2, 2])
    if is_running:
        if stop_col.button("⏹ Stop run"):
            try:
                api_post(f"/runs/{run_id}/stop", {})
                st.toast("Stop requested.")
            except Exception as e:
                st.error(f"Stop failed: {e}")
    else:
        _rs = run["status"]
        _rv = run.get("verdict") or ""
        _rl = (f"✓ {_rv.upper()}" if _rs == "completed" and _rv
               else "✓ Complete" if _rs == "completed"
               else "⏸ Paused" if _rs == "paused"
               else "⏹ Stopped" if _rs == "stopped"
               else "✕ Failed")
        if _rs == "completed":
            stop_col.success(_rl)
        elif _rs == "paused":
            stop_col.info(_rl)
        elif _rs == "stopped":
            stop_col.warning(_rl)
        else:
            stop_col.error(_rl)

    if clear_col.button("✕ Clear"):
        st.session_state.pop("active_run_id", None)
        st.rerun()
    if refresh_col.button("↺", help="Refresh — manually fetch the latest turns and run status"):
        st.rerun()
    judge_visible = judge_col.toggle(
        "Show judge analysis",
        value=st.session_state.get("_judge_visible", True),
        key="_judge_toggle_run",
    )
    st.session_state["_judge_visible"] = judge_visible

    if is_paused:
        _render_step_controls(run, key_prefix=f"runp_{run_id}")
    elif not is_running and run.get("status") in ("stopped", "failed"):
        _render_continue_run_section(run, key_prefix=f"runp_{run_id}")

    with placeholder.container():
        _render_run_summary(run, run_analysis=run.get("run_analysis"),
                            stop_detail=_stop_detail(run, turns))
        _render_transcript(turns, endpoint_name=ep_name, judge_visible=judge_visible)

    if run.get("status") in ("completed", "stopped", "failed"):
        _render_conclusion_section(run, llms, key_prefix=f"run_{run_id}")

    # WebSocket traffic log — shown only for WebSocket endpoints
    _ep_cfg = _find(eps, run.get("endpoint_config_id"))
    if _ep_cfg.get("protocol") == "websocket":
        with st.expander("🔌 WebSocket Logs", expanded=False):
            render_ws_logs_panel(run_id, key_prefix=f"runp_{run_id}")

    # Auto-refresh every 2 s while the run is active or paused in step mode.
    # We re-render via st.rerun() instead of a blocking while-loop so that,
    # when this page shares a tab group (Single Run → New Run / History),
    # the sibling tab still renders between polls.
    if is_running or is_paused:
        time.sleep(2)
        st.rerun()
