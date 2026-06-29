from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class AppSetting(Base):
    """Tiny key/value store for app-wide settings that must survive UI refreshes
    and restarts (e.g. the tester's name). Global to the deployment — fits the
    one-instance-per-tester distribution model."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
