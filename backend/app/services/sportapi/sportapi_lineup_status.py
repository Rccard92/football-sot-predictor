"""Stato rapido formazione SportAPI per UI upcoming / report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FixtureProviderLineup
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI

FORMATION_RECENT_HOURS = 6.0


def _age_hours(fetched_at: datetime | None) -> float | None:
    if fetched_at is None:
        return None
    now = datetime.now(timezone.utc)
    ft = fetched_at
    if ft.tzinfo is None:
        ft = ft.replace(tzinfo=timezone.utc)
    return (now - ft.astimezone(timezone.utc)).total_seconds() / 3600.0


def formation_status_label(
    *,
    has_lineup: bool,
    confirmed: bool | None,
    fetched_at: datetime | None,
) -> str:
    if not has_lineup:
        return "Mancante"
    if confirmed is True:
        return "Ufficiale"
    age = _age_hours(fetched_at)
    if age is not None and age <= FORMATION_RECENT_HOURS:
        return "Aggiornata"
    return "Da aggiornare"


def lineup_row_for_fixture(db: Session, fixture_id: int) -> FixtureProviderLineup | None:
    return db.scalar(
        select(FixtureProviderLineup).where(
            FixtureProviderLineup.fixture_id == int(fixture_id),
            FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
        ),
    )


def formation_status_payload(db: Session, fixture_id: int) -> dict[str, Any]:
    row = lineup_row_for_fixture(db, int(fixture_id))
    if row is None:
        return {
            "label": "Mancante",
            "has_lineup": False,
            "confirmed": None,
            "fetched_at": None,
        }
    fetched_iso = row.fetched_at.isoformat() if row.fetched_at else None
    return {
        "label": formation_status_label(
            has_lineup=True,
            confirmed=bool(row.confirmed),
            fetched_at=row.fetched_at,
        ),
        "has_lineup": True,
        "confirmed": bool(row.confirmed),
        "fetched_at": fetched_iso,
    }


def load_lineups_by_fixture_ids(db: Session, fixture_ids: list[int]) -> dict[int, FixtureProviderLineup]:
    if not fixture_ids:
        return {}
    rows = list(
        db.scalars(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id.in_([int(x) for x in fixture_ids]),
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        ).all(),
    )
    return {int(r.fixture_id): r for r in rows}


def formation_status_from_lineup(row: FixtureProviderLineup | None) -> dict[str, Any]:
    if row is None:
        return {
            "label": "Mancante",
            "has_lineup": False,
            "confirmed": None,
            "fetched_at": None,
        }
    fetched_iso = row.fetched_at.isoformat() if row.fetched_at else None
    return {
        "label": formation_status_label(
            has_lineup=True,
            confirmed=bool(row.confirmed),
            fetched_at=row.fetched_at,
        ),
        "has_lineup": True,
        "confirmed": bool(row.confirmed),
        "fetched_at": fetched_iso,
    }
