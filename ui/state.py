"""Session state, cache, and toast helpers."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.api import api_get


def _clear_keys(*keys: str) -> None:
    """Remove widget keys from session_state so value= is respected on next render."""
    for k in keys:
        st.session_state.pop(k, None)


def _maybe_reset(tracker_key: str, current_id: Any, *widget_keys: str) -> None:
    """If the selection changed since last render, wipe the dependent widget states."""
    if st.session_state.get(tracker_key) != current_id:
        _clear_keys(*widget_keys)
        st.session_state[tracker_key] = current_id


def _cached(cache_key: str, path: str) -> list:
    if cache_key not in st.session_state:
        st.session_state[cache_key] = api_get(path)
    return st.session_state[cache_key]


def _bust(*cache_keys: str) -> None:
    for k in cache_keys:
        st.session_state.pop(k, None)


def _saved_toast(msg: str) -> None:
    """Store a toast message to display after the next rerun."""
    st.session_state["_pending_toast"] = msg


def _maybe_show_toast() -> None:
    msg = st.session_state.pop("_pending_toast", None)
    if msg:
        st.toast(msg, icon="✅")
