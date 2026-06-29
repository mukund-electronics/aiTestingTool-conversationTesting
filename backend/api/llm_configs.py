from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models.llm_config import LLMConfig
from backend.schemas.llm_config import LLMConfigCreate, LLMConfigOut, LLMConfigUpdate

router = APIRouter(prefix="/llm-configs", tags=["llm-configs"])


def _to_out(row: LLMConfig) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "model": row.model,
        "base_url": row.base_url,
        "temperature": row.temperature,
        "max_tokens": row.max_tokens,
        "role": row.role,
        "has_api_key": bool(row.api_key),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.post("", response_model=LLMConfigOut, status_code=status.HTTP_201_CREATED)
async def create_llm_config(
    payload: LLMConfigCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = LLMConfig(**payload.model_dump())
    session.add(row)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.refresh(row)
    return _to_out(row)


@router.get("", response_model=list[LLMConfigOut])
async def list_llm_configs(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    res = await session.execute(select(LLMConfig).order_by(LLMConfig.id.desc()))
    return [_to_out(r) for r in res.scalars().all()]


@router.get("/{config_id}", response_model=LLMConfigOut)
async def get_llm_config(
    config_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(LLMConfig, config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LLMConfig not found")
    return _to_out(row)


@router.put("/{config_id}", response_model=LLMConfigOut)
async def update_llm_config(
    config_id: int,
    payload: LLMConfigUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(LLMConfig, config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LLMConfig not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    config_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(LLMConfig, config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LLMConfig not found")
    await session.delete(row)
    await session.commit()
