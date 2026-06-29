"""HTTP helpers for talking to the FastAPI backend."""

from __future__ import annotations

import os
from typing import Any

import httpx

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND_URL, timeout=30.0)


def api_get(path: str, **params) -> Any:
    with _client() as c:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()


def api_post(path: str, payload: dict) -> Any:
    with _client() as c:
        r = c.post(path, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text}")
        return r.json()


def api_put(path: str, payload: dict) -> Any:
    with _client() as c:
        r = c.put(path, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text}")
        return r.json()


def api_patch(path: str, payload: dict) -> Any:
    with _client() as c:
        r = c.patch(path, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text}")
        return r.json()


def api_delete(path: str) -> None:
    with _client() as c:
        r = c.delete(path)
        if r.status_code >= 400 and r.status_code != 404:
            raise RuntimeError(f"{r.status_code}: {r.text}")
