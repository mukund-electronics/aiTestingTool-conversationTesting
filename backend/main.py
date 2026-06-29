from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import (
    app_settings,
    batch_runs,
    config_transfer,
    endpoint_configs,
    llm_configs,
    runs,
    test_cases,
)
from backend.config import get_settings
from backend.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="conv-tester",
        version="2.0.0",
        description="Conversational AI testing tool",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(app_settings.router)
    app.include_router(batch_runs.router)
    app.include_router(config_transfer.router)
    app.include_router(endpoint_configs.router)
    app.include_router(llm_configs.router)
    app.include_router(test_cases.router)
    app.include_router(runs.router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
