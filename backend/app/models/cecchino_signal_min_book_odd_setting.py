"""Soglie minime quota book configurabili — Monitoraggio Segnali Cecchino."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class CecchinoSignalMinBookOddSetting(Base, TimestampMixin):
    __tablename__ = "cecchino_signal_min_book_odd_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_market_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    min_book_odd: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
