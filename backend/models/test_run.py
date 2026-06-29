from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), nullable=False)
    endpoint_config_id: Mapped[int] = mapped_column(
        ForeignKey("endpoint_configs.id"), nullable=False
    )
    simulator_llm_id: Mapped[int] = mapped_column(ForeignKey("llm_configs.id"), nullable=False)
    judge_llm_id: Mapped[int] = mapped_column(ForeignKey("llm_configs.id"), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verdict_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    run_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    conclusion:   Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)

    judge_criteria_override: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    skip_judge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    request_body_template_override: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Tester annotations (set from the UI; not produced by the runner/judge).
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marker_color: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)

    # Step-mode execution: pause after every turn so the tester can review/edit
    # the next question before it is sent.
    step_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_pending_query: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    ws_connect_delay_sec: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)

    turns: Mapped[list["Turn"]] = relationship(  # noqa: F821
        "Turn",
        back_populates="test_run",
        cascade="all, delete-orphan",
        order_by="Turn.turn_number",
    )
