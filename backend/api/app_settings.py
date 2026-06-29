"""App-wide key/value settings (e.g. the tester's name) persisted in the DB so
they survive UI refreshes and backend restarts."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models.app_setting import AppSetting

router = APIRouter(prefix="/app-settings", tags=["app-settings"])


class AppSettingUpsert(BaseModel):
    key: str
    value: str = ""


@router.get("")
async def get_app_settings(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Return all settings as a flat {key: value} map."""
    res = await session.execute(select(AppSetting))
    return {row.key: row.value for row in res.scalars().all()}


@router.put("")
async def put_app_setting(
    payload: AppSettingUpsert,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Upsert one setting and return the updated {key: value}."""
    row = await session.get(AppSetting, payload.key)
    if row is None:
        row = AppSetting(key=payload.key, value=payload.value)
        session.add(row)
    else:
        row.value = payload.value
    await session.commit()
    return {payload.key: payload.value}
