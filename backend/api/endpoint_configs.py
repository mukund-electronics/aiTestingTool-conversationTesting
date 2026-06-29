from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models.endpoint_config import EndpointConfig
from backend.schemas.endpoint_config import (
    EndpointConfigCreate,
    EndpointConfigOut,
    EndpointConfigUpdate,
)

router = APIRouter(prefix="/endpoint-configs", tags=["endpoint-configs"])


@router.post("", response_model=EndpointConfigOut, status_code=status.HTTP_201_CREATED)
async def create_endpoint_config(
    payload: EndpointConfigCreate,
    session: AsyncSession = Depends(get_session),
) -> EndpointConfig:
    row = EndpointConfig(**payload.model_dump())
    session.add(row)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.refresh(row)
    return row


@router.get("", response_model=list[EndpointConfigOut])
async def list_endpoint_configs(
    session: AsyncSession = Depends(get_session),
) -> list[EndpointConfig]:
    res = await session.execute(select(EndpointConfig).order_by(EndpointConfig.id.desc()))
    return list(res.scalars().all())


@router.get("/{config_id}", response_model=EndpointConfigOut)
async def get_endpoint_config(
    config_id: int,
    session: AsyncSession = Depends(get_session),
) -> EndpointConfig:
    row = await session.get(EndpointConfig, config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="EndpointConfig not found")
    return row


@router.put("/{config_id}", response_model=EndpointConfigOut)
async def update_endpoint_config(
    config_id: int,
    payload: EndpointConfigUpdate,
    session: AsyncSession = Depends(get_session),
) -> EndpointConfig:
    row = await session.get(EndpointConfig, config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="EndpointConfig not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint_config(
    config_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(EndpointConfig, config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="EndpointConfig not found")
    await session.delete(row)
    await session.commit()
