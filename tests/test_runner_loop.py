"""End-to-end smoke tests for the runner's execute_run / resume_run loops.

These drive the full turn loop with fakes (no real LLM or HTTP) against a
throwaway SQLite database, locking in observable behavior so the loop can be
refactored safely. They complement test_runner.py, which only covers the pure
decide_stop precedence function.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.services.runner as runner
from backend.db import Base
from backend.models.endpoint_config import EndpointConfig
from backend.models.llm_config import LLMConfig
from backend.models.test_case import TestCase as CaseModel
from backend.models.test_run import TestRun as RunModel
from backend.models.turn import Turn

# ── fakes ──────────────────────────────────────────────────────────────────


class _Sim:
    def __init__(self, q="user-msg", done=False):
        self.user_query = q
        self.done = done
        self.input_tokens = 1
        self.output_tokens = 1
        self.cost_usd = 0.001


class _Call:
    def __init__(self, reply="bot-reply"):
        self.error = None
        self.status_code = 200
        self.response_json = {"reply": reply}
        self.latency_ms = 5


class _Verdict:
    def __init__(self, result="pass", score=0.9):
        self.result = result
        self.score = score
        self.reasoning = "ok"
        self.criteria_scores = {}
        self.input_tokens = 1
        self.output_tokens = 1
        self.cost_usd = 0.001

    def to_analysis_dict(self):
        return {"result": self.result, "score": self.score}


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def Session(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(runner, "AsyncSessionLocal", maker)
    yield maker
    await engine.dispose()


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    async def fake_sim(*a, **k):
        return _Sim()

    async def fake_call(*a, **k):
        return _Call()

    async def fake_judge_turn(*a, **k):
        return _Verdict()

    async def fake_judge_transcript(*a, **k):
        return _Verdict(result="pass", score=0.95)

    monkeypatch.setattr(runner, "generate_user_query", fake_sim)
    monkeypatch.setattr(runner, "call_endpoint", fake_call)
    monkeypatch.setattr(runner, "judge_turn", fake_judge_turn)
    monkeypatch.setattr(runner, "judge_transcript", fake_judge_transcript)
    monkeypatch.setattr(runner, "build_provider", lambda *a, **k: object())
    monkeypatch.setattr(runner, "render_template", lambda tpl, v: {"q": v.get("user_query", "")})
    monkeypatch.setattr(
        runner, "extract_fields", lambda resp, ex: {"reply": (resp or {}).get("reply", "")}
    )
    monkeypatch.setattr(runner, "build_variables", lambda **k: dict(k))


# ── helpers ────────────────────────────────────────────────────────────────


async def _seed(maker, *, max_turns=2, mode="multi_turn", starting_query="", step_mode=False):
    async with maker() as s:
        tc = CaseModel(
            name="tc",
            usecase="uc",
            success_criteria="crit",
            persona="p",
            known_facts=[],
            starting_query=starting_query,
            max_turns=max_turns,
            mode=mode,
        )
        ep = EndpointConfig(name="ep", url="http://x", request_body_template="{}")
        llm = LLMConfig(name="llm", provider="openai", model="m", api_key="k")
        s.add_all([tc, ep, llm])
        await s.commit()
        run = RunModel(
            test_case_id=tc.id,
            endpoint_config_id=ep.id,
            simulator_llm_id=llm.id,
            judge_llm_id=llm.id,
            status="running",
            step_mode=step_mode,
        )
        s.add(run)
        await s.commit()
        return run.id


async def _turns(maker, run_id):
    async with maker() as s:
        res = await s.execute(
            select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
        )
        return list(res.scalars().all())


async def _run(maker, run_id):
    async with maker() as s:
        return await s.get(RunModel, run_id)


# ── tests ──────────────────────────────────────────────────────────────────


async def test_execute_run_max_turns(Session):
    run_id = await _seed(Session, max_turns=2)
    await runner.execute_run(run_id)

    turns = await _turns(Session, run_id)
    assert [t.turn_number for t in turns] == [1, 2]
    assert turns[0].extracted_reply == "bot-reply"
    assert turns[0].turn_verdict == "pass"

    run = await _run(Session, run_id)
    assert run.status == "completed"
    assert run.stop_reason == "max_turns"
    assert run.verdict == "pass"
    assert run.total_tokens > 0
    assert run.finished_at is not None


async def test_execute_run_starting_query_used_verbatim(Session):
    run_id = await _seed(Session, max_turns=1, starting_query="HELLO-VERBATIM")
    await runner.execute_run(run_id)
    turns = await _turns(Session, run_id)
    assert turns[0].user_query == "HELLO-VERBATIM"


async def test_execute_run_single_turn_stops_after_one(Session):
    run_id = await _seed(Session, max_turns=5, mode="single_turn")
    await runner.execute_run(run_id)
    turns = await _turns(Session, run_id)
    assert len(turns) == 1
    run = await _run(Session, run_id)
    assert run.status == "completed"


async def test_execute_run_goal_achieved(Session, monkeypatch):
    async def done_sim(*a, **k):
        return _Sim(done=True)

    monkeypatch.setattr(runner, "generate_user_query", done_sim)
    run_id = await _seed(Session, max_turns=5)
    await runner.execute_run(run_id)

    run = await _run(Session, run_id)
    assert run.stop_reason == "goal_achieved"
    assert len(await _turns(Session, run_id)) == 1


async def test_resume_run_appends_turns(Session):
    run_id = await _seed(Session, max_turns=2)
    await runner.execute_run(run_id)
    await runner.resume_run(run_id, additional_turns=2)

    turns = await _turns(Session, run_id)
    assert [t.turn_number for t in turns] == [1, 2, 3, 4]
    run = await _run(Session, run_id)
    assert run.status == "completed"
    assert run.stop_reason == "max_turns"


async def test_resume_run_query_override_used_on_first_resume_turn(Session):
    run_id = await _seed(Session, max_turns=2)
    await runner.execute_run(run_id)
    await runner.resume_run(run_id, additional_turns=1, query_override="RESUME-VERBATIM")

    turns = await _turns(Session, run_id)
    assert turns[2].user_query == "RESUME-VERBATIM"  # turn 3 = first resumed turn
