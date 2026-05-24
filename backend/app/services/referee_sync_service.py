"""Sync arbitro assegnato da API-Sports per singola fixture."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureReferee, Referee, Team
from app.models.fixture_referee import SOURCE_API_SPORTS
from app.models.referee import PROVIDER_API_SPORTS
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.api_football_fixture_detail import match_label_from_detail, parse_fixture_detail_item
from app.services.referee_name_normalize import normalize_referee_name


class RefereeSyncService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def _resolve_fixture(
        self,
        db: Session,
        *,
        fixture_id: int | None,
        api_fixture_id: int | None,
    ) -> Fixture | None:
        if fixture_id is not None:
            return db.get(Fixture, int(fixture_id))
        if api_fixture_id is not None:
            return db.scalar(select(Fixture).where(Fixture.api_fixture_id == int(api_fixture_id)))
        return None

    def _match_name(self, db: Session, fx: Fixture) -> str:
        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        return f"{home.name if home else 'Casa'} - {away.name if away else 'Trasferta'}"

    def _get_or_create_referee(self, db: Session, name: str, raw: dict[str, Any] | None) -> Referee:
        norm = normalize_referee_name(name)
        row = db.scalar(
            select(Referee).where(
                Referee.provider == PROVIDER_API_SPORTS,
                Referee.normalized_name == norm,
            ),
        )
        if row is None:
            row = Referee(
                provider=PROVIDER_API_SPORTS,
                name=name.strip(),
                normalized_name=norm,
                raw_payload=raw,
            )
            db.add(row)
            db.flush()
        else:
            row.name = name.strip()
            if raw:
                row.raw_payload = raw
        return row

    def _upsert_fixture_referee(
        self,
        db: Session,
        *,
        fx: Fixture,
        referee: Referee | None,
        referee_name: str | None,
        assigned_at: datetime | None,
        raw_item: dict[str, Any],
    ) -> FixtureReferee:
        link = db.scalar(
            select(FixtureReferee).where(
                FixtureReferee.fixture_id == int(fx.id),
                FixtureReferee.source == SOURCE_API_SPORTS,
            ),
        )
        if link is None:
            link = FixtureReferee(
                fixture_id=int(fx.id),
                api_fixture_id=int(fx.api_fixture_id),
                source=SOURCE_API_SPORTS,
            )
            db.add(link)
        link.api_fixture_id = int(fx.api_fixture_id)
        link.referee_id = int(referee.id) if referee else None
        link.referee_name = referee_name
        link.assigned_at = assigned_at
        link.raw_payload = raw_item
        return link

    def sync_fixture(
        self,
        db: Session,
        *,
        fixture_id: int | None = None,
        api_fixture_id: int | None = None,
    ) -> dict[str, Any]:
        fx = self._resolve_fixture(db, fixture_id=fixture_id, api_fixture_id=api_fixture_id)
        if fx is None:
            return {
                "status": "error",
                "message": "Fixture non trovata in DB",
                "fixture_id": fixture_id,
                "api_fixture_id": api_fixture_id,
                "saved": False,
            }

        api_id = int(fx.api_fixture_id)
        try:
            item = self._client.get_fixture_by_id(api_id)
        except ApiFootballError as exc:
            return {
                "status": "error",
                "message": str(exc),
                "fixture_id": int(fx.id),
                "api_fixture_id": api_id,
                "saved": False,
            }

        if not item:
            return {
                "status": "error",
                "message": "Fixture non trovata su API-Sports",
                "fixture_id": int(fx.id),
                "api_fixture_id": api_id,
                "saved": False,
            }

        detail = parse_fixture_detail_item(item)
        match_name = match_label_from_detail(detail) if detail.get("home_team_name") else self._match_name(db, fx)
        referee_name = detail.get("referee")
        kickoff = detail.get("kickoff_at")

        if not referee_name:
            fx.referee = None
            self._upsert_fixture_referee(
                db,
                fx=fx,
                referee=None,
                referee_name=None,
                assigned_at=kickoff,
                raw_item=item,
            )
            db.commit()
            return {
                "status": "success",
                "fixture_id": int(fx.id),
                "api_fixture_id": api_id,
                "match": match_name,
                "referee": None,
                "saved": False,
                "reason": "referee_not_available",
                "message": "Arbitro non ancora disponibile",
            }

        ref_row = self._get_or_create_referee(db, referee_name, {"source": "api_sports_fixture"})
        fx.referee = referee_name[:255]
        self._upsert_fixture_referee(
            db,
            fx=fx,
            referee=ref_row,
            referee_name=referee_name,
            assigned_at=kickoff or datetime.now(timezone.utc),
            raw_item=item,
        )
        db.commit()

        return {
            "status": "success",
            "fixture_id": int(fx.id),
            "api_fixture_id": api_id,
            "match": match_name,
            "referee": referee_name,
            "referee_id": int(ref_row.id),
            "saved": True,
        }
