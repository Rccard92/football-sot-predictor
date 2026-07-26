"""Anomalie e issue di qualità dati Cecchino Lab."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


class CecchinoLabDataIssue(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_data_issues"
    __table_args__ = (
        Index("ix_cecchino_lab_data_issues_import_id", "import_id"),
        Index("ix_cecchino_lab_data_issues_match_id", "match_id"),
        Index("ix_cecchino_lab_data_issues_severity", "severity"),
        Index("ix_cecchino_lab_data_issues_issue_code", "issue_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_matches.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
