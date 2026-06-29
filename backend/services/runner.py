"""Runner: orchestrates one TestRun end-to-end. Cancellable via asyncio."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import AsyncSessionLocal
from backend.models.endpoint_config import EndpointConfig
from backend.models.llm_config import LLMConfig
from backend.models.test_case import TestCase
from backend.models.test_run import TestRun
from backend.models.turn import Turn
from backend.services.endpoint_caller import call_endpoint
from backend.services.extractor import extract_fields, is_truthy_end_flag
from backend.services.judge import judge_transcript, judge_turn
from backend.services.llm import build_provider
from backend.services.simulator import generate_user_query
from backend.services.templating import build_variables, render_template
from backend.services.ws_caller import WebSocketSession

logger = logging.getLogger(__name__)

StopReason = Literal[
    "endpoint_error",
    "endpoint_signaled_end",
    "goal_achieved",
    "max_turns",
    "cost_cap",
    "user_stopped",
    "simulator_error",
    "judge_error",
    "step_pause",
]

# Maps stop_reason -> final TestRun.status.
_STATUS_FOR_STOP: dict[str, str] = {
    "endpoint_error": "failed",
    "endpoint_signaled_end": "completed",
    "goal_achieved": "completed",
    "max_turns": "completed",
    "cost_cap": "stopped",
    "user_stopped": "stopped",
    "simulator_error": "failed",
    "judge_error": "completed",  # run itself finished; only judging failed
    "step_pause": "paused",
}


@dataclass
class StopDecision:
    stop: bool
    reason: StopReason | None = None


def decide_stop(
    *,
    endpoint_error: bool,
    end_flag_truthy: bool,
    simulator_done: bool,
    turn_number: int,
    max_turns: int,
    cost_so_far: float,
    cost_cap: float | None,
) -> StopDecision:
    """Stop-condition precedence as specified.

    Order:
        1. endpoint_error
        2. endpoint_signaled_end
        3. goal_achieved (simulator <<<DONE>>>)
        4. max_turns
        5. cost_cap (checked last, after the turn is complete)
    """
    if endpoint_error:
        return StopDecision(True, "endpoint_error")
    if end_flag_truthy:
        return StopDecision(True, "endpoint_signaled_end")
    if simulator_done:
        return StopDecision(True, "goal_achieved")
    if turn_number >= max_turns:
        return StopDecision(True, "max_turns")
    if cost_cap is not None and cost_so_far >= cost_cap:
        return StopDecision(True, "cost_cap")
    return StopDecision(False, None)


# In-process registry of active run tasks, used by the /stop endpoint.
_RUN_TASKS: dict[int, asyncio.Task] = {}

# Persistent WebSocket sessions kept alive across step-mode pauses.
# Keyed by run_id. Populated on step_pause instead of closing; consumed by
# the next resume_run call. Closed on any terminal stop (including user cancel).
_WS_SESSIONS: dict[int, WebSocketSession] = {}


def _store_ws(run_id: int, ws: WebSocketSession) -> None:
    _WS_SESSIONS[run_id] = ws


def _pop_ws(run_id: int) -> WebSocketSession | None:
    return _WS_SESSIONS.pop(run_id, None)


def register_task(run_id: int, task: asyncio.Task) -> None:
    _RUN_TASKS[run_id] = task

    def _cleanup(_t: asyncio.Task) -> None:
        _RUN_TASKS.pop(run_id, None)

    task.add_done_callback(_cleanup)


async def cancel_run(run_id: int) -> bool:
    """Cancel an in-flight run. Returns True if a task was cancelled."""
    task = _RUN_TASKS.get(run_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _load_run_context(
    session: AsyncSession, run_id: int
) -> tuple[TestRun, TestCase, EndpointConfig, LLMConfig, LLMConfig]:
    run = await session.get(TestRun, run_id)
    if run is None:
        raise ValueError(f"TestRun {run_id} not found")
    test_case = await session.get(TestCase, run.test_case_id)
    endpoint = await session.get(EndpointConfig, run.endpoint_config_id)
    simulator_llm = await session.get(LLMConfig, run.simulator_llm_id)
    judge_llm = await session.get(LLMConfig, run.judge_llm_id)
    if not (test_case and endpoint and simulator_llm and judge_llm):
        raise ValueError(f"TestRun {run_id} references missing config rows")
    return run, test_case, endpoint, simulator_llm, judge_llm


async def _finalize_run(
    session: AsyncSession,
    run: TestRun,
    *,
    status: str,
    stop_reason: str | None,
    verdict_result: str | None = None,
    verdict_reasoning: str | None = None,
    verdict_score: float | None = None,
    run_analysis: dict | None = None,
) -> None:
    run.status = status
    run.stop_reason = stop_reason
    run.verdict = verdict_result
    run.verdict_reasoning = verdict_reasoning
    run.verdict_score = verdict_score
    if run_analysis is not None:
        run.run_analysis = run_analysis
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()


async def _pre_generate_query(
    simulator_provider,
    test_case,
    transcript: list[dict],
    simulator_cfg,
) -> str:
    """Draft the next user query via the simulator for step-mode preview.

    Returns an empty string if the simulator fails — the UI textarea will be
    blank and the tester can type the question manually.
    """
    try:
        sim = await generate_user_query(
            simulator_provider,
            test_case,
            transcript,
            temperature=simulator_cfg.temperature,
            max_tokens=simulator_cfg.max_tokens,
        )
        return sim.user_query if sim.user_query.strip() else ""
    except Exception:
        return ""


@dataclass
class _LoopState:
    """Mutable conversation state shared with the turn loop.

    ``transcript`` and ``all_turn_criteria`` are mutated in place; ``session_id``
    and ``turn_number`` are written back by the loop on normal completion.
    """

    transcript: list[dict[str, str]]
    session_id: str
    all_turn_criteria: list[dict]
    turn_number: int


def _make_session_id(test_case_name: str | None, run_name: str | None, run_id: int) -> str:
    """Build a human-readable session identifier: <testcase>+<runName>+<runId>."""
    def _slug(s: str | None) -> str:
        return re.sub(r"\s+", "_", (s or "").strip()) or "unknown"
    return f"{_slug(test_case_name)}-{_slug(run_name)}-{run_id}"


async def _conversation_loop(
    session: AsyncSession,
    run: TestRun,
    test_case: TestCase,
    endpoint: EndpointConfig,
    simulator_provider,
    judge_provider,
    simulator_cfg: LLMConfig,
    judge_cfg: LLMConfig,
    *,
    state: _LoopState,
    max_turns: int,
    ws_session: WebSocketSession | None,
    forced_first_query: str | None,
    forced_first_turn: int,
) -> StopReason | None:
    """Drive turns until a stop condition fires; persist each Turn as it goes.

    Shared by both execute_run and resume_run. The only behavioral differences
    between a fresh run and a resume are the starting ``state`` (empty vs.
    reconstructed), the ``max_turns`` ceiling, and which turn (if any) injects a
    verbatim ``forced_first_query`` instead of calling the simulator.

    Returns the stop_reason. Mutates ``state`` and commits rows on ``session``.
    """
    run_id = run.id
    transcript = state.transcript
    all_turn_criteria = state.all_turn_criteria
    session_id = state.session_id
    turn_number = state.turn_number
    stop_reason: StopReason | None = None

    while True:
        turn_number += 1

        # 1) Generate user query — up to 2 attempts before giving up. A
        # forced_first_query (test-case starting query, or step-mode override)
        # is used verbatim on its designated turn instead of the simulator.
        user_query = ""
        simulator_done = False
        sim_tokens = 0
        sim_cost = 0.0
        sim_error: str | None = None

        if turn_number == forced_first_turn and forced_first_query:
            user_query = forced_first_query
        else:
            for _attempt in range(2):
                try:
                    sim = await generate_user_query(
                        simulator_provider,
                        test_case,
                        transcript,
                        temperature=simulator_cfg.temperature,
                        max_tokens=simulator_cfg.max_tokens,
                    )
                    sim_tokens += sim.input_tokens + sim.output_tokens
                    sim_cost += sim.cost_usd
                    if sim.user_query.strip():
                        user_query = sim.user_query
                        simulator_done = sim.done
                        sim_error = None
                        break
                    else:
                        sim_error = "simulator returned an empty message"
                        logger.warning(
                            "Simulator returned empty query (attempt %s) on turn %s of run %s",
                            _attempt + 1, turn_number, run_id,
                        )
                except Exception as exc:
                    sim_error = str(exc)
                    logger.warning(
                        "Simulator error (attempt %s) on turn %s of run %s: %s",
                        _attempt + 1, turn_number, run_id, exc,
                    )

        if not user_query:
            err_msg = f"simulator_error: {sim_error or 'unknown error'}"
            logger.error("Simulator gave up after retries on turn %s of run %s: %s",
                         turn_number, run_id, sim_error)
            turn = Turn(
                test_run_id=run.id,
                turn_number=turn_number,
                user_query="",
                error=err_msg,
                tokens_used=sim_tokens,
                cost_usd=sim_cost,
            )
            session.add(turn)
            run.total_tokens += sim_tokens
            run.total_cost_usd += sim_cost
            await session.commit()
            stop_reason = "simulator_error"
            break

        # 2) Build packet via templating.
        variables = build_variables(
            user_query=user_query,
            session_id=session_id,
            history=transcript,
            turn_number=turn_number,
        )
        try:
            _tpl = run.request_body_template_override or endpoint.request_body_template
            payload = render_template(_tpl, variables)
        except Exception as exc:
            logger.exception("Template render failed on turn %s of run %s", turn_number, run_id)
            turn = Turn(
                test_run_id=run.id,
                turn_number=turn_number,
                user_query=user_query,
                error=f"template_error: {exc}",
                tokens_used=sim_tokens,
                cost_usd=sim_cost,
            )
            session.add(turn)
            await session.commit()
            stop_reason = "endpoint_error"
            break

        # 3) Call endpoint (HTTP with retries, or WebSocket send/recv).
        if ws_session is not None:
            call_result = await ws_session.send_and_receive(payload)
        else:
            call_result = await call_endpoint(endpoint, payload)
        endpoint_error_now = call_result.error is not None and (
            call_result.status_code is None or call_result.status_code >= 400
        )

        # 4) Extract fields.
        extracted = extract_fields(call_result.response_json, endpoint.response_extractors or {})
        extracted_reply = ""
        if "reply" in extracted and isinstance(extracted["reply"], str):
            extracted_reply = extracted["reply"]
        elif "reply" in extracted:
            extracted_reply = str(extracted["reply"])

        new_session_id = extracted.get("session_id")
        if isinstance(new_session_id, str) and new_session_id:
            session_id = new_session_id
        elif new_session_id is not None:
            session_id = str(new_session_id)

        end_flag_truthy = is_truthy_end_flag(extracted.get("end_flag"))

        # 5) Persist Turn row BEFORE deciding next step.
        turn_row = Turn(
            test_run_id=run.id,
            turn_number=turn_number,
            user_query=user_query,
            raw_request_payload=payload if isinstance(payload, (dict, list)) else None,
            raw_response_payload=call_result.response_json,
            extracted_reply=extracted_reply,
            extracted_fields=extracted,
            latency_ms=call_result.latency_ms,
            status_code=call_result.status_code,
            error=call_result.error,
            tokens_used=sim_tokens,
            cost_usd=sim_cost,
            simulator_done=simulator_done,
        )
        session.add(turn_row)
        run.total_tokens += sim_tokens
        run.total_cost_usd += sim_cost
        await session.commit()

        # 5b) Per-turn judge — rate this individual exchange.
        if extracted_reply and not endpoint_error_now and not run.skip_judge:
            try:
                t_verdict = await judge_turn(
                    judge_provider,
                    test_case,
                    turn_number=turn_number,
                    user_query=user_query,
                    bot_reply=extracted_reply,
                    history_before=list(transcript),  # snapshot before appending this turn
                    temperature=judge_cfg.temperature,
                    max_tokens=min(judge_cfg.max_tokens, 256),
                    success_criteria_override=run.judge_criteria_override or None,
                )
                turn_row.turn_verdict = t_verdict.result
                turn_row.turn_score = t_verdict.score
                turn_row.turn_reasoning = t_verdict.reasoning
                turn_row.turn_analysis = t_verdict.to_analysis_dict()
                if t_verdict.criteria_scores:
                    all_turn_criteria.append(t_verdict.criteria_scores)
                run.total_tokens += t_verdict.input_tokens + t_verdict.output_tokens
                run.total_cost_usd += t_verdict.cost_usd
                await session.commit()
            except Exception as exc:
                logger.warning("Per-turn judge failed on turn %s of run %s: %s",
                               turn_number, run_id, exc)

        # 6) Update transcript with the new exchange (only if we have a reply).
        transcript.append({"role": "user", "content": user_query})
        if extracted_reply:
            transcript.append({"role": "assistant", "content": extracted_reply})

        # 7) Check stop conditions in spec order.
        decision = decide_stop(
            endpoint_error=endpoint_error_now,
            end_flag_truthy=end_flag_truthy,
            simulator_done=simulator_done,
            turn_number=turn_number,
            max_turns=max_turns,
            cost_so_far=run.total_cost_usd,
            cost_cap=run.max_cost_usd,
        )
        if decision.stop:
            stop_reason = decision.reason
            break

        # Single-turn mode: stop after the first turn regardless.
        if test_case.mode == "single_turn":
            stop_reason = "max_turns"
            break

        # 7b) Step-mode pause: pre-generate the next query so the
        # tester can review/edit it before sending.
        if run.step_mode:
            run.next_pending_query = await _pre_generate_query(
                simulator_provider, test_case, transcript, simulator_cfg
            )
            await session.commit()
            stop_reason = "step_pause"
            break

    state.session_id = session_id
    state.turn_number = turn_number
    return stop_reason


async def _judge_and_finalize(
    session: AsyncSession,
    run: TestRun,
    test_case: TestCase,
    judge_provider,
    judge_cfg: LLMConfig,
    *,
    transcript: list[dict[str, str]],
    all_turn_criteria: list[dict],
    stop_reason: StopReason | None,
) -> None:
    """Judge the full transcript (when applicable) and persist the final state."""
    run_id = run.id
    verdict_result: str | None = None
    verdict_reasoning: str | None = None
    verdict_score: float | None = None
    run_analysis: dict | None = None

    judgeable = (
        not run.skip_judge
        and stop_reason not in ("simulator_error", "step_pause")
        and len(transcript) > 0
    )
    if judgeable:
        try:
            verdict = await judge_transcript(
                judge_provider,
                test_case,
                transcript,
                temperature=judge_cfg.temperature,
                max_tokens=judge_cfg.max_tokens,
                success_criteria_override=run.judge_criteria_override or None,
            )
            verdict_result = verdict.result
            verdict_reasoning = verdict.reasoning
            verdict_score = verdict.score
            run.total_tokens += verdict.input_tokens + verdict.output_tokens
            run.total_cost_usd += verdict.cost_usd

            # Build per-criterion run_analysis from transcript-level scores
            # and averages of the per-turn scores collected above.
            eval_criteria = test_case.eval_criteria or []
            if eval_criteria and verdict.criteria_scores:
                run_analysis = {}
                for c in eval_criteria:
                    name = c["name"]
                    turn_scores = [
                        t[name]["score"]
                        for t in all_turn_criteria
                        if name in t
                    ]
                    run_analysis[name] = {
                        "weight": c["weight"],
                        "transcript_score": verdict.criteria_scores.get(name, {}).get("score"),
                        "transcript_reasoning": verdict.criteria_scores.get(name, {}).get("reasoning", ""),
                        "avg_turn_score": (
                            sum(turn_scores) / len(turn_scores) if turn_scores else None
                        ),
                        "turn_scores": turn_scores,
                    }
        except Exception as exc:
            logger.exception("Judge failed on run %s", run_id)
            verdict_result = "inconclusive"
            verdict_reasoning = f"judge_error: {exc}"
            verdict_score = 0.0

    status = _STATUS_FOR_STOP.get(stop_reason or "max_turns", "completed")
    await _finalize_run(
        session,
        run,
        status=status,
        stop_reason=stop_reason,
        verdict_result=verdict_result,
        verdict_reasoning=verdict_reasoning,
        verdict_score=verdict_score,
        run_analysis=run_analysis,
    )


async def _teardown_ws(
    run_id: int, ws_session: WebSocketSession | None, stop_reason: StopReason | None
) -> None:
    """Close the WebSocket on a terminal stop, or stash it across a step pause."""
    if ws_session is None:
        return
    if stop_reason == "step_pause":
        # Keep the connection alive during the pause (responds to server pings
        # on our behalf); the next resume_run consumes it.
        ws_session.start_keepalive()
        _store_ws(run_id, ws_session)
    else:
        _pop_ws(run_id)
        await ws_session.close()


async def _finalize_cancelled(session: AsyncSession, run_id: int) -> None:
    run = await session.get(TestRun, run_id)
    if run is not None:
        await _finalize_run(session, run, status="stopped", stop_reason="user_stopped")


async def execute_run(run_id: int) -> None:
    """Drive a TestRun to completion. Persists per-turn rows as it goes.

    This function is meant to be wrapped in an asyncio.Task and registered
    via ``register_task`` so the stop endpoint can cancel it.
    """
    async with AsyncSessionLocal() as session:
        try:
            run, test_case, endpoint, simulator_cfg, judge_cfg = await _load_run_context(
                session, run_id
            )
        except Exception as exc:
            logger.exception("Failed to load run context for run %s", run_id)
            run = await session.get(TestRun, run_id)
            if run is not None:
                await _finalize_run(
                    session, run, status="failed", stop_reason="simulator_error"
                )
            raise

        simulator_provider = build_provider(
            simulator_cfg.provider, simulator_cfg.model, simulator_cfg.api_key,
            simulator_cfg.base_url,
        )
        judge_provider = build_provider(
            judge_cfg.provider, judge_cfg.model, judge_cfg.api_key, judge_cfg.base_url
        )

        # transcript is what the chatbot sees: roles user/assistant from the
        # chatbot's POV. We also track session_id from response extractors.
        # Seed with a deterministic UUID so {{session_id}} is non-empty from
        # turn 1 even when the endpoint never echoes it back.
        _initial_session_id = _make_session_id(test_case.name, run.name, run_id)
        state = _LoopState(transcript=[], session_id=_initial_session_id, all_turn_criteria=[], turn_number=0)
        stop_reason: StopReason | None = None
        ws_session: WebSocketSession | None = None

        try:
            if getattr(endpoint, "protocol", "http") == "websocket":
                ws_session = WebSocketSession(endpoint, run_id=run_id)
                await ws_session.connect()
                # Actively drain any server-sent welcome frames before sending
                # the first user message — only once, right after connection.
                if run.ws_connect_delay_sec and run.ws_connect_delay_sec > 0:
                    await ws_session.drain(run.ws_connect_delay_sec)

            stop_reason = await _conversation_loop(
                session, run, test_case, endpoint,
                simulator_provider, judge_provider, simulator_cfg, judge_cfg,
                state=state,
                max_turns=test_case.max_turns,
                ws_session=ws_session,
                forced_first_query=test_case.starting_query or None,
                forced_first_turn=1,
            )
            await _judge_and_finalize(
                session, run, test_case, judge_provider, judge_cfg,
                transcript=state.transcript,
                all_turn_criteria=state.all_turn_criteria,
                stop_reason=stop_reason,
            )

        except asyncio.CancelledError:
            logger.info("Run %s cancelled by user", run_id)
            # Always discard any stored session and close on user cancel.
            _pop_ws(run_id)
            if ws_session is not None:
                await ws_session.close()
                ws_session = None  # prevent finally from double-closing
            await _finalize_cancelled(session, run_id)
            raise
        finally:
            await _teardown_ws(run_id, ws_session, stop_reason)


async def resume_run(
    run_id: int,
    additional_turns: int,
    query_override: str | None = None,
) -> None:
    """Continue a stopped/paused run for *additional_turns* more exchanges.

    Reconstructs the conversation history from existing Turn rows and resumes
    exactly where execution left off.  Registered via ``register_task`` so the
    /stop endpoint can cancel it like any other run.

    ``query_override`` — when provided (step-mode), skips the simulator for the
    very first turn of this resume and uses the supplied text verbatim.
    """
    async with AsyncSessionLocal() as session:
        try:
            run, test_case, endpoint, simulator_cfg, judge_cfg = await _load_run_context(
                session, run_id
            )
        except Exception as exc:
            logger.exception("Failed to load run context for resumed run %s", run_id)
            run = await session.get(TestRun, run_id)
            if run is not None:
                await _finalize_run(session, run, status="failed", stop_reason="simulator_error")
            raise

        # ── Reconstruct state from existing turns ───────────────────────────
        res = await session.execute(
            select(Turn).where(Turn.test_run_id == run_id).order_by(Turn.turn_number)
        )
        existing_turns = list(res.scalars().all())

        _initial_session_id = _make_session_id(test_case.name, run.name, run_id)
        state = _LoopState(transcript=[], session_id=_initial_session_id, all_turn_criteria=[], turn_number=0)
        for t in existing_turns:
            if t.user_query:
                state.transcript.append({"role": "user", "content": t.user_query})
            if t.extracted_reply:
                state.transcript.append({"role": "assistant", "content": t.extracted_reply})
            if t.extracted_fields and t.extracted_fields.get("session_id"):
                state.session_id = str(t.extracted_fields["session_id"])
            if t.turn_analysis and t.turn_analysis.get("criteria_scores"):
                state.all_turn_criteria.append(t.turn_analysis["criteria_scores"])

        last_turn_number = max((t.turn_number for t in existing_turns), default=0)
        state.turn_number = last_turn_number
        effective_max_turns = last_turn_number + additional_turns
        first_resume_turn = last_turn_number + 1  # turn that may inject query_override

        # ── Reset run to running state ───────────────────────────────────────
        run.status = "running"
        run.stop_reason = None
        run.verdict = None
        run.verdict_reasoning = None
        run.verdict_score = None
        run.run_analysis = None
        run.finished_at = None
        run.next_pending_query = None  # consumed now; will be repopulated on next step_pause
        await session.commit()

        simulator_provider = build_provider(
            simulator_cfg.provider, simulator_cfg.model, simulator_cfg.api_key,
            simulator_cfg.base_url,
        )
        judge_provider = build_provider(
            judge_cfg.provider, judge_cfg.model, judge_cfg.api_key, judge_cfg.base_url
        )

        stop_reason: StopReason | None = None
        ws_session: WebSocketSession | None = None

        try:
            if getattr(endpoint, "protocol", "http") == "websocket":
                stored = _pop_ws(run_id)
                if stored is not None:
                    # Stop the keepalive task before touching the socket.
                    # This ensures no concurrent recv() calls between the
                    # keepalive loop and the upcoming send_and_receive().
                    await stored.stop_keepalive()
                    ws_session = stored
                    logger.debug("Reusing stored WS session for run %s", run_id)
                else:
                    ws_session = WebSocketSession(endpoint, run_id=run_id)
                    await ws_session.connect()

            stop_reason = await _conversation_loop(
                session, run, test_case, endpoint,
                simulator_provider, judge_provider, simulator_cfg, judge_cfg,
                state=state,
                max_turns=effective_max_turns,
                ws_session=ws_session,
                forced_first_query=query_override,
                forced_first_turn=first_resume_turn,
            )
            await _judge_and_finalize(
                session, run, test_case, judge_provider, judge_cfg,
                transcript=state.transcript,
                all_turn_criteria=state.all_turn_criteria,
                stop_reason=stop_reason,
            )

        except asyncio.CancelledError:
            logger.info("Resumed run %s cancelled by user", run_id)
            # Always discard any stored session and close on user cancel.
            _pop_ws(run_id)
            if ws_session is not None:
                await ws_session.close()
                ws_session = None  # prevent finally from double-closing
            await _finalize_cancelled(session, run_id)
            raise
        finally:
            await _teardown_ws(run_id, ws_session, stop_reason)
