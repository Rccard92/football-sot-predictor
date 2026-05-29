from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Competition, League, Season
from app.services.api_football_client import ApiFootballClient, ApiFootballError

logger = logging.getLogger(__name__)

SERIE_A_KEY = "serie_a_italy_2025"
SERIE_A_PROVIDER_LEAGUE_ID = 135
SERIE_A_SEASON = 2025


class CompetitionService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def get_by_id(self, db: Session, competition_id: int) -> Competition | None:
        return db.get(Competition, competition_id)

    def get_by_id_or_raise(self, db: Session, competition_id: int) -> Competition:
        row = self.get_by_id(db, competition_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Competition {competition_id} non trovata")
        return row

    def get_by_key(self, db: Session, key: str) -> Competition | None:
        return db.scalar(select(Competition).where(Competition.key == key))

    def get_primary(self, db: Session) -> Competition | None:
        return db.scalar(
            select(Competition)
            .where(Competition.is_primary.is_(True), Competition.is_active.is_(True))
            .order_by(Competition.id.asc())
            .limit(1)
        )

    def get_default(self, db: Session) -> Competition | None:
        settings = get_settings()
        key = getattr(settings, "default_competition_key", SERIE_A_KEY)
        row = self.get_by_key(db, key)
        if row is not None and row.is_active:
            return row
        return self.get_primary(db)

    def list_active(self, db: Session) -> list[Competition]:
        return list(
            db.scalars(
                select(Competition)
                .where(Competition.is_active.is_(True))
                .order_by(Competition.is_primary.desc(), Competition.name.asc())
            )
        )

    def resolve_or_raise(
        self,
        db: Session,
        *,
        competition_id: int | None = None,
        key: str | None = None,
        allow_default: bool = True,
    ) -> Competition:
        if competition_id is not None:
            return self.get_by_id_or_raise(db, competition_id)
        if key:
            row = self.get_by_key(db, key)
            if row is None:
                raise HTTPException(status_code=404, detail=f"Competition key={key!r} non trovata")
            return row
        if allow_default:
            row = self.get_default(db)
            if row is not None:
                return row
        raise HTTPException(
            status_code=400,
            detail="competition_id richiesto: nessuna competition default configurata",
        )

    def discover(
        self,
        db: Session,
        *,
        country: str,
        name_query: str,
        season: int,
    ) -> dict[str, Any]:
        _ = db
        try:
            body = self._client.get(
                "leagues",
                {"country": country.strip(), "search": name_query.strip()},
            )
        except ApiFootballError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        candidates: list[dict[str, Any]] = []
        for item in body.get("response") or []:
            lg = item.get("league") or {}
            seasons = item.get("seasons") or []
            has_season = any(isinstance(s, dict) and s.get("year") == season for s in seasons)
            if not has_season:
                continue
            country_name = (item.get("country") or {}).get("name")
            candidates.append(
                {
                    "provider_league_id": int(lg["id"]),
                    "name": str(lg.get("name") or ""),
                    "country": country_name,
                    "season": season,
                    "logo": lg.get("logo"),
                    "raw_payload": item,
                }
            )

        ambiguous = len(candidates) > 1
        message = None
        if not candidates:
            message = f"Nessuna lega trovata per country={country!r}, search={name_query!r}, season={season}"
        elif ambiguous:
            message = "Più leghe candidate: selezionare manualmente prima di creare la competition"

        return {
            "candidates": candidates,
            "ambiguous": ambiguous,
            "message": message,
        }

    def create(self, db: Session, data: dict[str, Any]) -> Competition:
        existing = self.get_by_key(db, str(data["key"]))
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Competition key={data['key']!r} già esistente")

        league = db.scalar(
            select(League).where(League.api_league_id == int(data["provider_league_id"]))
        )
        season_row = None
        if league is not None:
            season_row = db.scalar(
                select(Season).where(
                    Season.league_id == league.id,
                    Season.year == int(data["season"]),
                )
            )

        if data.get("is_primary"):
            db.execute(update(Competition).values(is_primary=False))

        row = Competition(
            key=str(data["key"]),
            name=str(data["name"]),
            country=data.get("country"),
            provider=str(data.get("provider") or "api_sports"),
            provider_league_id=int(data["provider_league_id"]),
            season=int(data["season"]),
            timezone=data.get("timezone"),
            is_active=bool(data.get("is_active", True)),
            is_primary=bool(data.get("is_primary", False)),
            pre_match_cron_enabled=bool(data.get("pre_match_cron_enabled", False)),
            status=data.get("status"),
            league_id=league.id if league else None,
            season_id=season_row.id if season_row else None,
            raw_payload=data.get("raw_payload"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def patch(self, db: Session, competition_id: int, data: dict[str, Any]) -> Competition:
        row = self.get_by_id_or_raise(db, competition_id)
        if data.get("is_primary") is True:
            db.execute(update(Competition).values(is_primary=False))
        for field in ("is_active", "is_primary", "pre_match_cron_enabled", "status", "timezone"):
            if field in data and data[field] is not None:
                setattr(row, field, data[field])
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def resolve_for_season_year(self, db: Session, season_year: int) -> Competition:
        """Retrocompatibilità route /serie-a/{season}."""
        row = db.scalar(
            select(Competition).where(
                Competition.season == season_year,
                Competition.provider_league_id == get_settings().default_league_id,
            )
        )
        if row is not None:
            return row
        row = self.get_by_key(db, f"serie_a_italy_{season_year}")
        if row is not None:
            return row
        return self.resolve_or_raise(db, key=SERIE_A_KEY)

    def ensure_serie_a_competition(self, db: Session, season_year: int = SERIE_A_SEASON) -> Competition:
        key = f"serie_a_italy_{season_year}"
        existing = self.get_by_key(db, key)
        if existing is not None:
            return existing

        settings = get_settings()
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        season_row = None
        if league is not None:
            season_row = db.scalar(
                select(Season).where(Season.league_id == league.id, Season.year == season_year)
            )

        db.execute(update(Competition).values(is_primary=False))
        row = Competition(
            key=key,
            name="Serie A",
            country="Italy",
            provider="api_sports",
            provider_league_id=settings.default_league_id,
            season=season_year,
            timezone="Europe/Rome",
            is_active=True,
            is_primary=True,
            pre_match_cron_enabled=True,
            status="active",
            league_id=league.id if league else None,
            season_id=season_row.id if season_row else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
