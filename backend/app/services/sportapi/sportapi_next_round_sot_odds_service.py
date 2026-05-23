"""Test recupero Over/Under SOT prossimo turno via mapping salvati."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Fixture, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.models.sportapi_odds_market_mapping import MARKET_KEY_MATCH_TOTAL_SOT
from app.models.sportapi_odds_provider import DEFAULT_PROVIDER_SLUG, SportApiOddsProvider
from app.services.sportapi.sportapi_client import SportApiClient, SportApiError
from app.services.sportapi.sportapi_event_odds_test_service import candidate_provider_ids
from app.services.sportapi.sportapi_odds_market_mapping_service import SportApiOddsMarketMappingService
from app.services.sportapi.sportapi_odds_markets_normalize import normalize_all_markets_from_event_odds
from app.services.sportapi.sportapi_odds_sot_candidates import _norm_name, _over_under_from_outcomes
from app.services.tracked_pick_round_backfill_service import TrackedPickRoundBackfillService

logger = logging.getLogger(__name__)

SLEEP_BETWEEN_FIXTURES_S = 0.3


class SportApiNextRoundSotOddsService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()
        self._round_svc = TrackedPickRoundBackfillService()

    def run(
        self,
        db: Session,
        *,
        provider_slug: str = DEFAULT_PROVIDER_SLUG,
        season_year: int | None = None,
        market_key: str = MARKET_KEY_MATCH_TOTAL_SOT,
        limit: int = 50,
    ) -> dict[str, Any]:
        slug = provider_slug.strip().lower()
        year = int(season_year or get_settings().default_season)
        mappings = SportApiOddsMarketMappingService().list_active(db, slug)
        key_mappings = [m for m in mappings if m.normalized_market_key == market_key]
        if not key_mappings:
            return {
                "status": "success",
                "message": "Nessun mapping SOT configurato. Usa Discovery mercati per individuare il mercato corretto.",
                "provider_slug": slug,
                "mappings_count": 0,
                "rows": [],
            }

        name_to_mapping = {m.raw_market_name: m for m in key_mappings}
        provider_row = db.scalar(
            select(SportApiOddsProvider).where(SportApiOddsProvider.provider_slug == slug),
        )
        candidate_ids = candidate_provider_ids(provider_row)

        fixtures = self._round_svc.current_round_fixtures(db, year, limit=limit)
        rows: list[dict[str, Any]] = []
        errors: list[str] = []

        for idx, fx in enumerate(fixtures):
            if idx > 0:
                time.sleep(SLEEP_BETWEEN_FIXTURES_S)
            home_t = db.get(Team, int(fx.home_team_id))
            away_t = db.get(Team, int(fx.away_team_id))
            match_label = f"{home_t.name if home_t else '?'} – {away_t.name if away_t else '?'}"

            mapping_fx = db.scalar(
                select(FixtureProviderMapping).where(
                    FixtureProviderMapping.fixture_id == int(fx.id),
                    FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                ),
            )
            if not mapping_fx or not mapping_fx.provider_event_id:
                rows.append(
                    self._row(fx, match_label, status="no_mapping"),
                )
                continue

            event_id = int(mapping_fx.provider_event_id)
            raw = None
            working_id = None
            for pid in candidate_ids:
                try:
                    raw = self._client.get_event_odds(event_id, pid)
                    working_id = pid
                    break
                except SportApiError:
                    continue

            if raw is None:
                rows.append(self._row(fx, match_label, status="api_error", sportapi_event_id=event_id))
                errors.append(f"fixture {fx.id}: quote non trovate")
                continue

            markets = normalize_all_markets_from_event_odds(raw)
            matched = None
            for m in markets:
                mname = str(m.get("market_name") or "")
                if mname in name_to_mapping:
                    matched = m
                    break
                for map_row in key_mappings:
                    if _norm_name(mname) == _norm_name(map_row.raw_market_name):
                        matched = m
                        break
                if matched:
                    break

            if matched is None:
                rows.append(
                    self._row(
                        fx,
                        match_label,
                        status="market_not_found",
                        sportapi_event_id=event_id,
                        provider_id_used=working_id,
                    ),
                )
                continue

            over_o, under_o, line_v = _over_under_from_outcomes(matched.get("outcomes") or [])
            if line_v is None:
                line_v = matched.get("line")
            rows.append(
                self._row(
                    fx,
                    match_label,
                    status="ok" if over_o is not None or under_o is not None else "no_over_under",
                    sportapi_event_id=event_id,
                    provider_id_used=working_id,
                    market_name=matched.get("market_name"),
                    line=line_v,
                    over_odd=over_o,
                    under_odd=under_o,
                ),
            )

        return {
            "status": "success",
            "provider_slug": slug,
            "market_key": market_key,
            "mappings_count": len(key_mappings),
            "total_fixtures": len(fixtures),
            "rows": rows,
            "errors": errors,
        }

    @staticmethod
    def _row(
        fx: Fixture,
        match_label: str,
        *,
        status: str,
        sportapi_event_id: int | None = None,
        provider_id_used: int | None = None,
        market_name: str | None = None,
        line: float | None = None,
        over_odd: float | None = None,
        under_odd: float | None = None,
    ) -> dict[str, Any]:
        return {
            "fixture_id": int(fx.id),
            "kickoff_at": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
            "match_label": match_label,
            "sportapi_event_id": sportapi_event_id,
            "provider_id_used": provider_id_used,
            "market_name": market_name,
            "line": line,
            "over_odd": over_odd,
            "under_odd": under_odd,
            "status": status,
        }
