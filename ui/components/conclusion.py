"""Conclusion report rendering."""

from __future__ import annotations

import streamlit as st

from ui.api import _client
from ui.components.shared import _find, _h


def _render_conclusion(data: dict) -> None:
    """Render a conclusion report dict as styled HTML sections."""
    if data.get("_parse_error"):
        st.error("The LLM returned an unparseable response.")
        st.code(data.get("raw", ""), language=None)
        return

    def _section(label: str, icon: str = "") -> str:
        return (
            f'<div style="font-size:0.68rem;font-weight:700;color:var(--ct-text5);'
            f'text-transform:uppercase;letter-spacing:0.1em;margin:18px 0 6px;">'
            f'{icon}{"  " if icon else ""}{label}</div>'
        )

    def _para(text: str) -> str:
        return (
            f'<p style="font-size:0.88rem;color:var(--ct-text2);line-height:1.6;margin:0 0 6px;">'
            f'{_h(text)}</p>'
        )

    def _list_items(items: list, color: str = "var(--ct-text2)") -> str:
        if not items:
            return ""
        return "<ul style=\"margin:0;padding-left:16px;\">" + "".join(
            f'<li style="font-size:0.85rem;color:{color};margin:3px 0;line-height:1.5;">{_h(str(i))}</li>'
            for i in items
        ) + "</ul>"

    html_parts = ['<div style="background:var(--ct-surface);border:1px solid var(--ct-border);'
                  'border-radius:6px;padding:18px 22px;margin-top:10px;">']

    if data.get("executive_summary"):
        html_parts.append(
            f'<div style="padding:12px 16px;background:var(--ct-surface2);border-left:4px solid var(--ct-accent);'
            f'border-radius:3px;margin-bottom:16px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:var(--ct-accent);'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Executive Summary</div>'
            f'{_para(data["executive_summary"])}</div>'
        )

    if data.get("behavior_overview"):
        html_parts.append(_section("Overall Behaviour", "◈"))
        html_parts.append(_para(data["behavior_overview"]))

    strong = data.get("strong_points") or []
    failures = data.get("failures") or []
    if strong or failures:
        cols_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:10px 0;">'
        if strong:
            cols_html += (
                f'<div><div style="font-size:0.63rem;font-weight:700;color:#22C55E;'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Strong Points</div>'
                f'{_list_items(strong, "#22C55E")}</div>'
            )
        else:
            cols_html += "<div></div>"
        if failures:
            sev_color = {"critical": "#EF4444", "major": "#F59E0B", "minor": "#888888"}
            f_items = ""
            for f in failures:
                t_num = f.get("turn", "?")
                desc  = f.get("description", "")
                sev   = f.get("severity", "minor")
                sc    = sev_color.get(sev, "#888888")
                f_items += (
                    f'<li style="margin:4px 0;font-size:0.85rem;color:var(--ct-text2);line-height:1.5;">'
                    f'<span style="font-size:0.7rem;font-weight:700;color:{sc};text-transform:uppercase;'
                    f'margin-right:4px;">[T{t_num} {sev}]</span>{_h(desc)}</li>'
                )
            cols_html += (
                f'<div><div style="font-size:0.63rem;font-weight:700;color:#EF4444;'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Failures</div>'
                f'<ul style="margin:0;padding-left:16px;">{f_items}</ul></div>'
            )
        cols_html += "</div>"
        html_parts.append(cols_html)

    hallucinations = data.get("hallucinations") or []
    if hallucinations:
        html_parts.append(_section("Hallucinations / Fabrications", "⚠"))
        h_items = ""
        for h in hallucinations:
            t_num   = h.get("turn", "?")
            claimed = h.get("claimed", "")
            issue   = h.get("issue", "")
            h_items += (
                f'<li style="margin:6px 0;font-size:0.85rem;line-height:1.5;">'
                f'<span style="color:var(--ct-accent);font-weight:600;">Turn {t_num}:</span> '
                f'<span style="color:var(--ct-text2);">{_h(claimed)}</span>'
                + (f'<br><span style="font-size:0.78rem;color:var(--ct-text4);">{_h(issue)}</span>' if issue else "")
                + "</li>"
            )
        html_parts.append(f'<ul style="margin:0;padding-left:16px;">{h_items}</ul>')
    else:
        html_parts.append(_section("Hallucinations", "⚠"))
        html_parts.append('<span style="font-size:0.85rem;color:#22C55E;">None detected.</span>')

    off_track = data.get("off_track") or []
    if off_track:
        html_parts.append(_section("Off-Track Responses", "↗"))
        ot_items = ""
        for ot in off_track:
            t_num = ot.get("turn", "?")
            desc  = ot.get("description", "")
            ot_items += (
                f'<li style="margin:4px 0;font-size:0.85rem;color:var(--ct-text2);line-height:1.5;">'
                f'<span style="color:var(--ct-accent);font-weight:600;">Turn {t_num}:</span> {_h(desc)}</li>'
            )
        html_parts.append(f'<ul style="margin:0;padding-left:16px;">{ot_items}</ul>')

    for key, label, icon in [
        ("consistency_analysis",  "Consistency",           "≡"),
        ("communication_quality", "Communication Quality",  "✦"),
        ("task_completion",       "Task Completion",        "✓"),
        ("user_experience",       "User Experience",        "👤"),
    ]:
        if data.get(key):
            html_parts.append(_section(label, icon))
            html_parts.append(_para(data[key]))

    factual = data.get("factual_concerns") or []
    if factual:
        html_parts.append(_section("Factual Concerns", "?"))
        html_parts.append(_list_items(factual, "#F59E0B"))

    critical = data.get("critical_issues") or []
    if critical:
        html_parts.append(_section("Critical Issues", "✕"))
        html_parts.append(_list_items(critical, "#EF4444"))

    recs = data.get("recommendations") or []
    if recs:
        html_parts.append(_section("Recommendations", "→"))
        html_parts.append(_list_items(recs, "#60A5FA"))

    if data.get("conclusion"):
        html_parts.append(
            f'<div style="margin-top:18px;padding:12px 16px;background:var(--ct-surface2);'
            f'border-left:4px solid var(--ct-accent);border-radius:3px;">'
            f'<div style="font-size:0.63rem;font-weight:700;color:var(--ct-accent);'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Conclusion</div>'
            f'{_para(data["conclusion"])}</div>'
        )

    html_parts.append("</div>")
    st.markdown("\n".join(html_parts), unsafe_allow_html=True)

    meta = data.get("_meta", {})
    if meta.get("tokens"):
        st.caption(
            f"Generated by {meta.get('model','?')} · "
            f"{meta['tokens']:,} tokens · ${meta.get('cost_usd', 0):.4f}"
        )


def _render_conclusion_section(run: dict, llms: list, key_prefix: str) -> None:
    """Expandable 'Create Conclusion' section for the Run and History pages."""
    st.subheader("Conclusion")

    judge_llms = [l for l in llms if l["role"] in ("judge", "either")]
    ck_data    = f"_concl_data_{key_prefix}"
    ck_llm     = f"_concl_llm_{key_prefix}"

    col_btn, col_llm, _ = st.columns([1, 2, 3])
    if judge_llms:
        chosen_llm_id = col_llm.selectbox(
            "LLM",
            [None] + [l["id"] for l in judge_llms],
            format_func=lambda i: (
                f"Same as run ({_find(judge_llms, run.get('judge_llm_id')).get('name', '?')})"
                if i is None else _find(judge_llms, i)["name"]
            ),
            key=ck_llm,
            label_visibility="collapsed",
        )
    else:
        chosen_llm_id = None

    if ck_data not in st.session_state and run.get("conclusion"):
        st.session_state[ck_data] = run["conclusion"]

    btn_label = "✦ Re-generate Conclusion" if st.session_state.get(ck_data) else "✦ Create Conclusion"
    if col_btn.button(btn_label, key=f"{key_prefix}_btn", type="primary"):
        with st.spinner("Analysing transcript…"):
            try:
                payload: dict = {}
                if chosen_llm_id is not None:
                    payload["judge_llm_id"] = chosen_llm_id
                with _client() as c:
                    r = c.post(
                        f"/runs/{run['id']}/conclusion",
                        json=payload,
                        timeout=120.0,
                    )
                    r.raise_for_status()
                    st.session_state[ck_data] = r.json()
            except Exception as exc:
                st.error(f"Conclusion failed: {exc}")

    data = st.session_state.get(ck_data)
    if data:
        _render_conclusion(data)
