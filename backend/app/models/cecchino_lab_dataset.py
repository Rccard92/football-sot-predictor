"""Dataset storico Cecchino Lab (campionato + stagione, isolato dalle tabelle operative)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

SOURCE_PROVIDER_FOOTBALL_DATA_UK = "football-data.co.uk"

DATASET_STATUS_ACTIVE = "active"
DATASET_STATUS_EMPTY = "empty"

QUALITY_STATUS_COMPLETE = "complete"
QUALITY_STATUS_PARTIAL = "partial"
QUALITY_STATUS_POOR = "poor"
QUALITY_STATUS_UNKNOWN = "unknown"


class CecchinoLabDataset(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_datasets"
    __table_args__ = (
        UniqueConstraint(
            "competition_name",
            "country",
            "season_label",
            "source_provider",
            name="uq_cecchino_lab_datasets_comp_country_season_source",
        ),
        Index("ix_cecchino_lab_datasets_country", "country"),
        Index("ix_cecchino_lab_datasets_season_label", "season_label"),
        Index("ix_cecchino_lab_datasets_quality_status", "data_quality_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    competition_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    division_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    season_label: Mapped[str] = mapped_column(String(32), nullable=False)
    start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Rome")
    source_provider: Mapped[str] = mapped_column(
        String(64), nullable=False, default=SOURCE_PROVIDER_FOOTBALL_DATA_UK
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DATASET_STATUS_EMPTY)
    matches_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_quality_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=QUALITY_STATUS_UNKNOWN
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
