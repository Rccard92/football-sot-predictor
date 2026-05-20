"""Risoluzione fixture per ID interno DB o api_fixture_id API-Football."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture

FIXTURE_NOT_FOUND_MSG = (
    "Fixture non trovata. Verifica di aver inserito l'ID interno DB oppure l'api_fixture_id API-Football."
)

ResolvedVia = Literal["db_id", "api_fixture_id"]

_FIXTURE_LOAD = (
    joinedload(Fixture.home_team),
    joinedload(Fixture.away_team),
    joinedload(Fixture.league),
)


def resolve_fixture(db: Session, raw_id: int) -> tuple[Fixture | None, ResolvedVia | None]:
    """Cerca prima fixtures.id, poi fixtures.api_fixture_id."""
    rid = int(raw_id)
    fx = db.scalar(
        select(Fixture)
        .where(Fixture.id == rid)
        .options(*_FIXTURE_LOAD),
    )
    if fx is not None:
        return fx, "db_id"

    fx = db.scalar(
        select(Fixture)
        .where(Fixture.api_fixture_id == rid)
        .options(*_FIXTURE_LOAD),
    )
    if fx is not None:
        return fx, "api_fixture_id"

    return None, None


def resolve_fixture_or_error(db: Session, raw_id: int) -> tuple[Fixture | None, dict[str, Any] | None]:
    fx, via = resolve_fixture(db, raw_id)
    if fx is None:
        return None, {
            "status": "error",
            "message": FIXTURE_NOT_FOUND_MSG,
            "input_id": int(raw_id),
        }
    return fx, {"resolved_via": via, "internal_fixture_id": int(fx.id)}
