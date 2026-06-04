"""Repository upsert/query fixture_bookmaker_odds."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.fixture_bookmaker_odds import FixtureBookmakerOdds


def upsert_fixture_odds(
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
        ),
    )
    ts = odds_updated_at or datetime.now(timezone.utc)
    if row is None:
        row = FixtureBookmakerOdds(
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
            provider_source=provider_source,
            provider_bookmaker_id=str(provider_bookmaker_id),
            bookmaker_name=bookmaker_name,
            normalized_market=normalized_market,
            provider_market_id=provider_market_id,
            home_odds=home_odds,
            draw_odds=draw_odds,
            away_odds=away_odds,
            raw_payload_json=raw_payload_json,
            odds_updated_at=ts,
        )
        db.add(row)
    else:
        row.bookmaker_name = bookmaker_name
        row.provider_market_id = provider_market_id
        row.home_odds = home_odds
        row.draw_odds = draw_odds
        row.away_odds = away_odds
        row.raw_payload_json = raw_payload_json
        row.odds_updated_at = ts
    db.flush()
    return row


def list_odds_for_fixtures(
    db: Session,
    *,
    competition_id: int,
    fixture_ids: list[int],
    normalized_market: str | None = None,
    provider_source: str | None = None,
    bookmaker_name: str | None = None,
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
    return list(db.scalars(q).all())


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
