"""Batch Run page — launch N parallel copies of the same test and review results."""

from __future__ import annotations

import io
import json
import time
import zipfile

import streamlit as st

from ui.api import _client, api_delete, api_get, api_patch, api_post
from ui.components.run_summary import _render_run_summary
from ui.components.shared import (
    _cell,
    _find,
    _h,
    _render_run_marker_controls,
    _row_tint,
    _score_bar_html,
    _status_pill,
    _table_header,
    _tint,
    _turn_breakdown_cell,
    _turn_result_cell,
    _verdict_pill,
)
from ui.components.transcript import _render_transcript
from ui.components.ws_logs import render_ws_logs_panel


# Runtime placeholders substituted by the runner — not selectable as per-run overrides.
_RUNNER_PLACEHOLDERS = {
    "{{user_query}}", "{{session_id}}", "{{history}}", "{{turn_number}}",
}

# Download formats offered for runs/batches: (api format, button label, mime, file ext).
_EXPORT_FORMATS = [
    ("html",     "HTML",     "text/html",        "html"),
    ("txt",      "Report",   "text/plain",       "txt"),
    ("json",     "JSON",     "application/json", "json"),
    ("markdown", "Markdown", "text/markdown",    "md"),
]


def _tester_name() -> str:
    """Tester name set in Settings → Tester, stamped into exports."""
    return (st.session_state.get("tester_name") or "").strip()


def _safe(label: str) -> str:
    """Filesystem-safe slug for download filenames."""
    return "".join(ch if ch.isalnum() or ch in "- _" else "_" for ch in label).strip("_") or "run"


def _fetch_export(run_id: int, fmt: str) -> str:
    """Fetch one run's export in the given format, returning the file content."""
    params: dict = {"format": fmt}
    tester = _tester_name()
    if tester:
        params["tester"] = tester
    with _client() as c:
        r = c.get(f"/runs/{run_id}/export", params=params)
        r.raise_for_status()
    return json.dumps(r.json(), indent=2) if fmt == "json" else r.text


def _render_run_export_buttons(run_id: int, safe_label: str, key_prefix: str) -> None:
    """Per-run download row: one button per format (click → generate → Save)."""
    cols = st.columns(len(_EXPORT_FORMATS))
    for col, (fmt, label, mime, ext) in zip(cols, _EXPORT_FORMATS):
        if col.button(f"⬇ {label}", key=f"{key_prefix}_dl_{fmt}_{run_id}", use_container_width=True):
            with st.spinner(f"Generating {label}…"):
                try:
                    data = _fetch_export(run_id, fmt)
                    col.download_button(
                        "⬇ Save", data=data,
                        file_name=f"{safe_label}.{ext}", mime=mime,
                        key=f"{key_prefix}_dlsave_{fmt}_{run_id}",
                    )
                except Exception as exc:
                    st.error(f"Export failed: {exc}")


def _render_full_batch_download(batch: dict, run_ids: list[int], key_prefix: str) -> None:
    """Download the whole batch as a single .zip — one report file per run, in
    the chosen format. Built client-side so no batch-specific backend is needed."""
    safe_batch = _safe(batch.get("name") or f"batch-{batch.get('id')}")
    fcol, bcol = st.columns([1.4, 2])
    fmt = fcol.selectbox(
        "Format",
        [f[0] for f in _EXPORT_FORMATS],
        format_func=lambda f: dict((x[0], x[1]) for x in _EXPORT_FORMATS)[f],
        key=f"{key_prefix}_zipfmt",
        label_visibility="collapsed",
    )
    ext = dict((f[0], f[3]) for f in _EXPORT_FORMATS)[fmt]
    if bcol.button("⬇ Download full batch (.zip)", key=f"{key_prefix}_zipbtn", use_container_width=True):
        with st.spinner(f"Building batch archive ({len(run_ids)} runs)…"):
            try:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, rid in enumerate(run_ids, 1):
                        zf.writestr(f"run_{i:02d}_id{rid}.{ext}", _fetch_export(rid, fmt))
                bcol.download_button(
                    "⬇ Save .zip", data=buf.getvalue(),
                    file_name=f"{safe_batch}.zip", mime="application/zip",
                    key=f"{key_prefix}_zipsave", use_container_width=True,
                )
            except Exception as exc:
                st.error(f"Batch export failed: {exc}")


def _flatten_static_keys(obj: dict, prefix: str = "") -> list[str]:
    """Return dot-notation leaf keys whose values are not runner-managed placeholders."""
    keys: list[str] = []
    for k, v in obj.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_flatten_static_keys(v, full))
        elif not (isinstance(v, str) and v.strip() in _RUNNER_PLACEHOLDERS):
            keys.append(full)
    return keys


def page_batch() -> None:
    st.title("Batch Run")
    tab_run, tab_results = st.tabs(["▶ Run Batch", "📊 Batch Results"])

    with tab_run:
        _tab_run()

    with tab_results:
        _tab_results()


# ── Tab 1: Launch & Monitor ───────────────────────────────────────────────────

def _tab_run() -> None:
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

    # ── Live monitor (shown instead of the form when a batch is active) ──────
    # Showing both form and monitor simultaneously caused confusion: the form's
    # slider/override rows displayed a different count than the running batch.
    _live_run_ids: list[int] = st.session_state.get("_batch_run_ids", [])
    if _live_run_ids:
        _live_runs_data: dict[int, dict] = {}
        _live_turns_data: dict[int, list] = {}
        for _rid in _live_run_ids:
            try:
                _live_runs_data[_rid] = api_get(f"/runs/{_rid}")
                _live_turns_data[_rid] = api_get(f"/runs/{_rid}/turns")
            except Exception:
                pass

        _live_n = len(_live_run_ids)
        _live_any_running = any(
            _live_runs_data.get(_rid, {}).get("status") == "running"
            for _rid in _live_run_ids
        )
        _live_name    = st.session_state.get("_batch_name", "Batch")
        _live_ep      = st.session_state.get("_batch_ep_name", "Bot")
        _live_ep_is_ws = st.session_state.get("_batch_ep_is_ws", False)

        hcol, clear_col = st.columns([5, 1])
        _icon   = "⏳" if _live_any_running else "✓"
        _run_lbl = f"{_live_n} run{'s' if _live_n != 1 else ''}"
        _suffix = f"running… ({_run_lbl})" if _live_any_running else f"completed ({_run_lbl})"
        hcol.subheader(f"{_icon}  {_live_name} — {_suffix}")

        if clear_col.button("✕ Clear", key="_batch_clear_btn"):
            for _k in ("_batch_run_ids", "_batch_id", "_batch_name", "_batch_ep_name", "_batch_ep_is_ws"):
                st.session_state.pop(_k, None)
            st.rerun()

        _render_batch_table(
            _live_run_ids, _live_runs_data, _live_turns_data, _live_n, _live_ep,
            key_prefix="live",
            tc_map={t["id"]: t["name"] for t in tcs},
            ep_is_ws=_live_ep_is_ws,
        )

        if not _live_any_running:
            _render_batch_aggregate(_live_runs_data, _live_n)
            # Offer to start a new batch now that this one is done.
            if st.button("＋ New Batch", key="_batch_new_btn", type="primary"):
                for _k in ("_batch_run_ids", "_batch_id", "_batch_name", "_batch_ep_name", "_batch_ep_is_ws"):
                    st.session_state.pop(_k, None)
                st.rerun()

        # Auto-refresh every 2 s while any run is still active.
        if _live_any_running:
            time.sleep(2)
            st.rerun()

        return  # do not render the form while a batch is active

    # ── Config form ──────────────────────────────────────────────────────────
    batch_name = st.text_input(
        "Batch name _*_",
        placeholder="e.g. Stress test v1",
        key="_brun_name",
    )

    c1, c2 = st.columns(2)
    tc_id = c1.selectbox(
        "Test case",
        [t["id"] for t in tcs],
        format_func=lambda i: _find(tcs, i)["name"],
        key="_brun_tc",
    )
    ep_id = c1.selectbox(
        "Endpoint",
        [e["id"] for e in eps],
        format_func=lambda i: _find(eps, i)["name"],
        key="_brun_ep",
    )
    sim_id = c2.selectbox(
        "Simulator LLM (generates user messages)",
        [l["id"] for l in sim_llms],
        format_func=lambda i: _find(sim_llms, i)["name"],
        key="_brun_sim",
    )
    judge_id = c2.selectbox(
        "Judge LLM (evaluates transcript at the end)",
        [l["id"] for l in judge_llms],
        format_func=lambda i: _find(judge_llms, i)["name"],
        key="_brun_judge",
    )

    parallel_count = st.slider(
        "Parallel runs — how many times to run this test case simultaneously",
        min_value=1,
        max_value=10,
        value=st.session_state.get("_batch_count_val", 3),
        key="_brun_count",
        help="Each run is an independent asyncio coroutine on the backend event loop — "
             "no threads required. All runs share the same endpoint and LLM config.",
    )

    # ── Per-run test case override ───────────────────────────────────────────
    # When the default (config-level) test case changes, reset every per-run pick
    # to the new default. We *set* session_state (rather than pop + index) because
    # popping a widget key does not clear Streamlit's internal widget value —
    # only writing session_state before the widget renders reliably overrides it.
    _tc_ids = [t["id"] for t in tcs]
    _default_tc_name = _find(tcs, tc_id).get("name", "")
    if st.session_state.get("_btc_last_default") != tc_id:
        st.session_state["_btc_last_default"] = tc_id
        for _k in range(10):
            st.session_state[f"_btc_{_k}"] = tc_id

    with st.expander("Use a different test case per run (optional)", expanded=False):
        st.markdown(
            '<p style="font-size:0.82rem;color:var(--ct-text4);margin:0 0 8px;">'
            "Each run defaults to the test case selected above "
            f"(<strong>{_h(_default_tc_name)}</strong>). "
            "Change any row to run a different test case in that parallel run.</p>",
            unsafe_allow_html=True,
        )
        for _k in range(parallel_count):
            # Guard: ensure a valid default exists before the widget reads it.
            if st.session_state.get(f"_btc_{_k}") not in _tc_ids:
                st.session_state[f"_btc_{_k}"] = tc_id
            _tc_row = st.columns([0.7, 4])
            _tc_row[0].markdown(
                f'<div style="padding-top:6px;font-size:0.82rem;'
                f'color:var(--ct-text4);">Run {_k + 1}</div>',
                unsafe_allow_html=True,
            )
            _tc_row[1].selectbox(
                f"tc_run_{_k}",
                _tc_ids,
                format_func=lambda i: _find(tcs, i)["name"],
                key=f"_btc_{_k}",
                label_visibility="collapsed",
            )

    # ── Per-run body field overrides ─────────────────────────────────────────
    # Reset field selection when the user changes the endpoint.
    if st.session_state.get("_brun_last_ep") != ep_id:
        st.session_state["_brun_last_ep"] = ep_id
        st.session_state.pop("_brun_vary_fields", None)

    _static_fields: list[str] = []
    try:
        _ep_cfg = api_get(f"/endpoint-configs/{ep_id}")
        _tpl_str = _ep_cfg.get("request_body_template") or "{}"
        _tpl_dict = json.loads(_tpl_str)
        if isinstance(_tpl_dict, dict):
            _static_fields = _flatten_static_keys(_tpl_dict)
    except Exception:
        pass

    with st.expander(
        "Vary body fields per run — simulate different devices/users (optional)",
        expanded=bool(st.session_state.get("_brun_vary_fields")),
    ):
        if not _static_fields:
            st.info(
                "The selected endpoint's request body has no static fields to vary "
                "(all values are runtime placeholders like `{{user_query}}`)."
            )
        else:
            st.markdown(
                '<p style="font-size:0.82rem;color:var(--ct-text4);margin:0 0 8px;">'
                "Pick body fields to override per run. Each run gets its own private copy of "
                "the request body template with the values you enter below — "
                "<code>{{user_query}}</code> is still substituted dynamically each turn.</p>",
                unsafe_allow_html=True,
            )
            vary_fields: list[str] = st.multiselect(
                "Fields to vary",
                options=_static_fields,
                default=[
                    f for f in st.session_state.get("_brun_vary_fields", [])
                    if f in _static_fields
                ],
                key="_brun_vary_fields",
                label_visibility="collapsed",
                placeholder="Select body fields to vary per run…",
            )

            if vary_fields:
                st.markdown(
                    '<div style="margin:10px 0 4px;font-size:0.75rem;font-weight:700;'
                    'letter-spacing:0.07em;text-transform:uppercase;color:var(--ct-text4);">'
                    "Enter a value for each parallel run:</div>",
                    unsafe_allow_html=True,
                )
                col_widths = [0.7] + [max(1.0, 4.0 / len(vary_fields))] * len(vary_fields)
                hdr_cols = st.columns(col_widths)
                hdr_cols[0].markdown(
                    '<div style="font-size:0.70rem;font-weight:700;color:var(--ct-text4);">Run</div>',
                    unsafe_allow_html=True,
                )
                for _i, _f in enumerate(vary_fields):
                    hdr_cols[_i + 1].markdown(
                        f'<div style="font-size:0.70rem;font-weight:700;color:var(--ct-text4);">{_f}</div>',
                        unsafe_allow_html=True,
                    )
                for _k in range(parallel_count):
                    row_cols = st.columns(col_widths)
                    row_cols[0].markdown(
                        f'<div style="padding-top:6px;font-size:0.82rem;'
                        f'color:var(--ct-text4);">Run {_k + 1}</div>',
                        unsafe_allow_html=True,
                    )
                    for _i, _field in enumerate(vary_fields):
                        row_cols[_i + 1].text_input(
                            f"run{_k + 1}_{_field}",
                            placeholder=f"value for run {_k + 1}",
                            key=f"_bpov_{_k}_{_field}",
                            label_visibility="collapsed",
                        )


    with st.expander("Override judge rules for this batch (optional)"):
        st.markdown(
            '<p style="font-size:0.82rem;color:var(--ct-text4);margin:0 0 6px;">'
            "Replaces the test case's <em>success criteria</em> for every run in this batch. "
            "Leave blank to use the test case criteria.</p>",
            unsafe_allow_html=True,
        )
        judge_override = st.text_area(
            "Judge rules override",
            placeholder="e.g. The assistant must always respond in under 20 words.",
            height=90,
            label_visibility="collapsed",
            key="_brun_judge_override",
        )

    st.markdown(
        '<div style="margin:16px 0 6px;padding:12px 16px;'
        "background:rgba(232,125,13,0.08);"
        "border:1.5px solid rgba(232,125,13,0.5);"
        'border-radius:8px;">'
        '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.13em;'
        'color:#E87D0D;text-transform:uppercase;margin-bottom:4px;">AI Analysis</div>'
        '<div style="font-size:0.86rem;color:var(--ct-text3);line-height:1.5;">'
        "Each turn and the full transcript are scored by the judge LLM. "
        "Disable for faster runs where only the raw transcript is needed.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    enable_judge = st.toggle("Enable AI judge analysis", value=False, key="_brun_judge_toggle")

    _sel_ep_batch = _find(eps, ep_id)
    ws_connect_delay_batch: float = 2.0
    if _sel_ep_batch.get("protocol") == "websocket":
        st.markdown(
            '<div style="margin:12px 0 6px;padding:12px 16px;'
            "background:rgba(34,197,94,0.05);"
            "border:1.5px solid rgba(34,197,94,0.35);"
            'border-radius:8px;">'
            '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.13em;'
            'color:#22C55E;text-transform:uppercase;margin-bottom:4px;">🔌 WebSocket Connect Delay</div>'
            '<div style="font-size:0.86rem;color:var(--ct-text3);line-height:1.5;">'
            "Seconds to wait after connecting before sending the first message. "
            "Applied once per run, right after the initial handshake.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        ws_connect_delay_batch = st.number_input(
            "Connect delay (seconds)",
            min_value=0.0, max_value=30.0, value=2.0, step=0.5,
            label_visibility="collapsed",
            key="_brun_ws_delay",
        )

    if st.button("▶ Start Batch", type="primary", key="_brun_start"):
        if not batch_name.strip():
            st.error("Please enter a batch name before starting.")
        else:
            try:
                payload: dict = {
                    "name": batch_name.strip(),
                    "count": parallel_count,
                    "test_case_id": tc_id,
                    "endpoint_config_id": ep_id,
                    "simulator_llm_id": sim_id,
                    "judge_llm_id": judge_id,
                    "skip_judge": not enable_judge,
                    "ws_connect_delay_sec": ws_connect_delay_batch,
                }
                if judge_override.strip():
                    payload["judge_criteria_override"] = judge_override.strip()

                # Collect per-run field values from the override grid.
                _vary = st.session_state.get("_brun_vary_fields", [])
                if _vary:
                    _per_run: list[dict] = []
                    for _k in range(parallel_count):
                        _overrides = {
                            _f: st.session_state.get(f"_bpov_{_k}_{_f}", "").strip()
                            for _f in _vary
                            if st.session_state.get(f"_bpov_{_k}_{_f}", "").strip()
                        }
                        _per_run.append(_overrides)
                    payload["per_run_overrides"] = _per_run

                # Collect per-run test case selections (default to config test case).
                _per_run_tcs = [
                    st.session_state.get(f"_btc_{_k}", tc_id)
                    for _k in range(parallel_count)
                ]
                if any(t != tc_id for t in _per_run_tcs):
                    payload["per_run_test_case_ids"] = _per_run_tcs

                result = api_post("/batches", payload)
                _ep_cfg = _find(eps, ep_id)
                st.session_state["_batch_run_ids"]   = result["run_ids"]
                st.session_state["_batch_id"]        = result["batch_id"]
                st.session_state["_batch_name"]      = batch_name.strip()
                st.session_state["_batch_ep_name"]   = _ep_cfg.get("name", "Bot")
                st.session_state["_batch_ep_is_ws"]  = _ep_cfg.get("protocol") == "websocket"
                st.session_state["_batch_count_val"] = parallel_count
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start batch: {e}")


# ── Tab 2: Batch Results ──────────────────────────────────────────────────────

def _tab_results() -> None:
    rcol, _ = st.columns([1, 5])
    if rcol.button("↻ Refresh", key="_bres_refresh"):
        st.rerun()

    try:
        batches = api_get("/batches")
    except Exception as e:
        st.error(f"Failed to load batches: {e}")
        return

    if not batches:
        st.info("No batch runs yet. Go to **▶ Run Batch** to start one.")
        return

    try:
        eps = api_get("/endpoint-configs")
    except Exception:
        eps = []
    try:
        tc_map = {t["id"]: t["name"] for t in api_get("/test-cases")}
    except Exception:
        tc_map = {}

    # ── Multi-select state ───────────────────────────────────────────────────
    _all_batch_ids = [b["id"] for b in batches]
    _bsel_ids = [bid for bid in _all_batch_ids if st.session_state.get(f"_bsel_{bid}", False)]

    # Delete confirmation banner
    _bres_del_pending = st.session_state.get("_bres_del_pending")
    if _bres_del_pending:
        _bdel = _bres_del_pending
        st.warning(
            f"**Delete {len(_bdel)} batch(es)?**  \n"
            "This permanently removes the batch records **and all their child runs and turn data**. Cannot be undone.",
            icon="⚠️",
        )
        _bdc1, _bdc2, _ = st.columns([1.3, 0.9, 6])
        if _bdc1.button("✅ Yes, delete all", key="_bres_del_confirm_btn", type="primary"):
            with st.spinner("Deleting…"):
                for _bid in _bdel:
                    try:
                        api_delete(f"/batches/{_bid}")
                    except Exception:
                        pass
                    st.session_state.pop(f"_bsel_{_bid}", None)
                    st.session_state.pop(f"_bres_exp_{_bid}", None)
            st.session_state.pop("_bres_del_pending", None)
            st.rerun()
        if _bdc2.button("❌ Cancel", key="_bres_del_cancel_btn"):
            st.session_state.pop("_bres_del_pending", None)
            st.rerun()

    # Selection controls: All / None buttons + actions popover
    _bsc1, _bsc2, _bsc3, _ = st.columns([1, 1, 2, 9])
    if _bsc1.button("☑ All", key="_bsel_all", use_container_width=True):
        for _bid in _all_batch_ids:
            st.session_state[f"_bsel_{_bid}"] = True
        st.rerun()
    if _bsc2.button("☐ None", key="_bsel_none", use_container_width=True):
        for _bid in _all_batch_ids:
            st.session_state[f"_bsel_{_bid}"] = False
        st.rerun()
    if _bsel_ids:
        with _bsc3.popover(f"⋮  {len(_bsel_ids)} selected", use_container_width=True):
            st.markdown(f"**{len(_bsel_ids)} batch(es) selected**")
            st.divider()
            if st.button("🗑 Delete selected", key="_bres_menu_del", use_container_width=True,
                         help="Permanently deletes the batches and all their child runs"):
                st.session_state["_bres_del_pending"] = _bsel_ids[:]
                st.rerun()

    # ── Batch table ──────────────────────────────────────────────────────────
    cols_w = [0.25, 0.3, 2.2, 2.0, 0.7, 1.6, 1.8, 0.6]
    _table_header(["", "#", "Batch Name", "Test Case", "Runs", "Endpoint", "Date", ""], cols_w)

    for idx, b in enumerate(batches):
        bid     = b["id"]
        exp_key = f"_bres_exp_{bid}"
        is_exp  = st.session_state.get(exp_key, False)
        ts      = b.get("created_at", "")[:16].replace("T", " ")

        c_cb, c0, c1, c2, c3, c4, c5, c6 = st.columns(cols_w)
        c_cb.checkbox(" ", key=f"_bsel_{bid}", label_visibility="collapsed")
        c0.markdown(_cell(str(idx + 1), weight="600", color="var(--ct-text4)"), unsafe_allow_html=True)
        c1.markdown(_cell(b["name"], weight="600"), unsafe_allow_html=True)
        c2.markdown(_cell(b["test_case_name"]), unsafe_allow_html=True)
        c3.markdown(_cell(str(b["count"])), unsafe_allow_html=True)
        c4.markdown(_cell(b["endpoint_name"], size="0.84rem"), unsafe_allow_html=True)
        c5.markdown(_cell(ts, size="0.84rem", color="var(--ct-text4)"), unsafe_allow_html=True)

        btn_lbl = "▲" if is_exp else "▼"
        if c6.button(btn_lbl, key=f"_bres_btn_{bid}", use_container_width=True):
            st.session_state[exp_key] = not is_exp
            st.rerun()

        if is_exp:
            with st.container():
                _render_batch_detail(b, eps, tc_map)

        st.markdown(
            '<hr style="margin:6px 0;border-color:var(--ct-border);opacity:0.4;">',
            unsafe_allow_html=True,
        )


def _render_batch_detail(b: dict, eps: list[dict], tc_map: dict[int, str] | None = None) -> None:
    """Expanded view under a batch row: aggregate stats + per-run sub-table."""
    bid     = b["id"]
    run_ids = b.get("run_ids", [])
    n       = b["count"]

    if not run_ids:
        st.warning("No run IDs stored for this batch.")
        return

    runs_data: dict[int, dict] = {}
    turns_data: dict[int, list] = {}
    for rid in run_ids:
        try:
            runs_data[rid]  = api_get(f"/runs/{rid}")
            turns_data[rid] = api_get(f"/runs/{rid}/turns")
        except Exception:
            pass

    ep_name  = "Bot"
    ep_is_ws = False
    if runs_data:
        first = next(iter(runs_data.values()))
        ep_id = first.get("endpoint_config_id")
        if ep_id:
            ep_cfg   = _find(eps, ep_id)
            ep_name  = ep_cfg.get("name", "Bot")
            ep_is_ws = ep_cfg.get("protocol") == "websocket"

    with st.container():
        st.markdown(
            '<div style="border-left:3px solid var(--ct-border);'
            "padding:0 0 4px 16px;margin:4px 0 10px 8px;",
            unsafe_allow_html=True,
        )
        _render_batch_aggregate(runs_data, n)

        # Full-batch download (one .zip of per-run reports). Per-run downloads
        # live inside each run's expanded "View" panel in the table below.
        st.markdown(
            '<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.07em;'
            'text-transform:uppercase;color:var(--ct-text4);margin:2px 0 4px;">'
            "Download</div>",
            unsafe_allow_html=True,
        )
        _render_full_batch_download(b, run_ids, key_prefix=f"res_{bid}")

        _render_batch_table(
            run_ids, runs_data, turns_data, n, ep_name,
            key_prefix=f"res_{bid}", tc_map=tc_map,
            ep_is_ws=ep_is_ws,
        )
        st.markdown("</div>", unsafe_allow_html=True)


# ── Shared rendering helpers ──────────────────────────────────────────────────

def _render_batch_table(
    run_ids: list[int],
    runs_data: dict[int, dict],
    turns_data: dict[int, list],
    n: int,
    ep_name: str,
    key_prefix: str = "",
    tc_map: dict[int, str] | None = None,
    ep_is_ws: bool = False,
) -> None:
    """Compact table of all runs in a batch with inline expand.

    Columns (left→right): index (with colour marker), test case, run status,
    total turns, per-turn pass/fail breakdown, a turn-level Result rollup that
    reads FAILED if *any* turn failed, the judge verdict, the score, a tester
    "Reviewed" checkbox, a colour marker, and the expand button. The Reviewed
    flag and colour are persisted on the run via PATCH so they survive refreshes.
    """
    cols_w = [0.45, 1.55, 0.95, 0.5, 0.85, 0.9, 0.95, 1.0, 0.55, 1.2, 0.8]
    _table_header(
        ["#", "Test Case", "Status", "Turns", "Turn ✓/✗", "Result",
         "Verdict", "Score", "Done", "Mark", ""],
        cols_w,
    )

    for idx, rid in enumerate(run_ids):
        run    = runs_data.get(rid, {})
        turns  = turns_data.get(rid, [])
        sts    = run.get("status", "running")
        verdict = run.get("verdict")
        score  = run.get("verdict_score")

        # Only show pass/fail counts once at least one turn carries a verdict —
        # either from the AI judge or a manual mark. When AI analysis was off and
        # nothing has been judged yet, every turn_verdict is None and we leave the
        # column blank until a tester marks at least one turn (typically a fail).
        # A turn counts as failed only on an explicit "fail" verdict; every other
        # turn (passed, inconclusive, or not-yet-judged) counts as success.
        has_verdict = any(t.get("turn_verdict") for t in turns)
        failed_t = sum(1 for t in turns if t.get("turn_verdict") == "fail")

        _tid = run.get("test_case_id")
        _tc_label = (tc_map or {}).get(_tid) or run.get("name", f"Run {idx + 1}/{n}")

        # Row tint — a light wash of the tester's marker colour across the row.
        tint = _row_tint(run)

        (c0, c1, c2, c3, c_tr, c_res,
         c4, c5, c_done, c_mark, c6) = st.columns(cols_w)

        c0.markdown(_tint(_cell(str(idx + 1), weight="600", color="var(--ct-text4)"), tint), unsafe_allow_html=True)
        c1.markdown(_tint(_cell(_h(_tc_label), size="0.85rem"), tint), unsafe_allow_html=True)
        c2.markdown(_tint(_status_pill(sts), tint), unsafe_allow_html=True)
        c3.markdown(_tint(_cell(str(len(turns))), tint), unsafe_allow_html=True)

        # Per-turn pass/fail breakdown + rollup (shared with the History table).
        c_tr.markdown(_turn_breakdown_cell(len(turns), failed_t, has_verdict, tint), unsafe_allow_html=True)
        c_res.markdown(_turn_result_cell(len(turns), failed_t, has_verdict, tint), unsafe_allow_html=True)

        if verdict:
            c4.markdown(_tint(_verdict_pill(verdict), tint), unsafe_allow_html=True)
        else:
            c4.markdown(_tint(_cell("—", color="var(--ct-text5)"), tint), unsafe_allow_html=True)
        if score is not None:
            c5.markdown(_tint(_score_bar_html(score), tint), unsafe_allow_html=True)
        else:
            c5.markdown(_tint(_cell("—", color="var(--ct-text5)"), tint), unsafe_allow_html=True)

        # Reviewed checkbox + colour marker (persisted; shared with History).
        _render_run_marker_controls(c_done, c_mark, run, rid, key_prefix)

        exp_key = f"_bexp_{key_prefix}_{rid}"
        is_exp  = st.session_state.get(exp_key, False)
        if c6.button(
            "▲ Hide" if is_exp else "▼ View",
            key=f"_bexpbtn_{key_prefix}_{rid}",
            use_container_width=True,
        ):
            st.session_state[exp_key] = not is_exp
            st.rerun()

        if is_exp:
            with st.container():
                st.markdown(
                    '<div style="border-left:3px solid var(--ct-border);'
                    "padding:12px 16px;margin:4px 0 10px 20px;"
                    'background:var(--ct-surface,#F8F8F8);border-radius:0 4px 4px 0;">',
                    unsafe_allow_html=True,
                )
                jv_key = f"_bjv_{key_prefix}_{rid}"
                jv = st.toggle(
                    "Show judge analysis",
                    value=st.session_state.get(jv_key, True),
                    key=f"_bjvt_{key_prefix}_{rid}",
                )
                st.session_state[jv_key] = jv
                _render_run_summary(run, run_analysis=run.get("run_analysis"))
                _render_transcript(
                    turns,
                    endpoint_name=ep_name,
                    judge_visible=jv,
                    run_id=rid,
                    key_prefix=f"{key_prefix}_{rid}",
                )
                if ep_is_ws:
                    with st.expander("🔌 WebSocket Logs", expanded=False):
                        render_ws_logs_panel(rid, key_prefix=f"{key_prefix}_{rid}")
                st.markdown(
                    '<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.07em;'
                    'text-transform:uppercase;color:var(--ct-text4);margin:8px 0 4px;">'
                    "Download this run</div>",
                    unsafe_allow_html=True,
                )
                _render_run_export_buttons(
                    rid, _safe(run.get("name") or f"run-{rid}"), key_prefix=f"{key_prefix}_{rid}",
                )
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            '<hr style="margin:4px 0;border-color:var(--ct-border);opacity:0.35;">',
            unsafe_allow_html=True,
        )


def _render_batch_aggregate(runs_data: dict[int, dict], n: int) -> None:
    """Summary strip: total / passed / failed / avg score / tokens."""
    passed  = sum(1 for r in runs_data.values() if r.get("verdict") == "pass")
    failed  = sum(1 for r in runs_data.values() if r.get("verdict") == "fail")
    scores  = [r["verdict_score"] for r in runs_data.values() if r.get("verdict_score") is not None]
    avg_sc  = sum(scores) / len(scores) if scores else None
    tokens  = sum(r.get("total_tokens", 0) for r in runs_data.values())

    sc_str  = f"{avg_sc:.2f}" if avg_sc is not None else "—"
    cp      = "#22C55E" if passed > 0 else "var(--ct-text5)"
    cf      = "#EF4444" if failed > 0 else "var(--ct-text5)"
    other   = n - passed - failed

    def _stat(label: str, value: str, color: str = "var(--ct-text)") -> str:
        # !important keeps these colours from being overridden by the light
        # theme's global "force dark text on all divs" rule.
        return (
            f'<div style="text-align:center;">'
            f'<div style="font-size:0.66rem;font-weight:700;letter-spacing:0.09em;'
            f'text-transform:uppercase;color:var(--ct-text5) !important;margin-bottom:2px;">{label}</div>'
            f'<div style="font-size:1.05rem;font-weight:700;color:{color} !important;">{value}</div>'
            f"</div>"
        )

    st.markdown(
        '<div style="margin:12px 0 16px;padding:12px 20px;'
        "background:var(--ct-surface,#F8F8F8);border:1px solid var(--ct-border);"
        'border-radius:6px;display:flex;justify-content:space-around;flex-wrap:wrap;gap:8px;">'
        + _stat("Total", str(n))
        + _stat("Passed", str(passed), cp)
        + _stat("Failed", str(failed), cf)
        + _stat("Other", str(other))
        + _stat("Avg Score", sc_str)
        + _stat("Tokens used in this testing", f"{tokens:,}")
        + "</div>",
        unsafe_allow_html=True,
    )


