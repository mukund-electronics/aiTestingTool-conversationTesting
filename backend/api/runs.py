from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import AsyncSessionLocal, get_session
from backend.models.endpoint_config import EndpointConfig
from backend.models.llm_config import LLMConfig
from backend.models.test_case import TestCase
from backend.models.test_run import TestRun
from backend.models.turn import Turn
from backend.schemas.test_run import TestRunCreate, TestRunOut, TestRunUpdate
from backend.schemas.turn import TurnOut
from backend.services.judge import judge_transcript, judge_turn
from backend.services.llm import build_provider
from backend.services.runner import cancel_run, execute_run, register_task, resume_run

router = APIRouter(prefix="/runs", tags=["runs"])


async def _attach_turn_stats(session: AsyncSession, runs: list[TestRun]) -> None:
    """Attach per-run turn-verdict aggregates (turn_total / turn_failed /
    turn_has_verdict) in a single grouped query, so the run list can render the
    ✓/✗ breakdown without an N+1 fetch of every run's turns."""
    ids = [r.id for r in runs]
    if not ids:
        return
    res = await session.execute(
        select(
            Turn.test_run_id,
            func.count().label("total"),
            func.sum(case((Turn.turn_verdict == "fail", 1), else_=0)).label("failed"),
            func.sum(case((Turn.turn_verdict.isnot(None), 1), else_=0)).label("with_verdict"),
        )
        .where(Turn.test_run_id.in_(ids))
        .group_by(Turn.test_run_id)
    )
    stats = {row.test_run_id: row for row in res.all()}
    for r in runs:
        row = stats.get(r.id)
        r.turn_total = int(row.total) if row else 0
        r.turn_failed = int(row.failed or 0) if row else 0
        r.turn_has_verdict = bool(row.with_verdict) if row else False


@router.post("", response_model=TestRunOut, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: TestRunCreate,
    session: AsyncSession = Depends(get_session),
) -> TestRun:
    # Validate references exist.
    tc = await session.get(TestCase, payload.test_case_id)
    if tc is None:
        raise HTTPException(404, "test_case not found")
    ep = await session.get(EndpointConfig, payload.endpoint_config_id)
    if ep is None:
        raise HTTPException(404, "endpoint_config not found")
    sim_llm = await session.get(LLMConfig, payload.simulator_llm_id)
    if sim_llm is None:
        raise HTTPException(404, "simulator_llm not found")
    judge_llm = await session.get(LLMConfig, payload.judge_llm_id)
    if judge_llm is None:
        raise HTTPException(404, "judge_llm not found")

    run = TestRun(
        name=payload.name,
        test_case_id=payload.test_case_id,
        endpoint_config_id=payload.endpoint_config_id,
        simulator_llm_id=payload.simulator_llm_id,
        judge_llm_id=payload.judge_llm_id,
        max_cost_usd=payload.max_cost_usd,
        judge_criteria_override=payload.judge_criteria_override or None,
        skip_judge=payload.skip_judge,
        step_mode=payload.step_mode,
        ws_connect_delay_sec=payload.ws_connect_delay_sec,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    task = asyncio.create_task(execute_run(run.id))
    register_task(run.id, task)

    return run


@router.get("", response_model=list[TestRunOut])
async def list_runs(
    test_case_id: int | None = None,
    status_: str | None = Query(default=None, alias="status"),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[TestRun]:
    stmt = select(TestRun).order_by(TestRun.id.desc()).limit(limit)
    if test_case_id is not None:
        stmt = stmt.where(TestRun.test_case_id == test_case_id)
    if status_ is not None:
        stmt = stmt.where(TestRun.status == status_)
    if since is not None:
        stmt = stmt.where(TestRun.started_at >= since)
    if until is not None:
        stmt = stmt.where(TestRun.started_at <= until)
    res = await session.execute(stmt)
    runs = list(res.scalars().all())
    await _attach_turn_stats(session, runs)
    return runs


@router.get("/{run_id}", response_model=TestRunOut)
async def get_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> TestRun:
    row = await session.get(TestRun, run_id)
    if row is None:
        raise HTTPException(404, "run not found")
    await _attach_turn_stats(session, [row])
    return row


@router.patch("/{run_id}", response_model=TestRunOut)
async def update_run(
    run_id: int,
    payload: TestRunUpdate,
    session: AsyncSession = Depends(get_session),
) -> TestRun:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    fields = payload.model_fields_set
    if payload.name is not None:
        run.name = payload.name
    if "reviewed" in fields and payload.reviewed is not None:
        run.reviewed = payload.reviewed
    if "marker_color" in fields:
        # Empty string or null clears the marker; otherwise store the hex value.
        run.marker_color = payload.marker_color or None
    await session.commit()
    await session.refresh(run)
    return run


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    await session.delete(run)  # cascade="all, delete-orphan" removes turns automatically
    await session.commit()


@router.get("/{run_id}/turns", response_model=list[TurnOut])
async def get_run_turns(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[Turn]:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    res = await session.execute(
        select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
    )
    return list(res.scalars().all())


@router.post("/{run_id}/stop", response_model=TestRunOut)
async def stop_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> TestRun:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status != "running":
        return run
    cancelled = await cancel_run(run_id)
    if not cancelled:
        # Task already gone (process restart?). Mark stopped directly.
        from datetime import timezone

        run.status = "stopped"
        run.stop_reason = "user_stopped"
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()
    # Give the cancellation handler a moment to write the final state.
    for _ in range(20):
        await asyncio.sleep(0.05)
        await session.refresh(run)
        if run.status != "running":
            break
    return run


# ── Continue a stopped run ───────────────────────────────────────────────────

class ContinueRequest(BaseModel):
    additional_turns: int = 5


@router.post("/{run_id}/continue", response_model=TestRunOut)
async def continue_run(
    run_id: int,
    payload: ContinueRequest,
    session: AsyncSession = Depends(get_session),
) -> TestRun:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status == "running":
        raise HTTPException(409, "run is already in progress")
    if run.status not in ("stopped", "failed", "completed", "paused"):
        raise HTTPException(422, f"cannot continue a run with status '{run.status}'")
    if payload.additional_turns < 1 or payload.additional_turns > 100:
        raise HTTPException(422, "additional_turns must be between 1 and 100")

    task = asyncio.create_task(resume_run(run_id, payload.additional_turns))
    register_task(run_id, task)

    # Refresh to get the updated status the task just set
    await asyncio.sleep(0)  # yield so the task can start
    await session.refresh(run)
    return run


# ── Step-mode: advance one turn at a time ────────────────────────────────────

class StepRequest(BaseModel):
    query: str | None = None   # user's (possibly edited) query; None = use pre-generated
    step_mode: bool = True     # False = switch to continuous mode after this turn


@router.post("/{run_id}/step", response_model=TestRunOut)
async def step_run(
    run_id: int,
    payload: StepRequest,
    session: AsyncSession = Depends(get_session),
) -> TestRun:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status != "paused":
        raise HTTPException(422, f"run is not paused (status: '{run.status}')")

    # Update the step_mode flag so the runner knows whether to pause again.
    run.step_mode = payload.step_mode
    await session.commit()

    # Prefer the user-supplied query; fall back to the pre-generated one.
    effective_query = (payload.query or "").strip() or run.next_pending_query or None

    # Always pass the remaining turns to respect test_case.max_turns.
    # resume_run sets effective_max_turns = last_turn_number + additional_turns, so
    # passing remaining = max_turns - turns_done makes effective_max_turns == max_turns.
    # Without this, passing a large constant (e.g. 100) would let the run blow past
    # the test-case limit in both step and continuous modes.
    tc = await session.get(TestCase, run.test_case_id)
    turns_res = await session.execute(
        select(func.count()).select_from(Turn).where(Turn.test_run_id == run_id)
    )
    turns_done = turns_res.scalar() or 0
    remaining = max((tc.max_turns if tc else 10) - turns_done, 1)
    additional = remaining

    task = asyncio.create_task(resume_run(run_id, additional, query_override=effective_query))
    register_task(run_id, task)

    await asyncio.sleep(0)  # yield so the task can update run.status to "running"
    await session.refresh(run)
    return run


# ── Analyse a single turn with AI judge ─────────────────────────────────────

@router.post("/{run_id}/turns/{turn_number}/judge")
async def judge_single_turn(run_id: int, turn_number: int) -> dict:
    """Re-judge one specific turn using the run's judge LLM and criteria.

    The endpoint is NOT called again — only the existing query/reply is analysed.
    Updates the turn row in the DB and returns the new verdict data.
    """
    async with AsyncSessionLocal() as session:
        run = await session.get(TestRun, run_id)
        if run is None:
            raise HTTPException(404, "run not found")

        tc = await session.get(TestCase, run.test_case_id)
        judge_llm = await session.get(LLMConfig, run.judge_llm_id)
        if judge_llm is None:
            raise HTTPException(404, "judge_llm not found")

        res = await session.execute(
            select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
        )
        all_turns = list(res.scalars().all())

        target = next((t for t in all_turns if t.turn_number == turn_number), None)
        if target is None:
            raise HTTPException(404, f"turn {turn_number} not found")
        if not target.user_query or not target.extracted_reply:
            raise HTTPException(422, "turn has no query or reply to analyse")

        history_before: list[dict[str, str]] = []
        for t in all_turns:
            if t.turn_number >= turn_number:
                break
            if t.user_query:
                history_before.append({"role": "user", "content": t.user_query})
            if t.extracted_reply:
                history_before.append({"role": "assistant", "content": t.extracted_reply})

        judge_provider = build_provider(
            judge_llm.provider, judge_llm.model, judge_llm.api_key, judge_llm.base_url
        )
        tv = await judge_turn(
            judge_provider,
            tc,
            turn_number=turn_number,
            user_query=target.user_query,
            bot_reply=target.extracted_reply,
            history_before=history_before,
            temperature=judge_llm.temperature,
            max_tokens=min(judge_llm.max_tokens, 256),
            success_criteria_override=run.judge_criteria_override or None,
        )

        target.turn_verdict = tv.result
        target.turn_score = tv.score
        target.turn_reasoning = tv.reasoning
        target.turn_analysis = tv.to_analysis_dict()
        await session.commit()

        return {
            "turn_number": turn_number,
            "turn_verdict": tv.result,
            "turn_score": tv.score,
            "turn_reasoning": tv.reasoning,
            "turn_analysis": tv.to_analysis_dict(),
        }


# ── Manual verdict override ───────────────────────────────────────────────────

class _ManualVerdictPayload(BaseModel):
    verdict: str | None = None  # "fail" | "pass" | "inconclusive" | None to clear


@router.patch("/{run_id}/turns/{turn_number}/verdict")
async def set_turn_verdict_manual(
    run_id: int,
    turn_number: int,
    payload: _ManualVerdictPayload,
) -> dict:
    """Manually set or clear a turn's verdict without calling the judge LLM."""
    if payload.verdict is not None and payload.verdict not in ("fail", "pass", "inconclusive"):
        raise HTTPException(422, "verdict must be 'fail', 'pass', 'inconclusive', or null")

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Turn).where(
                Turn.test_run_id == run_id,
                Turn.turn_number == turn_number,
            )
        )
        turn = res.scalar_one_or_none()
        if turn is None:
            raise HTTPException(404, "turn not found")

        if payload.verdict is None:
            turn.turn_verdict = None
            turn.turn_score = None
            turn.turn_reasoning = None
        else:
            turn.turn_verdict = payload.verdict
            turn.turn_score = None
            turn.turn_reasoning = "Manually marked by user"

        await session.commit()
        return {"turn_number": turn_number, "turn_verdict": turn.turn_verdict}


# ── Re-judge: background task + status polling ──────────────────────────────

import logging as _logging
_logger = _logging.getLogger(__name__)

# In-memory per-run rejudge state.
# Shape: {"status": "running"|"done"|"error",
#         "current_turn": int, "total_turns": int,
#         "verdict": str|None, "verdict_reasoning": str|None,
#         "verdict_score": float|None, "tokens_used": int, "cost_usd": float,
#         "error": str|None}
_REJUDGE_STATUS: dict[int, dict] = {}


async def _rejudge_task(run_id: int, override: str, judge_llm_id: int) -> None:
    try:
        async with AsyncSessionLocal() as session:
            run = await session.get(TestRun, run_id)
            tc = await session.get(TestCase, run.test_case_id)
            judge_llm = await session.get(LLMConfig, judge_llm_id)

            res = await session.execute(
                select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
            )
            all_turns = list(res.scalars().all())
            judgeable = [t for t in all_turns if t.user_query and t.extracted_reply]
            total = len(judgeable)
            _REJUDGE_STATUS[run_id]["total_turns"] = total

            # Clear all existing turn verdicts so the UI shows a clean slate.
            for t in all_turns:
                t.turn_verdict = None
                t.turn_score = None
                t.turn_reasoning = None
                t.turn_analysis = None
            await session.commit()

            judge_provider = build_provider(
                judge_llm.provider, judge_llm.model, judge_llm.api_key, judge_llm.base_url
            )
            total_tokens = 0
            total_cost = 0.0
            history: list[dict[str, str]] = []

            for idx, t in enumerate(judgeable, 1):
                _REJUDGE_STATUS[run_id]["current_turn"] = idx
                try:
                    tv = await judge_turn(
                        judge_provider, tc,
                        turn_number=t.turn_number,
                        user_query=t.user_query,
                        bot_reply=t.extracted_reply,
                        history_before=list(history),
                        temperature=judge_llm.temperature,
                        max_tokens=min(judge_llm.max_tokens, 256),
                        success_criteria_override=override,
                    )
                    t.turn_verdict = tv.result
                    t.turn_score = tv.score
                    t.turn_reasoning = tv.reasoning
                    t.turn_analysis = tv.to_analysis_dict()
                    total_tokens += tv.input_tokens + tv.output_tokens
                    total_cost += tv.cost_usd
                    await session.commit()
                except Exception as exc:
                    _logger.warning("Per-turn rejudge failed for turn %s of run %s: %s",
                                    t.turn_number, run_id, exc)
                history.append({"role": "user", "content": t.user_query})
                if t.extracted_reply:
                    history.append({"role": "assistant", "content": t.extracted_reply})

            # Judging full transcript — current_turn > total signals this phase.
            _REJUDGE_STATUS[run_id]["current_turn"] = total + 1

            transcript = []
            for t in all_turns:
                if t.user_query:
                    transcript.append({"role": "user", "content": t.user_query})
                if t.extracted_reply:
                    transcript.append({"role": "assistant", "content": t.extracted_reply})

            tv_full = await judge_transcript(
                judge_provider, tc, transcript,
                temperature=judge_llm.temperature,
                max_tokens=judge_llm.max_tokens,
                success_criteria_override=override,
            )
            run.verdict = tv_full.result
            run.verdict_reasoning = tv_full.reasoning
            run.verdict_score = tv_full.score
            total_tokens += tv_full.input_tokens + tv_full.output_tokens
            total_cost += tv_full.cost_usd
            await session.commit()

            _REJUDGE_STATUS[run_id] = {
                "status": "done",
                "current_turn": total,
                "total_turns": total,
                "verdict": run.verdict,
                "verdict_reasoning": run.verdict_reasoning,
                "verdict_score": run.verdict_score,
                "tokens_used": total_tokens,
                "cost_usd": total_cost,
                "error": None,
            }
    except Exception as exc:
        _logger.exception("Rejudge task failed for run %s", run_id)
        _REJUDGE_STATUS[run_id] = {
            "status": "error",
            "current_turn": 0,
            "total_turns": 0,
            "verdict": None,
            "verdict_reasoning": None,
            "verdict_score": None,
            "tokens_used": 0,
            "cost_usd": 0.0,
            "error": str(exc),
        }


class RejudgeRequest(BaseModel):
    success_criteria_override: str
    judge_llm_id: int | None = None


class RejudgeStartResponse(BaseModel):
    status: str
    total_turns: int


class RejudgeStatusResponse(BaseModel):
    status: str
    current_turn: int = 0
    total_turns: int = 0
    verdict: str | None = None
    verdict_reasoning: str | None = None
    verdict_score: float | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    error: str | None = None


@router.post("/{run_id}/rejudge", response_model=RejudgeStartResponse)
async def start_rejudge(
    run_id: int,
    payload: RejudgeRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status == "running":
        raise HTTPException(409, "run is still in progress; wait for it to complete")
    if _REJUDGE_STATUS.get(run_id, {}).get("status") == "running":
        raise HTTPException(409, "re-judge already in progress for this run")

    tc = await session.get(TestCase, run.test_case_id)
    if tc is None:
        raise HTTPException(404, "test_case not found")

    judge_llm_id = payload.judge_llm_id or run.judge_llm_id
    judge_llm = await session.get(LLMConfig, judge_llm_id)
    if judge_llm is None:
        raise HTTPException(404, "judge_llm not found")

    res = await session.execute(
        select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
    )
    turns = list(res.scalars().all())
    total_turns = len([t for t in turns if t.user_query and t.extracted_reply])
    if total_turns == 0:
        raise HTTPException(422, "no judgeable turns found for this run")

    _REJUDGE_STATUS[run_id] = {
        "status": "running",
        "current_turn": 0,
        "total_turns": total_turns,
        "verdict": None,
        "verdict_reasoning": None,
        "verdict_score": None,
        "tokens_used": 0,
        "cost_usd": 0.0,
        "error": None,
    }
    asyncio.create_task(_rejudge_task(run_id, payload.success_criteria_override.strip(), judge_llm_id))
    return {"status": "started", "total_turns": total_turns}


@router.get("/{run_id}/rejudge_status", response_model=RejudgeStatusResponse)
async def get_rejudge_status(run_id: int) -> dict:
    s = _REJUDGE_STATUS.get(run_id)
    if s is None:
        return {"status": "not_started", "current_turn": 0, "total_turns": 0}
    return s


@router.get("/{run_id}/export")
async def export_run(
    run_id: int,
    format: str = Query(default="json", pattern="^(json|markdown|txt|html)$"),
    tester: str | None = Query(default=None),
):
    async with AsyncSessionLocal() as session:
        run = await session.get(TestRun, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        tc = await session.get(TestCase, run.test_case_id)
        ep = await session.get(EndpointConfig, run.endpoint_config_id)
        res = await session.execute(
            select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
        )
        turns = list(res.scalars().all())

    tester_name = (tester or "").strip() or None

    if format == "html":
        html_content = _build_html_export(run_id, run, tc, ep, turns, tester=tester_name)
        return HTMLResponse(content=html_content)

    if format == "json":
        payload = {
            "run_id": run.id,
            "tester": tester_name,
            "test_case": tc.name if tc else None,
            "test_case_usecase": tc.usecase if tc else None,
            "test_case_success_criteria": tc.success_criteria if tc else None,
            "endpoint": ep.name if ep else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "status": run.status,
            "stop_reason": run.stop_reason,
            "verdict": run.verdict,
            "verdict_reasoning": run.verdict_reasoning,
            "verdict_score": run.verdict_score,
            "run_analysis": run.run_analysis,
            "total_tokens": run.total_tokens,
            "total_cost_usd": run.total_cost_usd,
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "user_query": t.user_query,
                    "extracted_reply": t.extracted_reply,
                    "latency_ms": t.latency_ms,
                    "status_code": t.status_code,
                    "error": t.error,
                    "turn_verdict": t.turn_verdict,
                    "turn_score": t.turn_score,
                    "turn_reasoning": t.turn_reasoning,
                    "turn_analysis": t.turn_analysis,
                    "extracted_fields": t.extracted_fields,
                    "raw_request_payload": t.raw_request_payload,
                    "raw_response_payload": t.raw_response_payload,
                    "simulator_done": t.simulator_done,
                }
                for t in turns
            ],
        }
        return payload

    if format == "markdown":
        lines: list[str] = []
        lines.append(f"# Run {run.id} — {tc.name if tc else 'unknown'}")
        lines.append("")
        if tester_name:
            lines.append(f"- **Tester:** {tester_name}")
        lines.append(f"- **Status:** {run.status}")
        lines.append(f"- **Stop reason:** {run.stop_reason}")
        lines.append(f"- **Verdict:** {run.verdict} (score: {run.verdict_score})")
        if run.verdict_reasoning:
            lines.append(f"- **Reasoning:** {run.verdict_reasoning}")
        lines.append(f"- **Total tokens:** {run.total_tokens}")
        lines.append(f"- **Total cost (USD):** {run.total_cost_usd:.6f}")

        if run.run_analysis:
            lines.append("")
            lines.append("## Per-Criterion Summary")
            lines.append("")
            lines.append("| Criterion | Weight | Overall Score | Avg Turn Score | Reasoning |")
            lines.append("|-----------|--------|---------------|---------------|-----------|")
            for cname, cdata in run.run_analysis.items():
                ts = f"{cdata.get('transcript_score', 0):.2f}" if cdata.get("transcript_score") is not None else "—"
                avg_t = f"{cdata.get('avg_turn_score', 0):.2f}" if cdata.get("avg_turn_score") is not None else "—"
                tr = cdata.get("transcript_reasoning", "")
                lines.append(f"| {cname} | {cdata.get('weight', 0):.2f} | {ts} | {avg_t} | {tr} |")

        failed_turns = [t for t in turns if t.turn_verdict == "fail"]
        if failed_turns:
            lines.append("")
            lines.append("## Failed Turns")
            lines.append("")
            lines.append("| Turn # | Score | Reasoning |")
            lines.append("|--------|-------|-----------|")
            for t in failed_turns:
                score_str = f"{t.turn_score:.2f}" if t.turn_score is not None else "—"
                reason = (t.turn_reasoning or "").replace("|", "\\|")
                lines.append(f"| {t.turn_number} | {score_str} | {reason} |")

        lines.append("")
        lines.append("## Transcript")
        lines.append("")
        for t in turns:
            v_tag = f"  `{t.turn_verdict.upper()}`" if t.turn_verdict else ""
            lines.append(f"### Turn {t.turn_number}{v_tag}")
            lines.append("")
            lines.append(f"**User:** {t.user_query}")
            lines.append("")
            lines.append(f"**{ep.name if ep else 'Bot'}:** {t.extracted_reply or '(no reply extracted)'}")
            if t.error:
                lines.append(f"\n**Error:** {t.error}")
            if t.turn_verdict:
                lines.append(f"\n**Turn verdict:** {t.turn_verdict}  |  score: {t.turn_score:.2f}")
                if t.turn_reasoning:
                    lines.append(f"*{t.turn_reasoning}*")
                if t.turn_analysis:
                    ana = t.turn_analysis
                    cs = ana.get("criteria_scores") or {}
                    if cs:
                        lines.append("\n**Criteria scores:**")
                        for cname, cdata in cs.items():
                            lines.append(f"- {cname}: {cdata.get('score', 0):.2f} — {cdata.get('reasoning', '')}")
                    if ana.get("issues"):
                        lines.append("Issues: " + " · ".join(ana["issues"]))
                    if ana.get("strengths"):
                        lines.append("Strengths: " + " · ".join(ana["strengths"]))
                    if ana.get("suggestion") and ana["suggestion"].lower() not in ("none", "n/a"):
                        lines.append(f"Suggestion: {ana['suggestion']}")
            lines.append("")
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")

    # ── txt (human-readable shareable report) ────────────────────────────────
    W = 72
    SEP  = "=" * W
    SEP2 = "-" * W

    def wrap(text: str, indent: int = 2) -> str:
        """Word-wrap a paragraph to width W with a left indent."""
        prefix = " " * indent
        words = text.split()
        lines_out: list[str] = []
        line = prefix
        for w in words:
            if len(line) + len(w) + 1 > W:
                lines_out.append(line.rstrip())
                line = prefix + w + " "
            else:
                line += w + " "
        if line.strip():
            lines_out.append(line.rstrip())
        return "\n".join(lines_out)

    verdict_icon = {"pass": "✓ PASS", "fail": "✕ FAIL", "inconclusive": "? INCONCLUSIVE"}
    overall_label = verdict_icon.get(run.verdict or "", f"  {(run.verdict or 'unknown').upper()}")
    score_str = f"{run.verdict_score:.2f}/1.00" if run.verdict_score is not None else "n/a"

    started = run.started_at.strftime("%Y-%m-%d %H:%M UTC") if run.started_at else "—"
    finished = run.finished_at.strftime("%H:%M UTC") if run.finished_at else "—"

    txt: list[str] = [
        SEP,
        f"  TEST REPORT  —  {tc.name if tc else 'unknown test case'}",
        f"  Run #{run.id}  •  {run.status}  •  stop: {run.stop_reason or '—'}",
    ]
    if tester_name:
        txt.append(f"  Tester: {tester_name}")
    txt += [
        f"  {started}  →  {finished}",
        f"  Tokens: {run.total_tokens:,}  •  Cost: ${run.total_cost_usd:.4f}",
        SEP,
        "",
        f"  OVERALL VERDICT:  {overall_label}  (score: {score_str})",
        "",
    ]
    if run.verdict_reasoning:
        txt.append(wrap(run.verdict_reasoning))
        txt.append("")

    # Why it failed — explicit section when verdict is fail
    if run.verdict == "fail" and run.verdict_reasoning:
        txt += [
            SEP2,
            "  WHY IT FAILED",
            SEP2,
            wrap(run.verdict_reasoning),
            "",
        ]

    if tc:
        txt += [
            SEP2,
            "  USECASE",
            SEP2,
            wrap(tc.usecase or "(unspecified)"),
            "",
            SEP2,
            "  SUCCESS CRITERIA",
            SEP2,
            wrap(tc.success_criteria or "(unspecified)"),
            "",
        ]

    failed_turns = [t for t in turns if t.turn_verdict == "fail"]
    if failed_turns:
        txt += [
            "",
            SEP2,
            "  FAILED TURNS",
            SEP2,
            "",
        ]
        for t in failed_turns:
            score_str = f"{t.turn_score:.2f}" if t.turn_score is not None else "n/a"
            reason = t.turn_reasoning or ""
            txt.append(f"  Turn {t.turn_number}  —  score: {score_str}")
            if reason:
                txt.append(wrap(reason))
            txt.append("")

    txt += [
        SEP,
        f"  TRANSCRIPT  ({len(turns)} turn{'s' if len(turns) != 1 else ''})",
        SEP,
    ]

    for t in turns:
        v = t.turn_verdict or ""
        v_label = verdict_icon.get(v, v.upper()) if v else ""
        header = f"  Turn {t.turn_number}"
        if v_label:
            padding = W - len(header) - len(v_label) - 2
            header = header + " " + ("·" * max(1, padding - 1)) + " " + v_label
        txt.append("")
        txt.append(header)
        txt.append(SEP2)
        txt.append("")
        txt.append("  USER:")
        txt.append(wrap(t.user_query or "(empty)", indent=4))
        txt.append("")
        txt.append(f"  {(ep.name if ep else 'Bot').upper()}:")
        txt.append(wrap(t.extracted_reply or "(no reply extracted)", indent=4))
        if t.error:
            txt.append(f"\n  ERROR: {t.error}")

        if t.turn_verdict:
            score_t = f"{t.turn_score:.2f}" if t.turn_score is not None else "n/a"
            txt.append("")
            txt.append(f"  TURN ASSESSMENT  —  {verdict_icon.get(t.turn_verdict, t.turn_verdict.upper())}  (score: {score_t})")
            if t.turn_reasoning:
                txt.append(wrap(t.turn_reasoning))

            ana = t.turn_analysis or {}
            ns = ana.get("need_satisfied")
            if ns is not None:
                ns_label = "Need satisfied: YES" if ns else "Need satisfied: NO"
                txt.append(f"  {ns_label}")

            issues = ana.get("issues") or []
            if issues:
                txt.append("  Issues:")
                for iss in issues:
                    txt.append(wrap(f"- {iss}", indent=6))

            strengths = ana.get("strengths") or []
            if strengths:
                txt.append("  Strengths:")
                for s in strengths:
                    txt.append(wrap(f"+ {s}", indent=6))

            suggestion = (ana.get("suggestion") or "").strip()
            if suggestion and suggestion.lower() not in ("none", "n/a"):
                txt.append("  Suggestion:")
                txt.append(wrap(suggestion, indent=6))

            # Per-criterion breakdown
            cs = ana.get("criteria_scores") or {}
            if cs:
                txt.append("  Criteria breakdown:")
                for cname, cdata in cs.items():
                    cscore = cdata.get("score", 0.0)
                    creason = cdata.get("reasoning", "")
                    icon = "✓" if cscore >= 0.7 else "✕" if cscore < 0.4 else "◆"
                    txt.append(f"    {icon} {cname}: {cscore:.2f}")
                    if creason:
                        txt.append(wrap(creason, indent=8))

    # Per-criterion overall summary
    if run.run_analysis:
        txt += [
            "",
            SEP,
            "  PER-CRITERION SUMMARY",
            SEP,
            "",
        ]
        for cname, cdata in run.run_analysis.items():
            ts = cdata.get("transcript_score")
            avg_t = cdata.get("avg_turn_score")
            tr = cdata.get("transcript_reasoning", "")
            wt = cdata.get("weight", 0)
            turn_scores = cdata.get("turn_scores") or []
            ts_str = f"{ts:.2f}" if ts is not None else "n/a"
            avg_str = f"{avg_t:.2f}" if avg_t is not None else "n/a"
            txt.append(f"  {cname}  (weight: {wt:.2f})")
            txt.append(f"    Overall score: {ts_str}  |  Avg per-turn: {avg_str}")
            if tr:
                txt.append(wrap(tr, indent=4))
            if turn_scores:
                sparks = "  ".join(
                    f"T{i+1}:{s:.2f}" for i, s in enumerate(turn_scores)
                )
                txt.append(f"    Turn scores: {sparks}")
            txt.append("")

    txt += ["", SEP, "  Generated by conv-tester", SEP, ""]
    return PlainTextResponse("\n".join(txt), media_type="text/plain")


# ── Conclusion ───────────────────────────────────────────────────────────────

class ConclusionRequest(BaseModel):
    judge_llm_id: int | None = None


@router.post("/{run_id}/conclusion")
async def create_conclusion(
    run_id: int,
    payload: ConclusionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status == "running":
        raise HTTPException(409, "run is still in progress")

    tc = await session.get(TestCase, run.test_case_id)
    ep = await session.get(EndpointConfig, run.endpoint_config_id)

    judge_llm_id = payload.judge_llm_id or run.judge_llm_id
    judge_llm = await session.get(LLMConfig, judge_llm_id)
    if judge_llm is None:
        raise HTTPException(404, "judge_llm not found")

    res = await session.execute(
        select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
    )
    turns = list(res.scalars().all())
    if not any(t.user_query for t in turns):
        raise HTTPException(422, "no turns found for this run")

    from backend.services.conclusion import generate_conclusion
    result = await generate_conclusion(run, tc, ep, turns, judge_llm)
    # Persist so the HTML export can include it without re-generating
    run.conclusion = result
    await session.commit()
    return result


# ── WebSocket traffic logs ───────────────────────────────────────────────────

@router.get("/{run_id}/ws-logs")
async def get_ws_logs(run_id: int) -> list[dict]:
    """Return the in-memory WebSocket traffic log for this run (newest last)."""
    from backend.services.run_log import get_ws_logs as _get
    return _get(run_id)


@router.delete("/{run_id}/ws-logs", status_code=204)
async def clear_ws_logs(run_id: int) -> None:
    """Discard all stored WebSocket log entries for this run."""
    from backend.services.run_log import clear_ws_logs as _clear
    _clear(run_id)


# ── HTML export ───────────────────────────────────────────────────────────────

# (imported lazily so the rest of the module doesn't pay the import cost)
def _build_html_export(run_id: int, run: "TestRun", tc, ep, turns: list, tester: str | None = None) -> str:
    from backend.services.html_export import render_run_html
    return render_run_html(
        run_id=run_id,
        run_name=run.name,
        run=run,
        tc=tc,
        ep=ep,
        turns=turns,
        tester=tester,
    )

