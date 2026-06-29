from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    usecase: Mapped[str] = mapped_column(Text, nullable=False)
    persona: Mapped[str] = mapped_column(Text, nullable=False, default="")
    known_facts: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    success_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    starting_query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="multi_turn")
    eval_criteria: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True, default=None)
    pass_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
