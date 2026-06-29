"""Single Run page — launch/monitor one run and browse run history in tabs.

Mirrors the Batch Run page (launch + results as two tabs). The two halves live
in their own modules (run.py, history.py); this page just composes them.
"""

from __future__ import annotations

import streamlit as st

from ui.pages.history import page_history
from ui.pages.run import page_run


def page_runs() -> None:
    st.title("Single Run")
    tab_new, tab_history = st.tabs(["▶ New Run", "📜 History"])

    with tab_new:
        page_run()

    with tab_history:
        page_history()
