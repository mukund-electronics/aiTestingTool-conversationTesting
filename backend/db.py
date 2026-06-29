from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def _existing_columns(conn: AsyncConnection, table: str) -> set[str]:
    """Return the set of column names currently defined on ``table`` (SQLite)."""
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    # PRAGMA table_info rows are (cid, name, type, notnull, dflt_value, pk)
    return {row[1] for row in result}


async def _add_missing_columns(
    conn: AsyncConnection, table: str, columns: list[tuple[str, str]]
) -> None:
    """Add any of ``columns`` (name, sql_type) that are not already on ``table``.

    Lightweight stand-in for a migration tool: only the genuinely missing
    columns are altered in, so a real SQL error is no longer hidden behind a
    blanket "column already exists" assumption. ``table`` and the column
    definitions are hardcoded constants, never user input.
    """
    existing = await _existing_columns(conn, table)
    for col, col_type in columns:
        if col not in existing:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))


async def init_db() -> None:
    # Import models so their tables register on Base.metadata.
    from backend.models import (  # noqa: F401
        app_setting,
        endpoint_config,
        llm_config,
        test_case,
        test_run,
        turn,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Columns introduced after the initial schema. Added on startup only if
        # missing, so existing databases pick them up without a migration tool.
        await _add_missing_columns(conn, "turns", [
            ("turn_verdict",   "VARCHAR(32)"),
            ("turn_score",     "FLOAT"),
            ("turn_reasoning", "TEXT"),
            ("turn_analysis",  "TEXT"),
        ])
        await _add_missing_columns(conn, "test_cases", [
            ("eval_criteria",  "TEXT"),
            ("pass_threshold", "FLOAT"),
        ])
        await _add_missing_columns(conn, "test_runs", [
            ("run_analysis",                    "TEXT"),
            ("name",                            "VARCHAR(255)"),
            ("judge_criteria_override",         "TEXT"),
            ("skip_judge",                      "INTEGER DEFAULT 0"),
            ("conclusion",                      "TEXT"),
            ("request_body_template_override",  "TEXT"),
            ("reviewed",                        "INTEGER DEFAULT 0"),
            ("marker_color",                    "VARCHAR(16)"),
            ("step_mode",                       "INTEGER DEFAULT 0"),
            ("next_pending_query",              "TEXT"),
            ("ws_connect_delay_sec",            "REAL DEFAULT 2.0"),
        ])
        await _add_missing_columns(conn, "endpoint_configs", [
            ("protocol", "VARCHAR(16) DEFAULT 'http'"),
        ])
        await _add_missing_columns(conn, "llm_configs", [
            ("base_url", "TEXT"),
        ])
