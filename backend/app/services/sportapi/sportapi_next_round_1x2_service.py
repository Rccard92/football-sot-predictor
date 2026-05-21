"""Batch quote 1X2 prossimo turno Serie A (sequenziale, solo informativo)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Fixture, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.models.sportapi_fixture_odds_snapshot import MARKET_1X2, SportApiFixtureOddsSnapshot
from app.models.sportapi_odds_provider import DEFAULT_PROVIDER_SLUG, SportApiOddsProvider
from app.services.sportapi.sportapi_client import SportApiClient, SportApiError
from app.services.sportapi.sportapi_event_odds_test_service import candidate_provider_ids
from app.services.sportapi.sportapi_odds_1x2_normalize import extract_1x2_from_event_odds
from app.services.sportapi.sportapi_round_refresh_service import SportApiRoundRefreshService

logger = logging.getLogger(__name__)

SLEEP_BETWEEN_FIXTURES_S = 0.3


class SportApiNextRound1x2Service:
    def __init__(
        self,
        client: SportApiClient | None = None,
        round_svc: SportApiRoundRefreshService | None = None,
    ) -> None:
        self._client = client or SportApiClient()
        self._round_svc = round_svc or SportApiRoundRefreshService()

    def run(
        self,
        db: Session,
        *,
        provider_slug: str = DEFAULT_PROVIDER_SLUG,
        season_year: int | None = None,
        force: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        _ = force  # riservato per refresh forzato futuro
        slug = provider_slug.strip().lower()
        year = int(season_year or get_settings().default_season)

        provider_row = db.scalar(
            select(SportApiOddsProvider).where(SportApiOddsProvider.provider_slug == slug),
        )
        if provider_row is None:
            return {
                "status": "error",
                "message": f"Provider {slug} non in DB. Esegui sync IT/app e sync-detail.",
                "processed": 0,
                "skipped_no_mapping": 0,
                "errors": [],
                "rows": [],
            }

        candidate_ids = candidate_provider_ids(provider_row)
        if not candidate_ids:
            return {
                "status": "error",
                "message": f"Provider {slug} senza id candidati. Esegui sync-detail.",
                "processed": 0,
                "skipped_no_mapping": 0,
                "errors": [],
                "rows": [],
            }

        fixtures = self._round_svc.upcoming_next_round_fixtures(db, year, limit=limit)
        if not fixtures:
            return {
                "status": "success",
                "message": "Nessuna fixture nel prossimo turno",
                "processed": 0,
                "skipped_no_mapping": 0,
                "errors": [],
                "rows": [],
            }

        team_cache: dict[int, Team] = {}
        processed = 0
        skipped_no_mapping = 0
        errors: list[str] = []
        rows: list[dict[str, Any]] = []

        for idx, fx in enumerate(fixtures):
            if idx > 0:
                time.sleep(SLEEP_BETWEEN_FIXTURES_S)

            mapping = db.scalar(
                select(FixtureProviderMapping).where(
                    FixtureProviderMapping.fixture_id == int(fx.id),
                    FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                ),
            )
            if mapping is None or not mapping.provider_event_id:
                skipped_no_mapping += 1
                rows.append(self._row_skeleton(fx, team_cache, db, status="no_mapping"))
                continue

            event_id = int(mapping.provider_event_id)
            working_id: int | None = None
            raw: Any = None
            last_err: str | None = None

            for pid in candidate_ids:
                try:
                    raw = self._client.get_event_odds(event_id, pid)
                    norm = extract_1x2_from_event_odds(raw)
                    if norm.get("market_found") or raw:
                        working_id = pid
                        break
                except SportApiError as exc:
                    last_err = str(exc)
                    continue

            if working_id is None:
                msg = last_err or f"Quote non trovate event_id={event_id}"
                errors.append(f"fixture {fx.id}: {msg}")
                rows.append(
                    self._row_skeleton(fx, team_cache, db, status="error", error=msg, sportapi_event_id=event_id),
                )
                continue

            norm = extract_1x2_from_event_odds(raw)
            snap = SportApiFixtureOddsSnapshot(
                fixture_id=int(fx.id),
                api_fixture_id=int(fx.api_fixture_id) if fx.api_fixture_id else None,
                sportapi_event_id=event_id,
                provider_slug=slug,
                provider_id_used=working_id,
                market_key=MARKET_1X2,
                market_name_original=norm.get("market_name_original"),
                home_odd=norm.get("home_odd"),
                draw_odd=norm.get("draw_odd"),
                away_odd=norm.get("away_odd"),
                normalized_payload=norm,
                raw_payload=raw if isinstance(raw, dict) else {"data": raw},
                fetched_at=datetime.now(timezone.utc),
            )
            db.add(snap)
            db.commit()

            if provider_row.working_odds_provider_id != working_id:
                provider_row.working_odds_provider_id = working_id
                db.commit()

            processed += 1
            rows.append(
                self._row_skeleton(
                    fx,
                    team_cache,
                    db,
                    status="ok" if norm.get("market_found") else "no_1x2",
                    sportapi_event_id=event_id,
                    provider_id_used=working_id,
                    home_odd=norm.get("home_odd"),
                    draw_odd=norm.get("draw_odd"),
                    away_odd=norm.get("away_odd"),
                    market_found=bool(norm.get("market_found")),
                    available_markets=norm.get("available_markets") or [],
                ),
            )

        return {
            "status": "success",
            "provider_slug": slug,
            "working_provider_id": provider_row.working_odds_provider_id,
            "candidate_provider_ids": candidate_ids,
            "total_fixtures": len(fixtures),
            "processed": processed,
            "skipped_no_mapping": skipped_no_mapping,
            "errors": errors,
            "rows": rows,
        }

    def _row_skeleton(
        self,
        fx: Fixture,
        team_cache: dict[int, Team],
        db: Session,
        *,
        status: str,
        sportapi_event_id: int | None = None,
        provider_id_used: int | None = None,
        home_odd: float | None = None,
        draw_odd: float | None = None,
        away_odd: float | None = None,
        market_found: bool | None = None,
        available_markets: list[str] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        home = self._team_name(db, fx.home_team_id, team_cache)
        away = self._team_name(db, fx.away_team_id, team_cache)
        return {
            "fixture_id": int(fx.id),
            "api_fixture_id": int(fx.api_fixture_id) if fx.api_fixture_id else None,
            "kickoff_at": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
            "match_label": f"{home} vs {away}",
            "sportapi_event_id": sportapi_event_id,
            "provider_id_used": provider_id_used,
            "status": status,
            "market_found": market_found,
            "home_odd": home_odd,
            "draw_odd": draw_odd,
            "away_odd": away_odd,
            "available_markets": available_markets or [],
            "error": error,
        }

    @staticmethod
    def _team_name(db: Session, team_id: int | None, cache: dict[int, Team]) -> str:
        if team_id is None:
            return "?"
        tid = int(team_id)
        if tid not in cache:
            t = db.get(Team, tid)
            cache[tid] = t  # type: ignore[assignment]
        t = cache.get(tid)
        return (t.name if t else None) or f"Team {tid}"
