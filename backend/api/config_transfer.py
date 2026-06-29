"""Config bundle export / import.

GET  /config/export  → JSON file with all test cases, LLM configs, endpoint configs.
POST /config/import  → Accept that JSON and add only records that don't already
                       exist (matched by name). Import is strictly additive: an
                       existing record is never updated or deleted — a same-name
                       entry in the bundle is reported under "skipped".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models.endpoint_config import EndpointConfig
from backend.models.llm_config import LLMConfig
from backend.models.test_case import TestCase

router = APIRouter(prefix="/config", tags=["config-transfer"])

_BUNDLE_VERSION = 1


# ── serialisers ──────────────────────────────────────────────────────────────

def _tc_to_dict(tc: TestCase) -> dict:
    return {
        "name": tc.name,
        "description": tc.description or "",
        "usecase": tc.usecase or "",
        "persona": tc.persona or "",
        "known_facts": tc.known_facts or [],
        "success_criteria": tc.success_criteria or "",
        "starting_query": tc.starting_query or "",
        "max_turns": tc.max_turns,
        "mode": tc.mode,
        "eval_criteria": tc.eval_criteria,
        "pass_threshold": tc.pass_threshold,
    }


def _llm_to_dict(llm: LLMConfig) -> dict:
    return {
        "name": llm.name,
        "provider": llm.provider,
        "model": llm.model,
        "base_url": getattr(llm, "base_url", None),
        "api_key": llm.api_key or "",   # exported in plaintext — treat file as sensitive
        "temperature": llm.temperature,
        "max_tokens": llm.max_tokens,
        "role": llm.role,
    }


def _ep_to_dict(ep: EndpointConfig) -> dict:
    return {
        "name": ep.name,
        "url": ep.url,
        "protocol": getattr(ep, "protocol", "http"),
        "http_method": ep.http_method,
        "headers": ep.headers or {},
        "request_body_template": ep.request_body_template or "{}",
        "response_extractors": ep.response_extractors or {},
        "auth_type": ep.auth_type or "none",
        "auth_value": ep.auth_value or "",
        "timeout_seconds": ep.timeout_seconds,
        "max_retries": ep.max_retries,
    }


# ── export ────────────────────────────────────────────────────────────────────

@router.get("/export")
async def export_config(session: AsyncSession = Depends(get_session)) -> Response:
    tcs  = list((await session.execute(select(TestCase).order_by(TestCase.id))).scalars().all())
    llms = list((await session.execute(select(LLMConfig).order_by(LLMConfig.id))).scalars().all())
    eps  = list((await session.execute(select(EndpointConfig).order_by(EndpointConfig.id))).scalars().all())

    bundle: dict[str, Any] = {
        "version":     _BUNDLE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "test_cases":       [_tc_to_dict(tc)  for tc  in tcs],
        "llm_configs":      [_llm_to_dict(llm) for llm in llms],
        "endpoint_configs": [_ep_to_dict(ep)   for ep  in eps],
    }

    return Response(
        content=json.dumps(bundle, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="conv_tester_config.json"'},
    )


# ── import ────────────────────────────────────────────────────────────────────

class _ImportResult:
    def __init__(self) -> None:
        self.created: dict[str, list[str]] = {
            "test_cases": [], "llm_configs": [], "endpoint_configs": []
        }
        self.skipped: dict[str, list[str]] = {
            "test_cases": [], "llm_configs": [], "endpoint_configs": []
        }
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {"created": self.created, "skipped": self.skipped, "errors": self.errors}


@router.post("/import")
async def import_config(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict:
    if payload.get("version", 1) != _BUNDLE_VERSION:
        raise HTTPException(400, f"Unsupported bundle version: {payload.get('version')}")

    result = _ImportResult()

    # ── test cases ──
    existing_tc_names = set(
        (await session.execute(select(TestCase.name))).scalars().all()
    )
    for item in payload.get("test_cases", []):
        name = item.get("name", "")
        if not name:
            result.errors.append("test_case with empty name skipped")
            continue
        if name in existing_tc_names:
            result.skipped["test_cases"].append(name)
            continue
        try:
            session.add(TestCase(
                name=name,
                description=item.get("description", ""),
                usecase=item.get("usecase", ""),
                persona=item.get("persona", ""),
                known_facts=item.get("known_facts") or [],
                success_criteria=item.get("success_criteria", ""),
                starting_query=item.get("starting_query", ""),
                max_turns=int(item.get("max_turns", 10)),
                mode=item.get("mode", "multi_turn"),
                eval_criteria=item.get("eval_criteria"),
                pass_threshold=float(item.get("pass_threshold", 0.7)),
            ))
            result.created["test_cases"].append(name)
        except Exception as exc:
            result.errors.append(f"test_case '{name}': {exc}")

    # ── LLM configs ──
    existing_llm_names = set(
        (await session.execute(select(LLMConfig.name))).scalars().all()
    )
    for item in payload.get("llm_configs", []):
        name = item.get("name", "")
        if not name:
            result.errors.append("llm_config with empty name skipped")
            continue
        if name in existing_llm_names:
            result.skipped["llm_configs"].append(name)
            continue
        try:
            session.add(LLMConfig(
                name=name,
                provider=item.get("provider", "openai"),
                model=item.get("model", ""),
                base_url=item.get("base_url") or None,
                api_key=item.get("api_key", ""),
                temperature=float(item.get("temperature", 0.7)),
                max_tokens=int(item.get("max_tokens", 1024)),
                role=item.get("role", "either"),
            ))
            result.created["llm_configs"].append(name)
        except Exception as exc:
            result.errors.append(f"llm_config '{name}': {exc}")

    # ── endpoint configs ──
    existing_ep_names = set(
        (await session.execute(select(EndpointConfig.name))).scalars().all()
    )
    for item in payload.get("endpoint_configs", []):
        name = item.get("name", "")
        if not name:
            result.errors.append("endpoint_config with empty name skipped")
            continue
        if name in existing_ep_names:
            result.skipped["endpoint_configs"].append(name)
            continue
        try:
            session.add(EndpointConfig(
                name=name,
                url=item.get("url", ""),
                protocol=item.get("protocol", "http"),
                http_method=item.get("http_method", "POST"),
                headers=item.get("headers") or {},
                request_body_template=item.get("request_body_template", "{}"),
                response_extractors=item.get("response_extractors") or {},
                auth_type=item.get("auth_type", "none"),
                auth_value=item.get("auth_value", ""),
                timeout_seconds=int(item.get("timeout_seconds", 30)),
                max_retries=int(item.get("max_retries", 3)),
            ))
            result.created["endpoint_configs"].append(name)
        except Exception as exc:
            result.errors.append(f"endpoint_config '{name}': {exc}")

    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(500, f"Commit failed: {exc}") from exc

    return result.to_dict()
