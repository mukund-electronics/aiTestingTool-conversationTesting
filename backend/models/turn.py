from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_run_id: Mapped[int] = mapped_column(
        ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)

    user_query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_response_payload: Mapped[Any] = mapped_column(JSON, nullable=True)
    extracted_reply: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    simulator_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    turn_verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    turn_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    turn_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    test_run: Mapped["TestRun"] = relationship("TestRun", back_populates="turns")  # noqa: F821
