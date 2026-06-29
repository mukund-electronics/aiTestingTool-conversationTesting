"""History page — browse runs, view transcripts, rejudge, export."""

from __future__ import annotations

import json
import time

import streamlit as st

from ui.api import api_delete, api_get, api_patch, api_post, _client
from ui.components.conclusion import _render_conclusion_section
from ui.components.run_summary import _render_run_summary
from ui.components.shared import (
    _cell,
    _find,
    _h,
    _render_run_marker_controls,
    _row_tint,
    _score_bar_html,
    _status_pill,
    _stop_detail,
    _table_header,
    _tint,
    _turn_breakdown_cell,
    _turn_result_cell,
    _verdict_pill,
)
from ui.components.transcript import (
    _render_continue_run_section,
    _render_step_controls,
    _render_transcript,
)
from ui.components.turn_card import _render_turn_card
from ui.state import _cached, _saved_toast


def page_history() -> None:
    try:
        tcs = api_get("/test-cases")
    except Exception:
        tcs = []

    try:
        llms = _cached("_c_llms", "/llm-configs")
    except Exception:
        llms = []

    c1, c2 = st.columns(2)
    tc_filter = c1.selectbox(
        "Filter by test case",
        [None] + [t["id"] for t in tcs],
        format_func=lambda i: "(all)" if i is None else _find(tcs, i)["name"],
    )
    status_filter = c2.selectbox(
        "Status",
        [None, "running", "completed", "failed", "stopped", "paused"],
        format_func=lambda s: "(all)" if s is None else s,
    )

    params: dict = {}
    if tc_filter:
        params["test_case_id"] = tc_filter
    if status_filter:
        params["status"] = status_filter

    try:
        runs = api_get("/runs", **params)
    except Exception as e:
        st.error(f"Load failed: {e}")
        return

    # Exclude runs that belong to a batch — those are reviewed under the
    # Batch Run → Batch Results tab. Batch runs are ordinary TestRun rows, linked
    # only via RunBatch.run_ids, so we filter them out by ID here.
    try:
        _batches = api_get("/batches")
        _batch_run_ids = {rid for b in _batches for rid in b.get("run_ids", [])}
    except Exception:
        _batch_run_ids = set()
    runs = [r for r in runs if r["id"] not in _batch_run_ids]

    if not runs:
        st.info("No single runs yet.")
        return

    tc_map = {t["id"]: t["name"] for t in tcs}

    def _split_dt(iso: str | None) -> tuple[str, str]:
        if not iso:
            return "", ""
        try:
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            _IST = _tz(_td(hours=5, minutes=30))
            d = _dt.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_IST)
            return d.strftime("%Y-%m-%d"), d.strftime("%H:%M:%S")
        except Exception:
            return iso, ""

    # ── Multi-select state ───────────────────────────────────────────────────
    _all_run_ids = [r["id"] for r in runs]
    _sel_ids = [rid for rid in _all_run_ids if st.session_state.get(f"_hsel_{rid}", False)]

    # Delete confirmation banner
    _hist_del_pending = st.session_state.get("_hist_del_pending")
    if _hist_del_pending:
        _pdel = _hist_del_pending
        st.warning(
            f"**Delete {len(_pdel)} run(s)?**  \n"
            "This permanently removes all their turns and judging data. Cannot be undone.",
            icon="⚠️",
        )
        _dc1, _dc2, _ = st.columns([1.3, 0.9, 6])
        if _dc1.button("✅ Yes, delete all", key="_hist_del_confirm_btn", type="primary"):
            with st.spinner("Deleting…"):
                for _did in _pdel:
                    try:
                        api_delete(f"/runs/{_did}")
                    except Exception:
                        pass
                    st.session_state.pop(f"_hsel_{_did}", None)
            st.session_state.pop("_hist_del_pending", None)
            if st.session_state.get("_hist_sel") in _pdel:
                st.session_state.pop("_hist_sel", None)
            st.rerun()
        if _dc2.button("❌ Cancel", key="_hist_del_cancel_btn"):
            st.session_state.pop("_hist_del_pending", None)
            st.rerun()

    # Selection controls: All / None buttons + actions popover
    _sc1, _sc2, _sc3, _ = st.columns([1, 1, 2, 9])
    if _sc1.button("☑ All", key="_hsel_all", use_container_width=True):
        for _rid in _all_run_ids:
            st.session_state[f"_hsel_{_rid}"] = True
        st.rerun()
    if _sc2.button("☐ None", key="_hsel_none", use_container_width=True):
        for _rid in _all_run_ids:
            st.session_state[f"_hsel_{_rid}"] = False
        st.rerun()
    if _sel_ids:
        with _sc3.popover(f"⋮  {len(_sel_ids)} selected", use_container_width=True):
            st.markdown(f"**{len(_sel_ids)} run(s) selected**")
            st.divider()
            if st.button("🗑 Delete selected", key="_hmenu_del", use_container_width=True):
                st.session_state["_hist_del_pending"] = _sel_ids[:]
                st.rerun()
            if st.button("✅ Mark as reviewed", key="_hmenu_rev", use_container_width=True):
                with st.spinner("Updating…"):
                    for _rid in _sel_ids:
                        try:
                            api_patch(f"/runs/{_rid}", {"reviewed": True})
                        except Exception:
                            pass
                st.rerun()
            if st.button("🔄 Clear markers", key="_hmenu_clr", use_container_width=True):
                with st.spinner("Clearing…"):
                    for _rid in _sel_ids:
                        try:
                            api_patch(f"/runs/{_rid}", {"marker_color": None, "reviewed": False})
                        except Exception:
                            pass
                st.rerun()

    # ── Pre-load selected run data before the table loop ────────────────────
    selected = st.session_state.get("_hist_sel")
    if selected and not any(r["id"] == selected for r in runs):
        st.session_state.pop("_hist_sel", None)
        selected = None

    _run_detail: dict | None = None
    _turns_detail: list | None = None
    if selected:
        try:
            _run_detail   = api_get(f"/runs/{selected}")
            _turns_detail = api_get(f"/runs/{selected}/turns")
        except Exception as _exc:
            st.error(f"Load failed: {_exc}")
            selected = None

    # ── Run table ────────────────────────────────────────────────────────────
    _hcols_w = [0.25, 0.35, 1.85, 0.9, 0.45, 0.8, 0.85, 0.95, 0.95, 0.5, 1.1, 0.75]
    _table_header(
        ["", "#", "Run / Test case", "Status", "Turns", "Turn ✓/✗", "Result",
         "Verdict", "Score", "Done", "Mark", ""],
        _hcols_w,
    )

    for _ri, r in enumerate(runs):
        rid     = r["id"]
        sts     = r.get("status", "")
        verdict = r.get("verdict")
        score   = r.get("verdict_score")
        t_total = r.get("turn_total", 0)
        t_failed = r.get("turn_failed", 0)
        t_hasv  = r.get("turn_has_verdict", False)
        tint    = _row_tint(r)
        _rdate, _rtime = _split_dt(r.get("started_at"))
        _name   = r.get("name") or f"Run #{rid}"
        _tcname = tc_map.get(r["test_case_id"], "")

        (h_cb, h0, h1, h2, h3, h_tr, h_res,
         h4, h5, h_done, h_mark, h6) = st.columns(_hcols_w)

        h_cb.checkbox(" ", key=f"_hsel_{rid}", label_visibility="collapsed")
        h0.markdown(_tint(_cell(str(_ri + 1), weight="600", color="var(--ct-text4)"), tint), unsafe_allow_html=True)

        _sub = _h(_tcname) + (f" · {_rdate} {_rtime}".rstrip() if _rdate else "")
        h1.markdown(_tint(
            f'<div style="padding-top:3px;">'
            f'<div style="font-size:0.88rem;font-weight:600;color:var(--ct-text);">{_h(_name)}</div>'
            f'<div style="font-size:0.72rem;color:var(--ct-text5);">{_sub}</div></div>', tint),
            unsafe_allow_html=True,
        )
        h2.markdown(_tint(_status_pill(sts), tint), unsafe_allow_html=True)
        h3.markdown(_tint(_cell(str(t_total)), tint), unsafe_allow_html=True)
        h_tr.markdown(_turn_breakdown_cell(t_total, t_failed, t_hasv, tint), unsafe_allow_html=True)
        h_res.markdown(_turn_result_cell(t_total, t_failed, t_hasv, tint), unsafe_allow_html=True)
        if verdict:
            h4.markdown(_tint(_verdict_pill(verdict), tint), unsafe_allow_html=True)
        else:
            h4.markdown(_tint(_cell("—", color="var(--ct-text5)"), tint), unsafe_allow_html=True)
        if score is not None:
            h5.markdown(_tint(_score_bar_html(score), tint), unsafe_allow_html=True)
        else:
            h5.markdown(_tint(_cell("—", color="var(--ct-text5)"), tint), unsafe_allow_html=True)

        _render_run_marker_controls(h_done, h_mark, r, rid, "hist")

        _is_sel = st.session_state.get("_hist_sel") == rid
        if h6.button(
            "▲ Hide" if _is_sel else "👁 View",
            key=f"_hview_{rid}", use_container_width=True,
        ):
            st.session_state["_hist_sel"] = None if _is_sel else rid
            st.rerun()

        st.markdown(
            '<hr style="margin:4px 0;border-color:var(--ct-border);opacity:0.35;">',
            unsafe_allow_html=True,
        )

        # ── Inline detail panel — shown directly below the selected row ──────
        if rid == selected and _run_detail is not None:
            run   = _run_detail
            turns = _turns_detail or []

            tc_detail = next((t for t in tcs if t["id"] == run.get("test_case_id")), None)
            current_run_name = run.get("name") or ""

            header_parts = []
            if current_run_name:
                header_parts.append(
                    f'<span style="font-size:0.95rem;font-weight:700;color:var(--ct-accent);">{current_run_name}</span>'
                )
            if tc_detail:
                header_parts.append(
                    f'<span style="font-size:0.68rem;font-weight:600;color:var(--ct-text5);'
                    f'text-transform:uppercase;letter-spacing:0.08em;">test case</span>'
                    f'<span style="font-size:0.88rem;color:var(--ct-text3);">{tc_detail["name"]}</span>'
                )
            if header_parts:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;margin:4px 0 12px;">'
                    + " · ".join(header_parts) +
                    f'</div>',
                    unsafe_allow_html=True,
                )

            rename_key      = f"_rename_run_open_{run['id']}"
            del_pending_key = f"_run_delete_pending_{run['id']}"

            _hdr_c1, _hdr_c2, _ = st.columns([1.4, 1.4, 7])
            if _hdr_c1.button("✏️ Rename", key=f"rename_run_btn_{run['id']}"):
                st.session_state[rename_key] = not st.session_state.get(rename_key, False)
                st.session_state.pop(del_pending_key, None)
            if _hdr_c2.button("🗑 Delete run", key=f"del_run_btn_{run['id']}"):
                st.session_state[del_pending_key] = True
                st.session_state.pop(rename_key, None)

            if st.session_state.get(rename_key):
                new_run_name = st.text_input("Run name", value=current_run_name,
                                             key=f"rename_run_input_{run['id']}")
                if st.button("Save name", key=f"rename_run_save_{run['id']}", type="primary"):
                    with st.spinner("Saving…"):
                        try:
                            api_patch(f"/runs/{run['id']}", {"name": new_run_name.strip()})
                            st.session_state.pop(rename_key, None)
                            label = new_run_name.strip() or "(cleared)"
                            st.toast(f'Run name set to "{label}"', icon="✅")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Rename failed: {exc}")

            if st.session_state.get(del_pending_key):
                run_label = current_run_name or f"Run #{run['id']}"
                st.warning(
                    f"**Delete '{run_label}'?**  \n"
                    f"This permanently removes the run and **all its turns and judging data** "
                    f"from storage. This cannot be undone.",
                    icon="⚠️",
                )
                _rd1, _rd2, _ = st.columns([1, 1, 6])
                if _rd1.button("✅ Yes, delete", key=f"run_del_confirm_{run['id']}", type="primary"):
                    with st.spinner("Deleting…"):
                        try:
                            api_delete(f"/runs/{run['id']}")
                            st.session_state.pop(del_pending_key, None)
                            _saved_toast(f"Run '{run_label}' deleted.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Delete failed: {exc}")
                if _rd2.button("❌ Cancel", key=f"run_del_cancel_{run['id']}"):
                    st.session_state.pop(del_pending_key, None)
                    st.rerun()

            try:
                eps_hist = _cached("_c_eps", "/endpoint-configs")
            except Exception:
                eps_hist = []
            ep_name = _find(eps_hist, run.get("endpoint_config_id")).get("name", "Bot")

            st.markdown("---")
            _render_run_summary(
                run,
                pass_threshold=float((tc_detail or {}).get("pass_threshold") or 0.7),
                run_analysis=run.get("run_analysis"),
                stop_detail=_stop_detail(run, turns),
            )

            rj_key    = f"_rj_{selected}"
            rj_active = st.session_state.get(rj_key)

            if rj_active:
                # ── REJUDGE IN PROGRESS ───────────────────────────────────────
                try:
                    rj_status = api_get(f"/runs/{selected}/rejudge_status")
                except Exception as exc:
                    st.error(f"Status check failed: {exc}")
                    rj_status = {"status": "error", "error": str(exc)}

                s       = rj_status.get("status", "running")
                current = rj_status.get("current_turn", 0)
                total   = rj_status.get("total_turns") or rj_active.get("total", 1)

                if s == "done":
                    v      = rj_status.get("verdict", "?")
                    vscore = rj_status.get("verdict_score")
                    vs_str = f"{vscore:.2f}" if vscore is not None else "n/a"
                    cost   = rj_status.get("cost_usd", 0)
                    st.session_state.pop(rj_key, None)
                    st.success(f"Re-judge complete — **{v.upper()}** (score: {vs_str}) · ${cost:.4f}")
                    time.sleep(0.5)
                    st.rerun()

                elif s == "error":
                    st.session_state.pop(rj_key, None)
                    st.error(f"Re-judge failed: {rj_status.get('error', 'Unknown error')}")

                else:
                    if current > total:
                        phase_label = "Judging full transcript..."
                        pct = 1.0
                    elif current > 0:
                        phase_label = f"Judging turn {current} / {total}"
                        pct = current / max(total, 1)
                    else:
                        phase_label = "Initializing..."
                        pct = 0.0

                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:12px;'
                        f'padding:10px 16px;margin-bottom:4px;'
                        f'background:rgba(232,125,13,0.08);border:1px solid rgba(232,125,13,0.25);'
                        f'border-radius:5px;">'
                        f'<span style="font-size:0.68rem;font-weight:700;letter-spacing:0.12em;'
                        f'color:#E87D0D;text-transform:uppercase;white-space:nowrap;">Re-judging</span>'
                        f'<span style="font-size:0.88rem;color:var(--ct-text2);flex:1;">{phase_label}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.progress(pct)

                    try:
                        fresh_turns = api_get(f"/runs/{selected}/turns")
                    except Exception:
                        fresh_turns = turns

                    for t in fresh_turns:
                        tn = t.get("turn_number", 0)
                        if t.get("turn_verdict"):
                            _render_turn_card(t, endpoint_name=ep_name, judge_visible=True, rj_state="done")
                        elif tn == current:
                            _render_turn_card(t, endpoint_name=ep_name, judge_visible=False, rj_state="judging")
                        else:
                            _render_turn_card(t, endpoint_name=ep_name, judge_visible=False, rj_state="pending")

                    time.sleep(2)
                    st.rerun()

            else:
                # ── NORMAL TRANSCRIPT VIEW ────────────────────────────────────
                judge_visible = st.toggle(
                    "Show judge analysis",
                    value=st.session_state.get("_judge_visible", True),
                    key=f"_judge_toggle_hist_{selected}",
                )
                st.session_state["_judge_visible"] = judge_visible

                _render_transcript(
                    turns,
                    endpoint_name=ep_name,
                    judge_visible=judge_visible,
                    run_id=selected,
                    allow_analyse=True,
                )

                st.markdown("---")
                with st.expander("⚖ Re-judge with different rules", expanded=False):
                    st.markdown(
                        '<p style="font-size:0.82rem;color:var(--ct-text4);margin:0 0 10px;">'
                        'Apply new evaluation rules to the <em>existing</em> transcript — '
                        'the endpoint is <strong>not</strong> called again. '
                        'All per-turn and overall verdicts are updated in place.</p>',
                        unsafe_allow_html=True,
                    )

                    rj_criteria = st.text_area(
                        "New judge rules",
                        placeholder="e.g. The assistant must always greet the user and confirm the request before answering.",
                        height=120,
                        key=f"_rj_criteria_{selected}",
                    )

                    try:
                        all_llms = _cached("_c_llms", "/llm-configs")
                        rj_judge_llms = [l for l in all_llms if l["role"] in ("judge", "either")]
                    except Exception:
                        rj_judge_llms = []

                    if rj_judge_llms:
                        rj_judge_id = st.selectbox(
                            "Judge LLM",
                            [None] + [l["id"] for l in rj_judge_llms],
                            format_func=lambda i: (
                                f"Same as run ({_find(rj_judge_llms, run.get('judge_llm_id')).get('name', '?')})"
                                if i is None else _find(rj_judge_llms, i)["name"]
                            ),
                            key=f"_rj_judge_{selected}",
                        )
                    else:
                        rj_judge_id = None

                    if run.get("status") == "running":
                        st.warning("Run is still in progress — wait for it to complete before re-judging.")
                    else:
                        if st.button("⚖ Re-judge transcript", key=f"_rj_btn_{selected}", type="primary"):
                            if not rj_criteria.strip():
                                st.error("Enter the new judge rules above before re-judging.")
                            else:
                                rj_payload: dict = {"success_criteria_override": rj_criteria.strip()}
                                if rj_judge_id is not None:
                                    rj_payload["judge_llm_id"] = rj_judge_id
                                try:
                                    result = api_post(f"/runs/{selected}/rejudge", rj_payload)
                                    st.session_state[rj_key] = {"total": result.get("total_turns", 0)}
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Failed to start re-judge: {exc}")

            if run.get("status") == "paused":
                st.markdown("---")
                _render_step_controls(run, key_prefix=f"hist_{selected}")
            elif run.get("status") in ("stopped", "failed"):
                st.markdown("---")
                _render_continue_run_section(run, key_prefix=f"hist_{selected}")

            st.markdown("---")
            st.subheader("Export")

            _tester = (st.session_state.get("tester_name") or "").strip()
            if _tester:
                st.caption(f"Reports will be attributed to tester: **{_tester}**.")
            else:
                st.caption("ℹ No tester name set — add yours in **Settings → Tester** to stamp it on reports.")

            def _export_params(fmt: str) -> dict:
                p = {"format": fmt}
                if _tester:
                    p["tester"] = _tester
                return p

            _ec1, _ec2, _ec3, _ec4 = st.columns(4)

            _run_label  = run.get("name") or f"run-{selected}"
            _safe_label = "".join(ch if ch.isalnum() or ch in "- _" else "_" for ch in _run_label).strip("_")

            if _ec1.button("⬇ Download HTML", key=f"dl_html_{selected}"):
                with st.spinner("Generating HTML report…"):
                    try:
                        with _client() as c:
                            _resp = c.get(f"/runs/{selected}/export", params=_export_params("html"))
                            _resp.raise_for_status()
                        _ec1.download_button(
                            "⬇ Save .html", data=_resp.text,
                            file_name=f"{_safe_label}.html", mime="text/html",
                            key=f"dl_html_save_{selected}",
                        )
                    except Exception as exc:
                        st.error(f"Export failed: {exc}")

            if _ec2.button("⬇ Download Report (.txt)", key=f"dl_txt_{selected}"):
                with st.spinner("Generating report…"):
                    try:
                        with _client() as c:
                            _resp = c.get(f"/runs/{selected}/export", params=_export_params("txt"))
                            _resp.raise_for_status()
                        _ec2.download_button(
                            "⬇ Save report", data=_resp.text,
                            file_name=f"{_safe_label}.txt", mime="text/plain",
                            key=f"dl_txt_save_{selected}",
                        )
                    except Exception as exc:
                        st.error(f"Export failed: {exc}")

            if _ec3.button("⬇ Download JSON", key=f"dl_json_{selected}"):
                with st.spinner("Generating JSON…"):
                    try:
                        with _client() as c:
                            _resp = c.get(f"/runs/{selected}/export", params=_export_params("json"))
                            _resp.raise_for_status()
                        _ec3.download_button(
                            "⬇ Save JSON", data=json.dumps(_resp.json(), indent=2),
                            file_name=f"{_safe_label}.json", mime="application/json",
                            key=f"dl_json_save_{selected}",
                        )
                    except Exception as exc:
                        st.error(f"Export failed: {exc}")

            if _ec4.button("⬇ Download Markdown", key=f"dl_md_{selected}"):
                with st.spinner("Generating markdown…"):
                    try:
                        with _client() as c:
                            _resp = c.get(f"/runs/{selected}/export", params=_export_params("markdown"))
                            _resp.raise_for_status()
                        _ec4.download_button(
                            "⬇ Save .md", data=_resp.text,
                            file_name=f"{_safe_label}.md", mime="text/markdown",
                            key=f"dl_md_save_{selected}",
                        )
                    except Exception as exc:
                        st.error(f"Export failed: {exc}")

            if run.get("status") in ("completed", "stopped", "failed"):
                st.markdown("---")
                _render_conclusion_section(run, llms, key_prefix=f"hist_{selected}")
