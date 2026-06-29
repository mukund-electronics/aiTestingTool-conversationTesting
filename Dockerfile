# syntax=docker/dockerfile:1

FROM python:3.11-slim

# curl is needed for the backend healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv from the official image — much faster than pip install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── Dependency layer (cached until pyproject.toml / uv.lock changes) ─────────
COPY pyproject.toml uv.lock ./
# --no-install-project: install deps only; the project itself is not a
# distributable package — we import it via PYTHONPATH instead.
RUN uv sync --frozen --no-dev --no-install-project

# ── Application source ────────────────────────────────────────────────────────
COPY backend/    ./backend/
COPY ui/         ./ui/
COPY .streamlit/ ./.streamlit/

# Activate the venv and expose the project root for imports
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8000 8501
