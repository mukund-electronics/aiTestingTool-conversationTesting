from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class RunBatch(Base):
    __tablename__ = "run_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    test_case_name: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint_name: Mapped[str] = mapped_column(String(255), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    run_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    @property
    def run_ids(self) -> list[int]:
        return json.loads(self.run_ids_json)
