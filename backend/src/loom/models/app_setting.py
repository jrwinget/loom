from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class AppSetting(UUIDMixin, TimestampMixin, Base):
    """runtime, admin-editable app configuration as a key-value row.

    used for settings that must change without a restart or env edit —
    currently the AI engine config (key ``"ai"``). secrets stored here
    (e.g. a user-supplied api key) live in the local database, which on
    the lite profile is the user's own machine.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
