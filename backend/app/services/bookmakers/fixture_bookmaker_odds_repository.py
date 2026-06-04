"""Repository upsert/query fixture_bookmaker_odds (per selection)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.fixture_bookmaker_odds import FixtureBookmakerOdds


def upsert_selection_odds(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
    provider_source: str,
    provider_bookmaker_id: str,
    bookmaker_name: str,
    normalized_market: str,
    selection_key: str,
    odds_value: float,
    selection_label: str | None = None,
    market_label: str | None = None,
    provider_fixture_id: int | None = None,
    provider_market_id: str | None = None,
    raw_payload_json: dict[str, Any] | None = None,
    odds_updated_at: datetime | None = None,
) -> FixtureBookmakerOdds:
    row = db.scalar(
        select(FixtureBookmakerOdds).where(
            FixtureBookmakerOdds.competition_id == int(competition_id),
            FixtureBookmakerOdds.fixture_id == int(fixture_id),
            FixtureBookmakerOdds.provider_source == provider_source,
            FixtureBookmakerOdds.provider_bookmaker_id == str(provider_bookmaker_id),
            FixtureBookmakerOdds.normalized_market == normalized_market,
            FixtureBookmakerOdds.selection_key == selection_key,
        ),
    )
    ts = odds_updated_at or datetime.now(timezone.utc)
    if row is None:
        row = FixtureBookmakerOdds(
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
            provider_source=provider_source,
            provider_fixture_id=provider_fixture_id,
            provider_bookmaker_id=str(provider_bookmaker_id),
            bookmaker_name=bookmaker_name,
            normalized_market=normalized_market,
            market_label=market_label,
            selection_key=selection_key,
            selection_label=selection_label,
            odds_value=float(odds_value),
            provider_market_id=provider_market_id,
            raw_payload_json=raw_payload_json,
            odds_updated_at=ts,
        )
        db.add(row)
    else:
        row.bookmaker_name = bookmaker_name
        row.odds_value = float(odds_value)
        row.selection_label = selection_label
        row.market_label = market_label
        row.provider_fixture_id = provider_fixture_id
        row.provider_market_id = provider_market_id
        if raw_payload_json is not None:
            row.raw_payload_json = raw_payload_json
        row.odds_updated_at = ts
    db.flush()
    return row


def upsert_fixture_odds_1x2(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
    provider_source: str,
    provider_bookmaker_id: str,
    bookmaker_name: str,
    normalized_market: str,
    home_odds: float | None = None,
    draw_odds: float | None = None,
    away_odds: float | None = None,
    provider_fixture_id: int | None = None,
    provider_market_id: str | None = None,
    market_label: str | None = None,
    raw_payload_json: dict[str, Any] | None = None,
    odds_updated_at: datetime | None = None,
) -> int:
    """Compat: scrive fino a 3 selection HOME/DRAW/AWAY. Ritorna righe upsertate."""
    saved = 0
    for sk, sl, val in (
        ("HOME", "1", home_odds),
        ("DRAW", "X", draw_odds),
        ("AWAY", "2", away_odds),
    ):
        if val is None:
            continue
        upsert_selection_odds(
            db,
            competition_id=competition_id,
            fixture_id=fixture_id,
            provider_source=provider_source,
            provider_bookmaker_id=provider_bookmaker_id,
            bookmaker_name=bookmaker_name,
            normalized_market=normalized_market,
            selection_key=sk,
            selection_label=sl,
            odds_value=float(val),
            market_label=market_label,
            provider_fixture_id=provider_fixture_id,
            provider_market_id=provider_market_id,
            raw_payload_json=raw_payload_json,
            odds_updated_at=odds_updated_at,
        )
        saved += 1
    return saved


def list_odds_for_fixtures(
    db: Session,
    *,
    competition_id: int,
    fixture_ids: list[int],
    normalized_market: str | None = None,
    provider_source: str | None = None,
    bookmaker_name: str | None = None,
    provider_bookmaker_ids: list[str] | None = None,
) -> list[FixtureBookmakerOdds]:
    if not fixture_ids:
        return []
    q = select(FixtureBookmakerOdds).where(
        FixtureBookmakerOdds.competition_id == int(competition_id),
        FixtureBookmakerOdds.fixture_id.in_([int(x) for x in fixture_ids]),
    )
    if normalized_market:
        q = q.where(FixtureBookmakerOdds.normalized_market == normalized_market)
    if provider_source:
        q = q.where(FixtureBookmakerOdds.provider_source == provider_source)
    if bookmaker_name:
        q = q.where(FixtureBookmakerOdds.bookmaker_name == bookmaker_name)
    if provider_bookmaker_ids:
        q = q.where(FixtureBookmakerOdds.provider_bookmaker_id.in_(provider_bookmaker_ids))
    return list(db.scalars(q).all())


def list_odds_for_fixture(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
    provider_source: str | None = None,
) -> list[FixtureBookmakerOdds]:
    return list_odds_for_fixtures(
        db,
        competition_id=competition_id,
        fixture_ids=[int(fixture_id)],
        provider_source=provider_source,
    )


def delete_odds_for_fixture_market(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
    provider_source: str,
    normalized_market: str,
) -> int:
    result = db.execute(
        delete(FixtureBookmakerOdds).where(
            FixtureBookmakerOdds.competition_id == int(competition_id),
            FixtureBookmakerOdds.fixture_id == int(fixture_id),
            FixtureBookmakerOdds.provider_source == provider_source,
            FixtureBookmakerOdds.normalized_market == normalized_market,
        ),
    )
    return int(result.rowcount or 0)
