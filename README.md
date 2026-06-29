# conv-tester

A Python tool for testing **conversational AI endpoints**. It simulates a user (via an LLM) chatting across multiple turns with your chatbot endpoint, then evaluates the conversation against a goal using a second LLM as judge.

- **Backend:** FastAPI + async SQLAlchemy on SQLite
- **UI:** Streamlit (separate process, talks to the backend over HTTP)
- **LLM providers:** OpenAI and Anthropic (pluggable via a small `LLMProvider` protocol)
- **Templating:** Jinja-style `{{variable}}` placeholders inside the request body JSON
- **Extraction:** JSONPath selectors pull the bot's reply, session id, and end-of-conversation flag out of each response

---

## Quick start

### 1. Install (using uv)

```powershell
# from the conv-tester directory
uv sync
```

This installs the runtime deps from `pyproject.toml`. Add `--extra dev` for pytest tools:

```powershell
uv sync --extra dev
```

If you don't have `uv`, regular pip works too:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 2. Configure

```powershell
copy .env.example .env
```

Edit `.env`. At a minimum, set one of `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` so the simulator/judge LLMs can run (you can also store API keys inside an `LLMConfig` row, which overrides the env fallback).

### 3. Run the backend

```powershell
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

The interactive API docs are at `http://127.0.0.1:8000/docs`.

### 4. Run the UI

In a second terminal:

```powershell
uv run streamlit run ui/app.py
```

Streamlit will open `http://localhost:8501`. Make sure `BACKEND_URL` in `.env` (or the environment) points at the FastAPI process.

---

## Concepts

### EndpointConfig
The chatbot endpoint you want to test.

| Field | Notes |
|---|---|
| `url`, `http_method` | Where and how to call the bot |
| `headers` | Static headers (dict) |
| `request_body_template` | A JSON string containing `{{variable}}` placeholders |
| `response_extractors` | Dict of `name → JSONPath` — e.g. `{"reply": "$.data.message"}` |
| `auth_type` | `none` / `bearer` / `api_key` / `basic` |
| `timeout_seconds`, `max_retries` | HTTP behavior |

**Supported template variables:**
- `{{user_query}}` — current turn's user message
- `{{session_id}}` — extracted from a prior response; empty on turn 1
- `{{history}}` — the OpenAI-style messages array so far (`[{"role":"user","content":"..."}, ...]`)
- `{{turn_number}}` — 1-based integer

Templating renders text first (with placeholders JSON-escaped according to context) then parses the result as JSON, so placeholders can sit inside string values *or* as raw values (`{{history}}` becomes an array literal).

**Special extractor keys** the runner watches:
- `reply` — the assistant's text, fed into the transcript
- `session_id` — preserved across turns
- `end_flag` — when truthy (`true`, `"yes"`, `1`, ...) the runner stops with `endpoint_signaled_end`

### LLMConfig
A named LLM endpoint (provider + model + key + sampling params + role). `role` can be `simulator`, `judge`, or `either`.

### TestCase
Defines a scenario:
- `usecase` — the goal the simulated user is trying to achieve
- `persona` — free-text user character
- `known_facts` — list of facts the user "knows" and can reveal when relevant
- `success_criteria` — used by the judge
- `starting_query` — optional override for turn 1 (used verbatim, no LLM call)
- `max_turns`, `mode` (`single_turn` / `multi_turn`)

### TestRun
A single execution of a TestCase against an EndpointConfig with a chosen simulator + judge LLM. Tracks status, verdict, tokens, cost, and optional `max_cost_usd` cap.

### Turn
Per-turn record: user query, raw request, raw response, extracted fields, latency, tokens, errors. Persisted **before** the next turn starts so a crash never loses data.

---

## Runner loop & stop precedence

Per turn:

1. Generate a user query (simulator LLM, or `starting_query` on turn 1)
2. Render `request_body_template` with current variables
3. Call the endpoint (httpx, exponential backoff on 429/5xx)
4. Extract fields via JSONPath
5. Persist a `Turn` row
6. Check stop conditions **in this exact order**:
   1. HTTP error after retries → `endpoint_error`
   2. `end_flag` truthy → `endpoint_signaled_end`
   3. Simulator emitted `<<<DONE>>>` → `goal_achieved`
   4. `turn_number >= max_turns` → `max_turns`
   5. `cost_so_far >= max_cost_usd` → `cost_cap`
7. If not stopping, loop with updated transcript
8. On stop, the judge LLM rates the full transcript → verdict persisted

The loop is an `asyncio.Task` registered in an in-process table; `POST /runs/{id}/stop` cancels it, and the runner writes a `stopped` row on the way down.

---

## API summary

| Method | Path | Purpose |
|---|---|---|
| `GET/POST/PUT/DELETE` | `/endpoint-configs[/...]` | CRUD |
| `GET/POST/PUT/DELETE` | `/llm-configs[/...]` | CRUD |
| `GET/POST/PUT/DELETE` | `/test-cases[/...]` | CRUD |
| `POST` | `/runs` | Start a run (returns immediately; loop runs in background) |
| `GET` | `/runs` | List with `test_case_id`, `status`, `since`, `until`, `limit` filters |
| `GET` | `/runs/{id}` | Run state + verdict |
| `GET` | `/runs/{id}/turns` | All persisted turns |
| `POST` | `/runs/{id}/stop` | Cancel an in-flight run |
| `GET` | `/runs/{id}/export?format=json\|markdown` | Exportable transcript |

---

## End-to-end example: test a public echo bot

Suppose you have an echo endpoint at `https://httpbin.org/anything` that simply echoes back the request body. We can wire it up as if it were a chatbot whose "reply" is whatever it received.

### a) Create an EndpointConfig

```powershell
curl -X POST http://127.0.0.1:8000/endpoint-configs `
  -H "Content-Type: application/json" `
  -d '{
    "name": "httpbin-echo",
    "url": "https://httpbin.org/anything",
    "http_method": "POST",
    "headers": {},
    "request_body_template": "{\"message\": \"{{user_query}}\", \"session_id\": \"{{session_id}}\"}",
    "response_extractors": {
      "reply": "$.json.message",
      "session_id": "$.json.session_id"
    },
    "auth_type": "none",
    "auth_value": "",
    "timeout_seconds": 30,
    "max_retries": 2
  }'
```

> `httpbin.org/anything` returns the request JSON under `$.json`, so the extractor reads back the same `message` we sent — making this a useful smoke-test fixture.

### b) Create an LLMConfig for the simulator

```powershell
curl -X POST http://127.0.0.1:8000/llm-configs `
  -H "Content-Type: application/json" `
  -d '{
    "name": "openai-sim",
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key": "sk-...",
    "temperature": 0.7,
    "max_tokens": 256,
    "role": "either"
  }'
```

Create a second one for the judge if you want (or reuse the same).

### c) Create a TestCase

```powershell
curl -X POST http://127.0.0.1:8000/test-cases `
  -H "Content-Type: application/json" `
  -d '{
    "name": "echo-smoke",
    "description": "Confirm the bot echoes user messages.",
    "usecase": "Get the bot to confirm it can hear you.",
    "persona": "Curious tester saying hello.",
    "known_facts": [],
    "success_criteria": "At least one assistant message contains the same content the user sent.",
    "starting_query": "Hello, bot!",
    "max_turns": 3,
    "mode": "multi_turn"
  }'
```

### d) Start a run

```powershell
curl -X POST http://127.0.0.1:8000/runs `
  -H "Content-Type: application/json" `
  -d '{"test_case_id": 1, "endpoint_config_id": 1, "simulator_llm_id": 1, "judge_llm_id": 1}'
```

Poll `GET /runs/{id}` until `status != "running"`, then read the verdict and turns. Or just open the Streamlit UI's **Run** page and watch turns appear live.

---

## Project layout

```
conv-tester/
├── pyproject.toml
├── .env.example
├── README.md
├── backend/
│   ├── main.py                  # FastAPI app + lifespan
│   ├── config.py                # pydantic-settings
│   ├── db.py                    # async engine + session
│   ├── models/                  # SQLAlchemy ORM
│   ├── schemas/                 # Pydantic request/response
│   ├── services/
│   │   ├── llm/                 # provider protocol + OpenAI/Anthropic adapters
│   │   ├── templating.py        # {{var}} → JSON renderer
│   │   ├── extractor.py         # JSONPath extraction
│   │   ├── endpoint_caller.py   # async httpx caller with retries
│   │   ├── simulator.py         # user-query generation + <<<DONE>>> parsing
│   │   ├── judge.py             # verdict JSON parsing
│   │   └── runner.py            # loop orchestration + cancellation
│   └── api/                     # routers: endpoint_configs, llm_configs, test_cases, runs
├── ui/app.py                    # Streamlit app
└── tests/                       # pytest suite
```

---

## Running the tests

```powershell
uv run pytest -q
```

The suite covers the deterministic parts that don't need a network: template substitution, JSONPath extraction, simulator `<<<DONE>>>` detection, judge JSON parsing, and runner stop-condition precedence.

---

## Out of scope (designed-for-later)

These are intentionally not in v1, but the data model supports them:

- Test suites / batch runs
- Parallel runs across the same backend
- Per-turn assertions beyond the judge verdict
- Step mode / manual query injection
- Cross-run regression comparison
- Authentication on the FastAPI itself

---

## Security notes

- API keys are never logged. The `LLMConfigOut` schema only exposes a `has_api_key` boolean, never the secret.
- The runner stores raw request and response bodies. **Don't put production secrets in your endpoint requests** — those payloads are persisted in SQLite for audit.
- Streamlit is a developer tool. Don't expose it to the public internet without a reverse proxy + auth in front.
