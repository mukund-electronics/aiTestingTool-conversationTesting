from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class EndpointConfig(Base):
    __tablename__ = "endpoint_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    protocol: Mapped[str] = mapped_column(String(16), nullable=False, default="http")
    http_method: Mapped[str] = mapped_column(String(10), nullable=False, default="POST")
    headers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    request_body_template: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    response_extractors: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    auth_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
