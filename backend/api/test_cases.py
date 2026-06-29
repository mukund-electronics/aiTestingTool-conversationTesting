from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models.test_case import TestCase
from backend.models.test_run import TestRun
from backend.schemas.test_case import TestCaseCreate, TestCaseOut, TestCaseUpdate

router = APIRouter(prefix="/test-cases", tags=["test-cases"])


@router.post("", response_model=TestCaseOut, status_code=status.HTTP_201_CREATED)
async def create_test_case(
    payload: TestCaseCreate,
    session: AsyncSession = Depends(get_session),
) -> TestCase:
    row = TestCase(**payload.model_dump())
    session.add(row)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.refresh(row)
    return row


@router.get("", response_model=list[TestCaseOut])
async def list_test_cases(
    session: AsyncSession = Depends(get_session),
) -> list[TestCase]:
    res = await session.execute(select(TestCase).order_by(TestCase.id.desc()))
    return list(res.scalars().all())


@router.get("/{tc_id}", response_model=TestCaseOut)
async def get_test_case(
    tc_id: int,
    session: AsyncSession = Depends(get_session),
) -> TestCase:
    row = await session.get(TestCase, tc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="TestCase not found")
    return row


@router.put("/{tc_id}", response_model=TestCaseOut)
async def update_test_case(
    tc_id: int,
    payload: TestCaseUpdate,
    session: AsyncSession = Depends(get_session),
) -> TestCase:
    row = await session.get(TestCase, tc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="TestCase not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{tc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test_case(
    tc_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(TestCase, tc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="TestCase not found")
    # Delete all runs for this test case first; each run cascades to its turns.
    runs_res = await session.execute(select(TestRun).where(TestRun.test_case_id == tc_id))
    for run in runs_res.scalars().all():
        await session.delete(run)
    await session.delete(row)
    await session.commit()
