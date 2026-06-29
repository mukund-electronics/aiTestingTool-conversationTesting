"""Configs page — Endpoints, LLMs, and Test Cases tabs."""

from __future__ import annotations

import json

import streamlit as st

from ui.api import api_delete, api_get, api_post, api_put
from ui.components.shared import _build_extractors, _find, _html_table, _run_extraction
from ui.parsers import _inject_user_query_placeholder, _parse_curl
from ui.state import (
    _bust,
    _cached,
    _clear_keys,
    _maybe_reset,
    _maybe_show_toast,
    _saved_toast,
)


def page_configs() -> None:
    st.title("Configs")
    _maybe_show_toast()

    tab_ep, tab_llm, tab_tc, tab_xfer = st.tabs(["Endpoints", "LLMs", "Test Cases", "📦 Export / Import"])

    # ── Endpoints ────────────────────────────────────────────────────────────
    with tab_ep:
        st.subheader("Endpoint configs")
        try:
            eps = _cached("_c_eps", "/endpoint-configs")
        except Exception as e:
            st.error(f"Failed to load: {e}")
            eps = []

        if eps:
            st.markdown(
                _html_table(
                    ["#", "ID", "Name", "Protocol", "Method", "URL", "Auth"],
                    [[i + 1, e["id"], e["name"], e.get("protocol", "http"),
                      e["http_method"] if e.get("protocol", "http") == "http" else "—",
                      e["url"], e["auth_type"]] for i, e in enumerate(eps)],
                ),
                unsafe_allow_html=True,
            )

        with st.expander("➕ Create new endpoint" if not eps else "➕ Create / ✏️ Edit endpoint",
                         expanded=not eps):

            edit_id = st.selectbox(
                "Edit existing (or leave as '— new —' to create)",
                options=[None] + [e["id"] for e in eps],
                format_func=lambda i: "— new —" if i is None else f"#{i}  {_find(eps, i)['name']}",
                key="ep_edit",
            )
            preset: dict = _find(eps, edit_id) if edit_id else {}
            existing_ext: dict = preset.get("response_extractors", {})

            if st.session_state.get("_ep_prev") != edit_id:
                if edit_id and preset:
                    _other_ext = {k: v for k, v in existing_ext.items() if k != "reply"}
                    st.session_state["ep_name"]       = preset.get("name", "")
                    st.session_state["ep_url"]        = preset.get("url", "")
                    st.session_state["ep_protocol"]   = preset.get("protocol", "http")
                    st.session_state["ep_method"]     = preset.get("http_method", "POST")
                    st.session_state["ep_headers"]    = json.dumps(preset.get("headers", {}), indent=2)
                    st.session_state["ep_template"]   = preset.get("request_body_template", '{"query": "{{user_query}}"}')
                    st.session_state["ep_auth_type"]  = preset.get("auth_type", "none")
                    st.session_state["ep_auth_value"] = preset.get("auth_value", "")
                    st.session_state["ep_reply_path"] = existing_ext.get("reply", "$.answer")
                    st.session_state["ep_extractors"] = json.dumps(_other_ext, indent=2) if _other_ext else "{}"
                else:
                    _clear_keys("ep_name", "ep_url", "ep_protocol", "ep_method", "ep_headers",
                                "ep_template", "ep_auth_type", "ep_auth_value",
                                "ep_reply_path", "ep_extractors")
                _clear_keys("ep_sample_json", "_ep_curl_ok", "_ep_curl_field", "ep_curl_input")
                st.session_state["_ep_prev"] = edit_id

            # ── Import from cURL ──
            st.markdown("#### Import from cURL")
            st.caption("Paste a cURL command and the form will be filled automatically.")
            curl_input = st.text_area(
                "cURL command",
                key="ep_curl_input",
                height=110,
                placeholder='curl -X POST https://api.example.com/chat \\\n  -H "Authorization: Bearer sk-..." \\\n  -H "Content-Type: application/json" \\\n  -d \'{"message": "Hello", "session_id": "abc"}\'',
                label_visibility="collapsed",
            )
            if st.button("⚡ Parse cURL", key="ep_curl_btn"):
                raw = (curl_input or "").strip()
                if not raw:
                    st.warning("Paste a cURL command first.")
                else:
                    try:
                        parsed = _parse_curl(raw)
                        if not parsed["url"]:
                            st.error("Could not extract a URL from the cURL command.")
                        else:
                            template_raw = parsed["request_body"] or "{}"
                            template_filled, detected_field = _inject_user_query_placeholder(template_raw)
                            st.session_state["ep_url"]        = parsed["url"]
                            st.session_state["ep_protocol"]   = parsed.get("protocol", "http")
                            st.session_state["ep_method"]     = parsed["http_method"]
                            st.session_state["ep_headers"]    = json.dumps(parsed["headers"], indent=2) if parsed["headers"] else "{}"
                            st.session_state["ep_template"]   = template_filled
                            st.session_state["ep_auth_type"]  = parsed["auth_type"]
                            st.session_state["ep_auth_value"] = parsed["auth_value"]
                            st.session_state["_ep_curl_ok"]   = True
                            st.session_state["_ep_curl_field"] = detected_field
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Parse failed: {exc}")

            if st.session_state.get("_ep_curl_ok"):
                detected = st.session_state.get("_ep_curl_field")
                if detected:
                    st.success(
                        f"✅ cURL imported — URL, headers, auth, and body are filled in.  \n"
                        f"Field **`{detected}`** was automatically set to `{{{{user_query}}}}`. "
                        f"Verify it's the right field in **Request body template** below."
                    )
                else:
                    st.warning(
                        "✅ cURL imported — URL, headers, and auth are filled in.  \n"
                        "⚠️ **Action needed:** In the **Request body template** below, replace the value of the "
                        "field that carries the user message with `{{user_query}}`."
                    )

            st.markdown("---")

            st.markdown("#### Bot reply field")
            st.caption(
                "The JSONPath to the text the bot says. "
                "This is what goes into the transcript and what the **judge evaluates**."
            )
            reply_path = st.text_input(
                "Reply JSONPath _*_",
                value=existing_ext.get("reply", "$.answer"),
                key="ep_reply_path",
                placeholder="e.g.  $.answer  or  $.data.message",
            )
            with st.expander("🔍 Test extraction against a sample response"):
                sample_json_str = st.text_area(
                    "Paste a sample JSON response from your endpoint",
                    height=160, key="ep_sample_json",
                    placeholder='{\n  "answer": "Hi, how can I help?",\n  "intent": "greeting"\n}',
                )
                if st.button("Extract", key="ep_extract_btn") and sample_json_str.strip():
                    try:
                        sample = json.loads(sample_json_str)
                        results = _run_extraction(
                            sample,
                            _build_extractors(reply_path,
                                              st.session_state.get("ep_extractors", "{}")),
                        )
                        for k, v in results.items():
                            label = "✅ **reply** (→ judge sees this)" if k == "reply" else f"`{k}`"
                            st.write(f"{label}: `{v}`")
                        if "reply" not in results:
                            st.warning(f"`{reply_path}` matched nothing.")
                    except json.JSONDecodeError as exc:
                        st.error(f"Invalid JSON: {exc}")
                    except Exception as exc:
                        st.error(f"Extraction error: {exc}")

            st.markdown("---")

            with st.form("ep_form"):
                protocols = ["http", "websocket"]
                protocol = st.selectbox(
                    "Protocol",
                    protocols,
                    index=protocols.index(preset.get("protocol", "http")),
                    key="ep_protocol",
                    help="HTTP — standard REST/JSON over HTTPS. WebSocket — persistent ws:// or wss:// connection.",
                )
                name = st.text_input("Name _*_", value=preset.get("name", ""), key="ep_name")
                _url_help = (
                    "WebSocket URL — must start with ws:// (plain) or wss:// (TLS)."
                    if protocol == "websocket"
                    else None
                )
                url = st.text_input("URL _*_", value=preset.get("url", ""), key="ep_url",
                                    help=_url_help)
                if protocol == "http":
                    methods = ["POST", "GET", "PUT", "PATCH", "DELETE"]
                    method = st.selectbox("HTTP method", methods,
                                          index=methods.index(preset.get("http_method", "POST")),
                                          key="ep_method")
                else:
                    st.caption("HTTP method is not applicable for WebSocket endpoints.")
                    method = "POST"
                headers_json = st.text_area(
                    "Headers (JSON)",
                    value=json.dumps(preset.get("headers", {}), indent=2),
                    height=80,
                    key="ep_headers",
                    help='e.g. {"X-IMEI": "355967152308808", "X-BIC-ID": "BIC002"}',
                )
                _template_label = (
                    "Message template  ({{user_query}}, {{session_id}}, {{history}}, {{turn_number}})"
                    if protocol == "websocket"
                    else "Request body template  ({{user_query}}, {{session_id}}, {{history}}, {{turn_number}})"
                )
                template = st.text_area(
                    _template_label,
                    value=preset.get("request_body_template", '{"query": "{{user_query}}"}'),
                    height=120,
                    key="ep_template",
                )
                other_ext = {k: v for k, v in existing_ext.items() if k != "reply"}
                st.markdown("**Additional extractors** (session_id, end_flag, custom — optional)")
                extractors_json = st.text_area(
                    "Extra extractors (JSON: name → JSONPath)",
                    value=json.dumps(other_ext, indent=2) if other_ext else "{}",
                    height=90, key="ep_extractors",
                    help='Special: "session_id" persists across turns; "end_flag" stops run when truthy.',
                )
                st.markdown("---")
                auth_types = ["none", "bearer", "api_key", "basic"]
                auth_type = st.selectbox(
                    "Auth type", auth_types,
                    index=auth_types.index(preset.get("auth_type", "none")),
                    key="ep_auth_type",
                )
                auth_value = st.text_input(
                    "Auth value", value=preset.get("auth_value", ""), type="password",
                    key="ep_auth_value",
                    help="Bearer token / API key / 'user:pass' for basic",
                )
                c1, c2 = st.columns(2)
                timeout = c1.number_input("Timeout (s)", 1, 600,
                                          int(preset.get("timeout_seconds", 30)))
                retries = c2.number_input("Max retries", 0, 10,
                                          int(preset.get("max_retries", 2)))
                ba, bb, _ = st.columns([1, 1, 4])
                save_btn   = ba.form_submit_button("💾 Save", type="primary")
                delete_btn = bb.form_submit_button("🗑 Delete") if edit_id else None

            if save_btn:
                if not reply_path.strip():
                    st.error("Reply JSONPath is required — enter the JSONPath to the bot's reply text (e.g. `$.answer`).")
                elif not name.strip():
                    st.error("Name is required.")
                elif not url.strip():
                    st.error("URL is required.")
                else:
                    with st.spinner("Saving…"):
                        try:
                            extra = json.loads(extractors_json or "{}")
                            extra["reply"] = reply_path.strip()
                            body = {
                                "name": name.strip(), "url": url.strip(),
                                "protocol": protocol, "http_method": method,
                                "headers": json.loads(headers_json or "{}"),
                                "request_body_template": template,
                                "response_extractors": extra,
                                "auth_type": auth_type, "auth_value": auth_value,
                                "timeout_seconds": int(timeout), "max_retries": int(retries),
                            }
                            if edit_id:
                                api_put(f"/endpoint-configs/{edit_id}", body)
                                _saved_toast("Endpoint config updated.")
                            else:
                                api_post("/endpoint-configs", body)
                                _saved_toast("Endpoint config created.")
                            _bust("_c_eps")
                            _clear_keys("ep_edit", "_ep_prev",
                                        "_ep_curl_ok", "_ep_curl_field", "ep_curl_input")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Save failed: {exc}")

            if delete_btn:
                with st.spinner("Deleting…"):
                    api_delete(f"/endpoint-configs/{edit_id}")
                _bust("_c_eps")
                _clear_keys("ep_edit", "_ep_prev")
                _saved_toast("Endpoint config deleted.")
                st.rerun()

    # ── LLMs ─────────────────────────────────────────────────────────────────
    with tab_llm:
        st.subheader("LLM configs")
        st.info(
            "Works with **any** OpenAI-compatible API — OpenAI and Anthropic in the cloud, "
            "and self-hosted / local models via **LM Studio, Ollama, vLLM, LocalAI**, or "
            "other providers (Groq, Together, OpenRouter, DeepSeek, Mistral, …). "
            "For those, set a **Base URL** and leave the API key blank if the server doesn't need one. "
            "Cloud keys are stored in the database (encrypted if `SECRET_KEY` is set in `.env`) "
            "and never displayed after saving."
        )

        try:
            llms = _cached("_c_llms", "/llm-configs")
        except Exception as e:
            st.error(f"Failed to load: {e}")
            llms = []

        if llms:
            st.markdown(
                _html_table(
                    ["#", "ID", "Name", "Provider", "Model", "Base URL", "Role", "Key set"],
                    [[i + 1, l["id"], l["name"], l["provider"], l["model"],
                      l.get("base_url") or "— (cloud)", l["role"],
                      "✓" if l["has_api_key"] else "—"] for i, l in enumerate(llms)],
                ),
                unsafe_allow_html=True,
            )

        with st.expander("➕ Create new LLM" if not llms else "➕ Create / ✏️ Edit LLM",
                         expanded=not llms):

            edit_id = st.selectbox(
                "Edit existing (or leave as '— new —' to create)",
                options=[None] + [l["id"] for l in llms],
                format_func=lambda i: "— new —" if i is None else f"#{i}  {_find(llms, i)['name']}",
                key="llm_edit",
            )
            _maybe_reset("_llm_prev", edit_id)
            preset = _find(llms, edit_id) if edit_id else {}

            with st.expander("📡 Common Base URLs (local & hosted)"):
                st.markdown(
                    "Leave **Base URL** blank for the OpenAI / Anthropic cloud. "
                    "For anything else, set it (the path usually ends in `/v1`):\n\n"
                    "| Provider | Base URL | API key |\n"
                    "|---|---|---|\n"
                    "| LM Studio (local) | `http://localhost:1234/v1` | not needed |\n"
                    "| Ollama (local) | `http://localhost:11434/v1` | not needed |\n"
                    "| vLLM / LocalAI (local) | `http://localhost:8000/v1` | not needed |\n"
                    "| Groq | `https://api.groq.com/openai/v1` | required |\n"
                    "| Together | `https://api.together.xyz/v1` | required |\n"
                    "| OpenRouter | `https://openrouter.ai/api/v1` | required |\n"
                    "| DeepSeek | `https://api.deepseek.com/v1` | required |\n\n"
                    "Self-hosting on another machine? Use its address, e.g. "
                    "`http://192.168.1.50:1234/v1`."
                )

            key_label = (
                "API key  (leave blank to keep the existing key, or if the server needs none)"
                if preset else "API key  (leave blank for a local server without auth)"
            )

            with st.form("llm_form"):
                name = st.text_input("Name _*_", value=preset.get("name", ""))
                cp, cm = st.columns(2)
                provider = cp.text_input(
                    "Provider _*_", value=preset.get("provider", "openai"),
                    help="openai · anthropic · or any label for an OpenAI-compatible server "
                         "(lmstudio, ollama, vllm, groq, together, openrouter, deepseek, mistral, …). "
                         "Anything other than 'anthropic' is treated as OpenAI-compatible.",
                )
                model = cm.text_input(
                    "Model _*_", value=preset.get("model", "gpt-4o-mini"),
                    help="The model name your provider/server expects, e.g. gpt-4o-mini, "
                         "claude-sonnet-4-6, llama-3.1-8b-instruct, qwen2.5-7b-instruct.",
                )
                base_url = st.text_input(
                    "Base URL", value=preset.get("base_url") or "",
                    placeholder="blank for OpenAI/Anthropic cloud · e.g. http://localhost:1234/v1",
                    help="Set this for local or third-party OpenAI-compatible servers. "
                         "Leave blank for the OpenAI / Anthropic cloud.",
                )
                api_key = st.text_input(key_label, value="", type="password")
                c1, c2 = st.columns(2)
                temperature = c1.slider("Temperature", 0.0, 2.0,
                                        float(preset.get("temperature", 0.7)), 0.05)
                max_tokens  = c2.number_input("Max tokens", 1, 200_000,
                                              int(preset.get("max_tokens", 1024)))
                roles = ["simulator", "judge", "either"]
                role = st.selectbox(
                    "Role", roles,
                    index=roles.index(preset.get("role", "either")),
                    help='"simulator" generates user messages · "judge" evaluates transcripts · "either" does both',
                )
                ba, bb, _ = st.columns([1, 1, 4])
                save_btn   = ba.form_submit_button("💾 Save", type="primary")
                delete_btn = bb.form_submit_button("🗑 Delete") if edit_id else None

            if save_btn:
                # Cloud providers need a key; a Base URL (local/self-hosted) means
                # the key is usually optional.
                needs_key = (
                    not base_url.strip()
                    and provider.strip().lower() in ("openai", "anthropic", "claude")
                )
                if not name.strip() or not provider.strip() or not model.strip():
                    st.error("Name, Provider, and Model are required.")
                elif not edit_id and needs_key and not api_key.strip():
                    st.error(
                        "An API key is required for the OpenAI / Anthropic cloud. "
                        "For a local server, set a Base URL instead and leave the key blank."
                    )
                else:
                    with st.spinner("Saving…"):
                        try:
                            body: dict = {
                                "name": name, "provider": provider.strip(), "model": model,
                                "base_url": base_url.strip() or None,
                                "temperature": float(temperature),
                                "max_tokens": int(max_tokens), "role": role,
                            }
                            if api_key.strip():
                                body["api_key"] = api_key.strip()
                            if edit_id:
                                api_put(f"/llm-configs/{edit_id}", body)
                                _saved_toast("LLM config updated.")
                            else:
                                api_post("/llm-configs", body)
                                _saved_toast("LLM config created.")
                            _bust("_c_llms")
                            _clear_keys("llm_edit", "_llm_prev")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Save failed: {exc}")

            if delete_btn:
                with st.spinner("Deleting…"):
                    api_delete(f"/llm-configs/{edit_id}")
                _bust("_c_llms")
                _clear_keys("llm_edit", "_llm_prev")
                _saved_toast("LLM config deleted.")
                st.rerun()

    # ── Test Cases ────────────────────────────────────────────────────────────
    with tab_tc:
        st.subheader("Test cases")
        try:
            tcs = _cached("_c_tcs", "/test-cases")
        except Exception as e:
            st.error(f"Failed to load: {e}")
            tcs = []

        with st.expander("➕ Create new test case" if not tcs else "➕ Create / ✏️ Edit test case",
                         expanded=st.session_state.get("_tc_form_open", not bool(tcs))):

            _pending = st.session_state.pop("_tc_edit_pending", None)
            if _pending is not None:
                st.session_state["tc_edit"] = _pending

            edit_id = st.selectbox(
                "Edit existing (or leave as '— new —' to create)",
                options=[None] + [t["id"] for t in tcs],
                format_func=lambda i: "— new —" if i is None else f"#{i}  {_find(tcs, i)['name']}",
                key="tc_edit",
            )
            _maybe_reset("_tc_prev", edit_id, f"tc_criteria_{edit_id}")
            preset = _find(tcs, edit_id) if edit_id else {}

            criteria_key = f"tc_criteria_{edit_id}"
            if criteria_key not in st.session_state:
                st.session_state[criteria_key] = list(preset.get("eval_criteria") or [])

            st.markdown("#### Evaluation criteria")
            st.caption(
                "Define named dimensions the judge scores independently. "
                "Weights are normalized automatically — they don't need to sum to 1."
            )
            current_criteria: list[dict] = st.session_state[criteria_key]
            to_delete = None
            for idx, crit in enumerate(current_criteria):
                cols = st.columns([3, 4, 1, 0.5])
                crit["name"] = cols[0].text_input(
                    "Criterion name", value=crit.get("name", ""),
                    key=f"crit_name_{edit_id}_{idx}", label_visibility="collapsed",
                    placeholder="e.g. Answers the question",
                )
                crit["description"] = cols[1].text_input(
                    "Description", value=crit.get("description", ""),
                    key=f"crit_desc_{edit_id}_{idx}", label_visibility="collapsed",
                    placeholder="What the bot should do for this criterion",
                )
                crit["weight"] = cols[2].number_input(
                    "Weight", value=float(crit.get("weight", 1.0)),
                    min_value=0.0, max_value=10.0, step=0.05,
                    key=f"crit_wt_{edit_id}_{idx}", label_visibility="collapsed",
                )
                if cols[3].button("✕", key=f"crit_del_{edit_id}_{idx}"):
                    to_delete = idx
            if to_delete is not None:
                st.session_state[criteria_key].pop(to_delete)
                st.rerun()
            if st.button("＋ Add criterion", key=f"crit_add_{edit_id}"):
                st.session_state[criteria_key].append({"name": "", "description": "", "weight": 1.0})
                st.rerun()

            total_w = sum(float(c.get("weight", 0)) for c in current_criteria if c.get("name", "").strip())
            if current_criteria and any(c.get("name", "").strip() for c in current_criteria):
                if abs(total_w - 1.0) < 0.01:
                    st.success(f"Weights sum to {total_w:.2f} ✓", icon="✅")
                else:
                    st.warning(f"Weights sum to {total_w:.2f} — will be normalized on scoring.")

            st.markdown("---")

            with st.form("tc_form"):
                name        = st.text_input("Name _*_", value=preset.get("name", ""))
                description = st.text_area("Description", value=preset.get("description", ""), height=60)
                usecase = st.text_area(
                    "Usecase / goal _*_  (what the simulated user is trying to achieve)",
                    value=preset.get("usecase", ""), height=90,
                )
                persona = st.text_area(
                    "Persona  (character the simulated user plays)",
                    value=preset.get("persona", ""), height=70,
                )
                facts_text = st.text_area(
                    "Known facts  (one per line — revealed only when relevant or asked)",
                    value="\n".join(preset.get("known_facts", []) or []), height=90,
                )
                success_criteria = st.text_area(
                    "Success criteria _*_  (used by the judge LLM to evaluate the transcript)",
                    value=preset.get("success_criteria", ""), height=90,
                )
                starting_query = st.text_input(
                    "Starting query  (optional — used verbatim as turn 1, skips simulator)",
                    value=preset.get("starting_query", ""),
                )
                c1, c2 = st.columns(2)
                max_turns = c1.number_input("Max turns", 1, 200, int(preset.get("max_turns", 10)))
                modes = ["multi_turn", "single_turn"]
                mode = c2.selectbox("Mode", modes,
                                    index=modes.index(preset.get("mode", "multi_turn")))
                pass_threshold = st.slider(
                    "Pass threshold  (visual reference — judge still decides pass/fail)",
                    0.0, 1.0, float(preset.get("pass_threshold") or 0.7), step=0.05,
                )
                ba, bb, _ = st.columns([1, 1, 4])
                save_btn   = ba.form_submit_button("💾 Save", type="primary")
                delete_btn = bb.form_submit_button("🗑 Delete") if edit_id else None

            if save_btn:
                with st.spinner("Saving…"):
                    try:
                        clean_criteria = [
                            c for c in st.session_state.get(criteria_key, [])
                            if c.get("name", "").strip()
                        ]
                        body = {
                            "name": name, "description": description,
                            "usecase": usecase, "persona": persona,
                            "known_facts": [l.strip() for l in facts_text.splitlines() if l.strip()],
                            "success_criteria": success_criteria,
                            "starting_query": starting_query,
                            "max_turns": int(max_turns), "mode": mode,
                            "eval_criteria": clean_criteria or None,
                            "pass_threshold": float(pass_threshold),
                        }
                        if edit_id:
                            api_put(f"/test-cases/{edit_id}", body)
                            _saved_toast("Test case updated.")
                        else:
                            api_post("/test-cases", body)
                            _saved_toast("Test case created.")
                        _bust("_c_tcs")
                        st.session_state.pop(criteria_key, None)
                        st.session_state.pop("_tc_form_open", None)
                        _clear_keys("tc_edit", "_tc_prev")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

            if delete_btn:
                st.session_state["_tc_delete_pending"] = edit_id

            _tc_del_pending = st.session_state.get("_tc_delete_pending")
            if _tc_del_pending and _tc_del_pending == edit_id:
                tc_name = preset.get("name", f"#{edit_id}")
                st.warning(
                    f"**Delete '{tc_name}'?**  \n"
                    f"This permanently removes the test case and **all its runs and turn data** "
                    f"from storage. This cannot be undone.",
                    icon="⚠️",
                )
                _dc1, _dc2, _ = st.columns([1, 1, 5])
                if _dc1.button("✅ Yes, delete", key="_tc_del_confirm", type="primary"):
                    with st.spinner("Deleting…"):
                        try:
                            api_delete(f"/test-cases/{edit_id}")
                            _bust("_c_tcs")
                            st.session_state.pop(criteria_key, None)
                            st.session_state.pop("_tc_delete_pending", None)
                            st.session_state.pop("_tc_form_open", None)
                            _clear_keys("tc_edit", "_tc_prev")
                            _saved_toast(f"Test case '{tc_name}' and all its runs deleted.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Delete failed: {exc}")
                if _dc2.button("❌ Cancel", key="_tc_del_cancel"):
                    st.session_state.pop("_tc_delete_pending", None)
                    st.rerun()

        if tcs:
            st.markdown(
                _html_table(
                    ["#", "Name", "Mode", "Turns"],
                    [[i + 1, tc["name"],
                      "multi" if tc["mode"] == "multi_turn" else "single",
                      tc["max_turns"]] for i, tc in enumerate(tcs)],
                ),
                unsafe_allow_html=True,
            )

            _sel_tc_id = st.selectbox(
                "Select a test case to edit / rename / delete",
                options=[None] + [t["id"] for t in tcs],
                format_func=lambda i: "— none —" if i is None else f"#{i}  {_find(tcs, i)['name']}",
                key="_tc_tbl_pick",
            )
            _sel_tc = next((t for t in tcs if t["id"] == _sel_tc_id), None)

            if _sel_tc:
                _tc_ren = st.session_state.get("_tc_tbl_ren") == _sel_tc_id
                _tc_del = st.session_state.get("_tc_tbl_del") == _sel_tc_id

                if _tc_ren:
                    _nv = st.text_input("New name", value=_sel_tc["name"], key=f"_tc_rnv_{_sel_tc_id}")
                    _r1, _r2, _ = st.columns([1, 1, 8])
                    if _r1.button("💾 Save", key=f"_tc_rsv_{_sel_tc_id}", type="primary"):
                        if _nv.strip():
                            try:
                                api_put(f"/test-cases/{_sel_tc_id}", {"name": _nv.strip()})
                                _bust("_c_tcs")
                                st.session_state.pop("_tc_tbl_ren", None)
                                _saved_toast(f"Renamed to '{_nv.strip()}'.")
                                st.rerun()
                            except Exception as _exc:
                                st.error(f"Rename failed: {_exc}")
                    if _r2.button("✖ Cancel", key=f"_tc_rcl_{_sel_tc_id}"):
                        st.session_state.pop("_tc_tbl_ren", None)
                        st.rerun()
                elif _tc_del:
                    st.warning(
                        f"Delete **'{_sel_tc['name']}'**?  \n"
                        "This permanently removes the test case and all its runs.",
                        icon="⚠️",
                    )
                    _d1, _d2, _ = st.columns([1, 1, 6])
                    if _d1.button("✅ Yes, delete", key=f"_tc_dcf_{_sel_tc_id}", type="primary"):
                        try:
                            api_delete(f"/test-cases/{_sel_tc_id}")
                            _bust("_c_tcs")
                            st.session_state.pop("_tc_tbl_del", None)
                            _saved_toast(f"'{_sel_tc['name']}' and all its runs deleted.")
                            st.rerun()
                        except Exception as _exc:
                            st.error(f"Delete failed: {_exc}")
                    if _d2.button("❌ Cancel", key=f"_tc_dca_{_sel_tc_id}"):
                        st.session_state.pop("_tc_tbl_del", None)
                        st.rerun()
                else:
                    _a1, _a2, _a3, _ = st.columns([1, 1, 1, 6])
                    if _a1.button("📝 Edit", key=f"_tc_eb_{_sel_tc_id}", use_container_width=True):
                        st.session_state["_tc_edit_pending"] = _sel_tc_id
                        st.session_state["_tc_form_open"] = True
                        st.rerun()
                    if _a2.button("✏️ Rename", key=f"_tc_reb_{_sel_tc_id}", use_container_width=True):
                        st.session_state["_tc_tbl_ren"] = _sel_tc_id
                        st.rerun()
                    if _a3.button("🗑 Delete", key=f"_tc_deb_{_sel_tc_id}", use_container_width=True):
                        st.session_state["_tc_tbl_del"] = _sel_tc_id
                        st.rerun()
            else:
                st.caption("Pick a test case above to edit, rename or delete.")

    # ── Export / Import ───────────────────────────────────────────────────────
    with tab_xfer:
        # ── Selective Export ──────────────────────────────────────────────────
        st.subheader("Selective Export")
        st.caption(
            "Pick any combination of endpoints, LLMs, and test cases, "
            "then export them together as a single JSON bundle."
        )

        try:
            _xp_eps  = _cached("_c_eps",  "/endpoint-configs")
        except Exception:
            _xp_eps  = []
        try:
            _xp_llms = _cached("_c_llms", "/llm-configs")
        except Exception:
            _xp_llms = []
        try:
            _xp_tcs  = _cached("_c_tcs",  "/test-cases")
        except Exception:
            _xp_tcs  = []

        _sel_eps = st.multiselect(
            "Endpoints",
            options=[e["id"] for e in _xp_eps],
            format_func=lambda i: _find(_xp_eps, i).get("name", str(i)),
            key="_xp_sel_eps",
            placeholder="Select endpoint configs to export…",
        )
        _sel_llms = st.multiselect(
            "LLMs",
            options=[l["id"] for l in _xp_llms],
            format_func=lambda i: _find(_xp_llms, i).get("name", str(i)),
            key="_xp_sel_llms",
            placeholder="Select LLM configs to export…",
        )
        _sel_tcs = st.multiselect(
            "Test Cases",
            options=[t["id"] for t in _xp_tcs],
            format_func=lambda i: _find(_xp_tcs, i).get("name", str(i)),
            key="_xp_sel_tcs",
            placeholder="Select test cases to export…",
        )

        _any_sel = bool(_sel_eps or _sel_llms or _sel_tcs)
        _xp_col, _ = st.columns([2, 6])
        if _xp_col.button(
            "⬇ Export selected",
            disabled=not _any_sel,
            type="primary",
            use_container_width=True,
            key="_xp_export_btn",
        ):
            with st.spinner("Building export bundle…"):
                try:
                    _full = api_get("/config/export")
                    _sel_ep_names  = {e["name"] for e in _xp_eps  if e["id"] in _sel_eps}
                    _sel_llm_names = {l["name"] for l in _xp_llms if l["id"] in _sel_llms}
                    _sel_tc_names  = {t["name"] for t in _xp_tcs  if t["id"] in _sel_tcs}

                    _partial = {
                        "version":          _full.get("version", 1),
                        "exported_at":      _full.get("exported_at", ""),
                        "test_cases":       [x for x in _full.get("test_cases",       []) if x["name"] in _sel_tc_names],
                        "llm_configs":      [x for x in _full.get("llm_configs",      []) if x["name"] in _sel_llm_names],
                        "endpoint_configs": [x for x in _full.get("endpoint_configs", []) if x["name"] in _sel_ep_names],
                    }
                    _n = (len(_partial["test_cases"]) + len(_partial["llm_configs"])
                          + len(_partial["endpoint_configs"]))
                    _types = (["endpoints"] if _sel_eps else []) + (["llms"] if _sel_llms else []) + (["test_cases"] if _sel_tcs else [])
                    _suffix = "_".join(_types) if _types else "config"
                    st.download_button(
                        f"⬇ Save bundle  ({_n} item{'s' if _n != 1 else ''})",
                        data=json.dumps(_partial, indent=2, ensure_ascii=False),
                        file_name=f"conv_tester_{_suffix}.json",
                        mime="application/json",
                        use_container_width=True,
                        key="_xp_dl_btn",
                    )
                except Exception as _exc:
                    st.error(f"Export failed: {_exc}")

        st.markdown("---")

        # ── Import ────────────────────────────────────────────────────────────
        st.subheader("Import")
        st.caption(
            "Upload a bundle (full or partial) to add new records. "
            "Import is additive — records whose name already exists are skipped, "
            "never overwritten or deleted."
        )

        _imp_file = st.file_uploader(
            "Drop a .json bundle here",
            type=["json"],
            key="_xp_import_upload",
            label_visibility="collapsed",
        )
        if _imp_file is not None:
            if st.button("⬆ Import bundle", type="primary", key="_xp_import_btn"):
                with st.spinner("Importing…"):
                    try:
                        _bundle_data = json.loads(_imp_file.read())
                        with _client() as _hx:
                            _ir = _hx.post("/config/import", json=_bundle_data, timeout=30.0)
                            _ir.raise_for_status()
                        _res     = _ir.json()
                        _created = _res.get("created", {})
                        _skipped = _res.get("skipped", {})
                        _errors  = _res.get("errors", [])
                        _lines: list[str] = []
                        for _k, _label in [
                            ("test_cases",       "Test cases"),
                            ("llm_configs",      "LLM configs"),
                            ("endpoint_configs", "Endpoints"),
                        ]:
                            _c_list = _created.get(_k, [])
                            _s_list = _skipped.get(_k, [])
                            if _c_list:
                                _lines.append(f"**{_label}** created: {', '.join(_c_list)}")
                            if _s_list:
                                _lines.append(f"**{_label}** skipped (already exist): {', '.join(_s_list)}")
                        for _e in _errors:
                            st.warning(f"⚠ {_e}")
                        if _lines:
                            st.success("\n\n".join(_lines))
                            _bust("_c_tcs", "_c_eps", "_c_llms")
                        else:
                            st.info("Nothing to import — all records already exist.")
                    except Exception as _exc:
                        st.error(f"Import failed: {_exc}")
