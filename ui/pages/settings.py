"""Settings page — theme, config backup, env reference."""

from __future__ import annotations

import json

import streamlit as st

from ui.api import BACKEND_URL, _client, api_put
from ui.state import _bust

# App provenance — shown in the About section.
DEVELOPER = "Mukund Aggarwal"
LAST_MODIFIED = "2026-06-05"


def _save_tester_name() -> None:
    """Persist the tester name to the backend so it survives a browser refresh."""
    val = (st.session_state.get("tester_name") or "").strip()
    try:
        api_put("/app-settings", {"key": "tester_name", "value": val})
    except Exception as exc:
        st.warning(f"Couldn't save tester name: {exc}")


def page_settings() -> None:
    st.title("Settings")

    # ── Tester identity ──────────────────────────────────────────────────────
    st.subheader("Tester")
    _saved_name = (st.session_state.get("tester_name") or "").strip()
    _editing = st.session_state.get("_editing_tester_name", False)

    if _saved_name and not _editing:
        # Display mode — show the saved name prominently with an Edit button
        st.markdown(
            f'<p style="font-size:1.5rem;font-weight:700;margin:0.25rem 0 0.5rem;">'
            f'{_saved_name}</p>',
            unsafe_allow_html=True,
        )
        st.caption("Exported reports will be attributed to this name.")
        if st.button("Edit name", key="_tester_edit_btn"):
            st.session_state["_editing_tester_name"] = True
            st.rerun()
    else:
        # Edit mode — show the text input
        tester_name = st.text_input(
            "Your name (tester)",
            key="tester_name",
            placeholder="e.g. Jane Doe",
            on_change=_save_tester_name,
            help="Included in every downloaded report so reviewers know who ran the test. "
                 "Saved on the backend, so it persists across refreshes.",
        )
        col_save, col_cancel = st.columns([1, 5])
        with col_save:
            if st.button("Save", key="_tester_save_btn", type="primary"):
                _save_tester_name()
                st.session_state["_editing_tester_name"] = False
                st.rerun()
        if _editing:
            with col_cancel:
                if st.button("Cancel", key="_tester_cancel_btn"):
                    st.session_state["_editing_tester_name"] = False
                    st.rerun()
        if not (st.session_state.get("tester_name") or "").strip():
            st.caption("⚠ Not set — exported reports won't show a tester name until you fill this in.")

    st.subheader("Appearance")
    current_theme = st.session_state.get("_theme", "dark")
    new_theme = st.radio(
        "Theme",
        ["dark", "light"],
        index=0 if current_theme == "dark" else 1,
        horizontal=True,
        format_func=lambda t: " Dark" if t == "dark" else "☀ Light",
    )
    if new_theme != current_theme:
        st.session_state["_theme"] = new_theme
        try:
            api_put("/app-settings", {"key": "_theme", "value": new_theme})
        except Exception:
            pass
        st.rerun()

    st.caption(f"Backend URL (used by this UI): {BACKEND_URL}")

    st.subheader("Config backup")
    st.caption(
        "Export all test cases, LLM configs, and endpoint configs as a single JSON file. "
        "The file contains API keys — keep it private. "
        "Import is additive: it only adds records whose name you don't already have. "
        "Your existing configs are never modified or deleted — same-name records in the file are skipped."
    )

    ex_col, im_col = st.columns(2)

    with ex_col:
        if st.button("⬇ Export config bundle", use_container_width=True, type="primary"):
            with st.spinner("Gathering config…"):
                try:
                    with _client() as _c:
                        _r = _c.get("/config/export", timeout=15.0)
                        _r.raise_for_status()
                    st.download_button(
                        "⬇ Save conv_tester_config.json",
                        data=_r.text,
                        file_name="conv_tester_config.json",
                        mime="application/json",
                        use_container_width=True,
                        key="_cfg_dl",
                    )
                except Exception as _exc:
                    st.error(f"Export failed: {_exc}")

    with im_col:
        _upload = st.file_uploader(
            "Import config bundle (.json)",
            type=["json"],
            key="_cfg_upload",
            label_visibility="collapsed",
        )
        if _upload is not None:
            if st.button("⬆ Import", use_container_width=True, type="primary", key="_cfg_import_btn"):
                with st.spinner("Importing…"):
                    try:
                        _bundle = json.loads(_upload.read())
                        with _client() as _c:
                            _r = _c.post("/config/import", json=_bundle, timeout=30.0)
                            _r.raise_for_status()
                        _res = _r.json()
                        _created = _res.get("created", {})
                        _skipped = _res.get("skipped", {})
                        _errors  = _res.get("errors", [])
                        _lines = []
                        for _k, _label in [
                            ("test_cases", "Test cases"),
                            ("llm_configs", "LLM configs"),
                            ("endpoint_configs", "Endpoints"),
                        ]:
                            _c_list = _created.get(_k, [])
                            _s_list = _skipped.get(_k, [])
                            if _c_list:
                                _lines.append(f"**{_label}** created: {', '.join(_c_list)}")
                            if _s_list:
                                _lines.append(f"**{_label}** skipped (already exist): {', '.join(_s_list)}")
                        if _errors:
                            for _e in _errors:
                                st.warning(f"⚠ {_e}")
                        if _lines:
                            st.success("\n\n".join(_lines))
                            _bust("_c_tcs", "_c_eps", "_c_llms")
                        else:
                            st.info("Nothing to import — all records already exist.")
                    except Exception as _exc:
                        st.error(f"Import failed: {_exc}")
        else:
            st.caption("Upload a bundle file above, then click Import.")

    st.subheader("About")
    st.markdown(
        f"""
| | |
|---|---|
| **Developer** | {DEVELOPER} |
| **Last modified** | {LAST_MODIFIED} |
        """
    )
