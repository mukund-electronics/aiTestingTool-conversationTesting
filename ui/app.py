"""Streamlit UI for conv-tester. Talks to the FastAPI backend over HTTP."""

from __future__ import annotations

import streamlit as st

from ui.api import BACKEND_URL, api_get
from ui.theme import _DARK_CSS, _LIGHT_CSS

VERSION = "2.0.0"

st.set_page_config(page_title="conv-tester", layout="wide", page_icon="▶")

# Hide Streamlit's auto-generated sidebar nav (triggered by ui/pages/* being detected as pages)
st.markdown(
    '<style>[data-testid="stSidebarNav"]{display:none!important}</style>',
    unsafe_allow_html=True,
)

# Hydrate persisted settings (tester name + theme) from the backend once per
# session. Must happen BEFORE the theme CSS is applied so a refresh picks up
# the user's saved theme rather than defaulting to dark every time.
if "_theme_loaded" not in st.session_state:
    try:
        _settings = api_get("/app-settings")
        st.session_state["tester_name"] = _settings.get("tester_name", "")
        st.session_state["_theme"] = _settings.get("_theme", "dark")
    except Exception:
        st.session_state.setdefault("tester_name", "")
        st.session_state.setdefault("_theme", "dark")
    st.session_state["_theme_loaded"] = True

# Apply theme
_theme = st.session_state.get("_theme", "dark")
st.markdown(_DARK_CSS if _theme == "dark" else _LIGHT_CSS, unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown(
    '<div style="padding:0 4px 16px;border-bottom:1px solid var(--ct-border);margin-bottom:16px;">'
    '<span style="font-size:1.05rem;font-weight:700;color:var(--ct-accent);letter-spacing:-0.01em;">AI conv</span>'
    '<span style="font-size:1.05rem;font-weight:700;color:var(--ct-text);letter-spacing:-0.01em;">-Testing Tool</span>'
    # '<span style="font-size:0.65rem;color:var(--ct-text5);margin-left:8px;">▶ CLI</span>'
    '</div>',
    unsafe_allow_html=True,
)

PAGE = st.sidebar.radio(
    "Navigate",
    ["Configs", "Single Run", "Batch Run", "Settings"],
    label_visibility="collapsed",
    key="nav_page",
)
st.sidebar.markdown("---")
st.sidebar.caption(f"backend: {BACKEND_URL}")
try:
    health = api_get("/healthz")
    st.sidebar.success(f"API: {health.get('status', 'ok')}")
except Exception as e:
    st.sidebar.error(f"Backend unreachable: {e}")
st.sidebar.markdown("---")
st.sidebar.caption(f"v{VERSION}")

# ── Router ────────────────────────────────────────────────────────────────────
if PAGE == "Configs":
    from ui.pages.configs import page_configs
    page_configs()
elif PAGE == "Single Run":
    from ui.pages.runs import page_runs
    page_runs()
elif PAGE == "Batch Run":
    from ui.pages.batch import page_batch
    page_batch()
elif PAGE == "Settings":
    from ui.pages.settings import page_settings
    page_settings()
