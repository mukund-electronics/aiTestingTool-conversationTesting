"""Run summary card rendering."""

from __future__ import annotations

import streamlit as st

from ui.components.shared import (
    _STATUS_COLOR,
    _STOP_REASON_LABEL,
    _STOP_REASON_STYLE,
    _h,
    _score_bar_html,
    _score_bar_with_threshold_html,
    _verdict_pill,
)


def _render_run_summary(
    run: dict,
    pass_threshold: float = 0.7,
    run_analysis: dict | None = None,
    stop_detail: str | None = None,
) -> None:
    status = run.get("status", "—")
    verdict = run.get("verdict") or ""
    score = run.get("verdict_score")
    s_bg, s_fg = _STATUS_COLOR.get(status, ("var(--ct-surface)", "var(--ct-text)"))

    status_pill = (
        f'<span style="padding:2px 10px;border-radius:3px;background:{s_bg};'
        f'color:{s_fg};font-weight:600;font-size:0.78rem;letter-spacing:0.05em;">{status.upper()}</span>'
    )
    verdict_pill = _verdict_pill(verdict) if verdict else '<span style="color:#666666">—</span>'
    score_html = _score_bar_html(score) if score is not None else '<span style="color:#666666">—</span>'

    summary_html = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;'
        f'background:var(--ct-surface);border:1px solid var(--ct-border);border-radius:4px;padding:14px 18px;margin-bottom:14px;">'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:var(--ct-text5);text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:6px;">Status</div>{status_pill}</div>'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:var(--ct-text5);text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:6px;">Verdict</div>{verdict_pill}</div>'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:var(--ct-text5);text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:6px;">Score</div>'
        f'{_score_bar_with_threshold_html(score, pass_threshold)}</div>'
        f'<div><div style="font-size:0.68rem;font-weight:600;color:var(--ct-text5);text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:6px;">Tokens used in this testing</div>'
        f'<span style="font-size:1rem;font-weight:700;color:var(--ct-text);">{run.get("total_tokens", 0):,}</span></div>'
        f'</div>'
    )
    st.markdown(summary_html, unsafe_allow_html=True)

    if run.get("stop_reason"):
        _sr = run["stop_reason"]
        _sr_label = _STOP_REASON_LABEL.get(_sr, _sr.replace("_", " ").title())
        _sr_bg, _sr_fg = _STOP_REASON_STYLE.get(_sr, ("rgba(136,136,136,0.10)", "#888888"))
        _detail_html = (
            f'<div style="margin-top:5px;font-size:0.82rem;color:{_sr_fg};opacity:0.85;">'
            f'{_h(stop_detail)}</div>'
            if stop_detail else ""
        )
        st.markdown(
            f'<div style="padding:10px 14px;margin:8px 0;background:{_sr_bg};'
            f'border:1px solid {_sr_fg}33;border-radius:4px;">'
            f'<span style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:{_sr_fg};">Run stopped</span>'
            f'<span style="font-size:0.9rem;font-weight:600;color:{_sr_fg};margin-left:10px;">'
            f'{_sr_label}</span>'
            f'{_detail_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if run.get("verdict_reasoning"):
        st.markdown(
            f'<div style="padding:10px 14px;background:var(--ct-surface);border-radius:3px;'
            f'border-left:3px solid var(--ct-accent);font-size:0.88rem;color:var(--ct-text2);margin:8px 0;">'
            f'{run["verdict_reasoning"]}</div>',
            unsafe_allow_html=True,
        )

    if run_analysis:
        rows_html = ""
        for cname, cdata in run_analysis.items():
            ts = cdata.get("transcript_score")
            avg_t = cdata.get("avg_turn_score")
            tr = cdata.get("transcript_reasoning", "")
            wt = cdata.get("weight", 0)
            turn_scores = cdata.get("turn_scores") or []
            avg_text = f"{avg_t:.2f}" if avg_t is not None else "—"
            spark = " ".join(
                ("▲" if s >= 0.7 else "▼" if s < 0.4 else "◆") for s in turn_scores
            ) if turn_scores else "—"
            rows_html += (
                f'<tr style="border-bottom:1px solid var(--ct-border2);">'
                f'<td style="padding:6px 8px 6px 0;font-size:0.83rem;font-weight:600;'
                f'color:var(--ct-text);white-space:nowrap;">{cname}'
                f'<span style="margin-left:6px;font-size:0.7rem;font-weight:400;'
                f'color:var(--ct-text5);">w:{wt:.2f}</span></td>'
                f'<td style="padding:6px 12px;min-width:130px;">{_score_bar_html(ts)}</td>'
                f'<td style="padding:6px 8px;font-size:0.76rem;color:var(--ct-text4);white-space:nowrap;">'
                f'avg/turn: {avg_text}  {spark}</td>'
                f'<td style="padding:6px 0;font-size:0.78rem;color:var(--ct-text4);">{tr}</td>'
                f'</tr>'
            )
        st.markdown(
            f'<div style="margin:12px 0;background:var(--ct-surface);border:1px solid var(--ct-border);'
            f'border-radius:4px;padding:14px;">'
            f'<div style="font-size:0.7rem;font-weight:600;color:var(--ct-text5);'
            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">'
            f'Per-Criterion Summary</div>'
            f'<table style="width:100%;border-collapse:collapse;">{rows_html}</table>'
            f'</div>',
            unsafe_allow_html=True,
        )
