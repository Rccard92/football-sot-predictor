"""Mixin competition_id per tabelle scoped per campionato."""

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class CompetitionScopedMixin:
    competition_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
