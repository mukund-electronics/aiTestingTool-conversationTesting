"""HTTP caller for the endpoint under test. Handles auth, retries, timeouts."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from backend.models.endpoint_config import EndpointConfig


@dataclass
class EndpointCallResult:
    status_code: int | None
    response_json: Any
    response_text: str
    latency_ms: int
    error: str | None
    retries_used: int


def _apply_auth(
    headers: dict[str, str], auth_type: str, auth_value: str
) -> dict[str, str]:
    headers = dict(headers)
    if not auth_value:
        return headers
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth_value}"
    elif auth_type == "api_key":
        # Convention: "Header-Name:value". Default to X-API-Key.
        if ":" in auth_value:
            name, val = auth_value.split(":", 1)
            headers[name.strip()] = val.strip()
        else:
            headers["X-API-Key"] = auth_value
    elif auth_type == "basic":
        import base64

        token = base64.b64encode(auth_value.encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    return headers


async def call_endpoint(
    config: EndpointConfig,
    payload: Any,
) -> EndpointCallResult:
    """Call the configured endpoint with retries and return a structured result.

    Retries on connection errors, HTTP 429, and HTTP 5xx. Exponential backoff
    with jitter caps at ~8s per attempt.
    """
    headers = _apply_auth(dict(config.headers or {}), config.auth_type, config.auth_value)
    headers.setdefault("Content-Type", "application/json")

    method = config.http_method.upper()
    timeout = httpx.Timeout(config.timeout_seconds)
    max_retries = max(0, int(config.max_retries))

    last_error: str | None = None
    start_total = time.monotonic()
    retries_used = 0

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries + 1):
            try:
                t0 = time.monotonic()
                request_kwargs: dict[str, Any] = {"headers": headers}
                if method == "GET":
                    if isinstance(payload, dict):
                        request_kwargs["params"] = payload
                else:
                    request_kwargs["json"] = payload

                resp = await client.request(method, config.url, **request_kwargs)
                latency_ms = int((time.monotonic() - t0) * 1000)

                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                    if attempt < max_retries:
                        retries_used += 1
                        await asyncio.sleep(min(2 ** attempt, 8))
                        continue
                    return EndpointCallResult(
                        status_code=resp.status_code,
                        response_json=_safe_json(resp),
                        response_text=resp.text,
                        latency_ms=int((time.monotonic() - start_total) * 1000),
                        error=last_error,
                        retries_used=retries_used,
                    )

                return EndpointCallResult(
                    status_code=resp.status_code,
                    response_json=_safe_json(resp),
                    response_text=resp.text,
                    latency_ms=latency_ms,
                    error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                    retries_used=retries_used,
                )

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                    httpx.PoolTimeout, httpx.RemoteProtocolError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < max_retries:
                    retries_used += 1
                    await asyncio.sleep(min(2 ** attempt, 8))
                    continue
                return EndpointCallResult(
                    status_code=None,
                    response_json=None,
                    response_text="",
                    latency_ms=int((time.monotonic() - start_total) * 1000),
                    error=last_error,
                    retries_used=retries_used,
                )

    # Unreachable, but keeps type checkers happy.
    return EndpointCallResult(
        status_code=None,
        response_json=None,
        response_text="",
        latency_ms=int((time.monotonic() - start_total) * 1000),
        error=last_error or "unknown error",
        retries_used=retries_used,
    )


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None
