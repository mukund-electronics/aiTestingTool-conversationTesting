"""Batch run endpoints — create and query groups of parallel test runs."""

from __future__ import annotations

import asyncio
import copy
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models.endpoint_config import EndpointConfig
from backend.models.llm_config import LLMConfig
from backend.models.run_batch import RunBatch
from backend.models.test_case import TestCase
from backend.models.test_run import TestRun
from backend.schemas.run_batch import BatchRunCreate, BatchRunResponse, RunBatchRead
from backend.services.runner import execute_run, register_task

router = APIRouter(prefix="/batches", tags=["batches"])


def _set_nested(obj: dict, keys: list[str], value: str) -> None:
    """Set obj[keys[0]][keys[1]]…[keys[-1]] = value, creating dicts as needed."""
    for key in keys[:-1]:
        if key not in obj or not isinstance(obj[key], dict):
            obj[key] = {}
        obj = obj[key]
    obj[keys[-1]] = value


@router.post("", response_model=BatchRunResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    payload: BatchRunCreate,
    session: AsyncSession = Depends(get_session),
) -> BatchRunResponse:
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

    n = payload.count
    base_name = (payload.name or "Batch run").strip()

    # Resolve each run's test case (defaults to the batch-level test_case_id),
    # validate any non-default ones, and snapshot their names.
    tc_name_by_id: dict[int, str] = {payload.test_case_id: tc.name}
    per_run_tc_ids: list[int] = []
    for k in range(n):
        tid = payload.test_case_id
        if payload.per_run_test_case_ids and k < len(payload.per_run_test_case_ids):
            tid = payload.per_run_test_case_ids[k] or payload.test_case_id
        per_run_tc_ids.append(tid)
        if tid not in tc_name_by_id:
            _tc = await session.get(TestCase, tid)
            if _tc is None:
                raise HTTPException(404, f"test_case {tid} not found")
            tc_name_by_id[tid] = _tc.name

    distinct_tc_names = {tc_name_by_id[tid] for tid in per_run_tc_ids}
    batch_test_case_name = (
        next(iter(distinct_tc_names))
        if len(distinct_tc_names) == 1
        else f"Mixed ({len(distinct_tc_names)} test cases)"
    )

    # Pre-compute per-run body template overrides if the user specified field values.
    base_template: dict = {}
    try:
        base_template = json.loads(ep.request_body_template or "{}")
    except json.JSONDecodeError:
        pass  # malformed template — overrides won't be applied

    def _make_template_override(k: int) -> str | None:
        overrides = (payload.per_run_overrides or [])[k] if payload.per_run_overrides and k < len(payload.per_run_overrides) else {}
        if not overrides or not isinstance(base_template, dict):
            return None
        modified = copy.deepcopy(base_template)
        for field_path, value in overrides.items():
            if field_path.strip():
                _set_nested(modified, field_path.split("."), value)
        return json.dumps(modified)

    # Create all TestRun rows in one transaction, then commit so IDs are assigned.
    runs: list[TestRun] = []
    for k in range(1, n + 1):
        run = TestRun(
            name=f"{base_name} [{k}/{n}]",
            test_case_id=per_run_tc_ids[k - 1],
            endpoint_config_id=payload.endpoint_config_id,
            simulator_llm_id=payload.simulator_llm_id,
            judge_llm_id=payload.judge_llm_id,
            max_cost_usd=payload.max_cost_usd,
            judge_criteria_override=payload.judge_criteria_override or None,
            skip_judge=payload.skip_judge,
            ws_connect_delay_sec=payload.ws_connect_delay_sec,
            status="running",
            request_body_template_override=_make_template_override(k - 1),
        )
        session.add(run)
        runs.append(run)

    await session.commit()
    for run in runs:
        await session.refresh(run)

    # Launch one asyncio task per run — identical to how POST /runs works.
    # Tasks are I/O-bound (LLM + endpoint HTTP calls) so they run concurrently
    # on the event loop without threads.
    run_ids: list[int] = []
    for run in runs:
        task = asyncio.create_task(execute_run(run.id))
        register_task(run.id, task)
        run_ids.append(run.id)

    # Persist the batch record with a snapshot of names for the Results tab.
    batch = RunBatch(
        name=base_name,
        test_case_name=batch_test_case_name,
        endpoint_name=ep.name,
        count=n,
        run_ids_json=json.dumps(run_ids),
    )
    session.add(batch)
    await session.commit()
    await session.refresh(batch)

    return BatchRunResponse(
        batch_id=batch.id,
        run_ids=run_ids,
        batch_size=n,
        name=base_name,
    )


@router.get("", response_model=list[RunBatchRead])
async def list_batches(
    session: AsyncSession = Depends(get_session),
) -> list[RunBatch]:
    result = await session.execute(
        select(RunBatch).order_by(RunBatch.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{batch_id}", response_model=RunBatchRead)
async def get_batch(
    batch_id: int,
    session: AsyncSession = Depends(get_session),
) -> RunBatch:
    batch = await session.get(RunBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "batch not found")
    return batch


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    batch = await session.get(RunBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "batch not found")
    for rid in batch.run_ids:
        run = await session.get(TestRun, rid)
        if run:
            await session.delete(run)
    await session.delete(batch)
    await session.commit()
