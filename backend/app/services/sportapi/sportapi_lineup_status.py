"""Stato rapido formazione SportAPI per UI upcoming / report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FixtureProviderLineup
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI

# Per competition multi-campionato (es. Brasileirão), SportAPI è la fonte principale
# per disponibilità formazioni. Non usare solo FixtureLineup (API-Football) per readout/flag.

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
        return "Probabili aggiornate"
    return "Da aggiornare"


def next_round_sportapi_lineup_stats(db: Session, fixture_ids: list[int]) -> dict[str, Any]:
    """Conteggi lineups SportAPI per un insieme di fixture (es. prossimo turno)."""
    total = len(fixture_ids)
    if not fixture_ids:
        return {
            "next_round_fixture_count": 0,
            "next_round_sportapi_lineups_count": 0,
            "next_round_coverage_pct": 0.0,
            "confirmed_lineups_count": 0,
            "probable_lineups_count": 0,
        }
    rows = list(
        db.scalars(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id.in_([int(x) for x in fixture_ids]),
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        ).all(),
    )
    by_fx = {int(r.fixture_id): r for r in rows}
    sportapi_count = len(by_fx)
    confirmed = sum(1 for r in by_fx.values() if bool(r.confirmed))
    probable = sportapi_count - confirmed
    pct = round(100.0 * sportapi_count / max(total, 1), 1)
    return {
        "next_round_fixture_count": total,
        "next_round_sportapi_lineups_count": sportapi_count,
        "next_round_coverage_pct": pct,
        "confirmed_lineups_count": confirmed,
        "probable_lineups_count": probable,
    }


def build_lineup_coverage_messages(
    *,
    coverage: dict[str, Any],
    api_football_lineups_count: int = 0,
) -> tuple[list[str], list[str]]:
    """
    Ritorna (warnings, info) per UI Prossima giornata.
    SportAPI è fonte principale; API-Football usato solo se entrambe assenti.
    """
    warnings: list[str] = []
    info: list[str] = []
    total = int(coverage.get("next_round_fixture_count") or 0)
    sportapi_n = int(coverage.get("next_round_sportapi_lineups_count") or 0)

    if total <= 0:
        return warnings, info

    if sportapi_n <= 0 and api_football_lineups_count <= 0:
        warnings.append("Lineups non disponibili: prediction generate senza impatto formazioni.")
    elif 0 < sportapi_n < total:
        warnings.append(f"Formazioni disponibili solo per {sportapi_n}/{total} partite.")
    elif sportapi_n >= total and total > 0:
        info.append("Formazioni SportAPI disponibili per tutto il turno.")

    return warnings, info


def competition_sportapi_lineup_confirmed_counts(db: Session, competition_id: int) -> dict[str, int]:
    """Conteggi confirmed/probable SportAPI per intera competition."""
    rows = list(
        db.scalars(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.competition_id == int(competition_id),
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        ).all(),
    )
    confirmed = sum(1 for r in rows if bool(r.confirmed))
    total = len(rows)
    return {
        "confirmed_lineups_count": confirmed,
        "probable_lineups_count": total - confirmed,
        "sportapi_lineup_rows_count": total,
    }


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
