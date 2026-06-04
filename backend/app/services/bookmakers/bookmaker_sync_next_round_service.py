"""Sync quote 1X2 prossimo turno → fixture_bookmaker_odds (competition-scoped)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings, sportapi_configured
from app.models import Fixture
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.models.sportapi_fixture_odds_snapshot import MARKET_1X2, SportApiFixtureOddsSnapshot
from app.models.sportapi_odds_provider import DEFAULT_PROVIDER_SLUG, SportApiOddsProvider
from app.services.bookmakers.bookmaker_constants import (
    MARKET_MATCH_WINNER_1X2,
    PROVIDER_SOURCE_API_FOOTBALL,
    PROVIDER_SOURCE_SPORTAPI,
)
from app.services.bookmakers.fixture_bookmaker_odds_repository import upsert_fixture_odds
from app.services.competition_service import CompetitionService
from app.services.next_round_selection import select_next_round_fixtures
from app.services.sportapi.sportapi_client import SportApiClient, SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_event_odds_test_service import candidate_provider_ids
from app.services.sportapi.sportapi_odds_1x2_normalize import extract_1x2_from_event_odds

logger = logging.getLogger(__name__)

SLEEP_BETWEEN_FIXTURES_S = 0.3


class BookmakerSyncNextRoundService:
    def __init__(
        self,
        comp_svc: CompetitionService | None = None,
        client: SportApiClient | None = None,
    ) -> None:
        self._comp_svc = comp_svc or CompetitionService()
        self._client = client or SportApiClient()

    def sync(
        self,
        db: Session,
        competition_id: int,
        *,
        market: str = MARKET_MATCH_WINNER_1X2,
        provider_source: str = "auto",
        bookmaker_name: str | None = None,
        provider_slug: str = DEFAULT_PROVIDER_SLUG,
        limit: int = 50,
    ) -> dict[str, Any]:
        comp = self._comp_svc.get_by_id_or_raise(db, competition_id)
        all_fixtures = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == comp.id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all(),
        )
        selection = select_next_round_fixtures(all_fixtures, limit=limit, only_next_round=True)
        fixtures = selection.fixtures

        warnings: list[str] = []
        failed: list[str] = []
        fixtures_checked = len(fixtures)
        odds_saved = 0
        bookmakers_found: set[str] = set()
        markets_found: set[str] = set()

        src = (provider_source or "auto").strip().lower()
        use_sportapi = src in ("auto", "sportapi", PROVIDER_SOURCE_SPORTAPI)
        use_api_football = src in ("auto", "api_football", PROVIDER_SOURCE_API_FOOTBALL)

        if use_api_football and not get_settings().api_football_key.strip():
            warnings.append("API-Football: API_FOOTBALL_KEY non configurata.")
            use_api_football = False
        if use_api_football:
            warnings.append(
                "API-Football: quote fixture 1X2 non disponibili nel client; "
                "usa SportAPI per sync 1X2.",
            )
            use_api_football = False

        if use_sportapi and not sportapi_configured():
            warnings.append("SportAPI: non configurata (SPORTAPI_ENABLED + key).")
            use_sportapi = False

        if not use_sportapi and not use_api_football:
            return {
                "status": "error",
                "competition_id": int(comp.id),
                "round_label": selection.final_round,
                "market": market,
                "provider_source": provider_source,
                "fixtures_checked": fixtures_checked,
                "odds_saved": 0,
                "bookmakers_found": [],
                "markets_found": [],
                "failed": failed,
                "warnings": warnings,
                "message": "Nessun provider configurato per sync quote.",
            }

        if market != MARKET_MATCH_WINNER_1X2:
            warnings.append(f"Sync implementato solo per {MARKET_MATCH_WINNER_1X2}; richiesto {market}.")

        slug = (bookmaker_name or provider_slug).strip().lower()
        provider_row = db.scalar(
            select(SportApiOddsProvider).where(SportApiOddsProvider.provider_slug == slug),
        )
        if provider_row is None and bookmaker_name:
            provider_row = db.scalar(
                select(SportApiOddsProvider).where(
                    SportApiOddsProvider.provider_name.ilike(bookmaker_name),
                ),
            )
        if provider_row is None:
            provider_row = db.scalar(
                select(SportApiOddsProvider).where(
                    SportApiOddsProvider.provider_slug == DEFAULT_PROVIDER_SLUG,
                ),
            )
        if provider_row is None:
            return {
                "status": "error",
                "message": "Nessun provider SportAPI in DB. Esegui sync providers.",
                "fixtures_checked": fixtures_checked,
                "odds_saved": 0,
                "bookmakers_found": [],
                "markets_found": [],
                "failed": failed,
                "warnings": warnings,
            }

        candidate_ids = candidate_provider_ids(provider_row)
        if not candidate_ids:
            return {
                "status": "error",
                "message": f"Provider {provider_row.provider_slug} senza id candidati.",
                "fixtures_checked": fixtures_checked,
                "odds_saved": 0,
                "bookmakers_found": [],
                "markets_found": [],
                "failed": failed,
                "warnings": warnings,
            }

        bm_name = provider_row.provider_name
        bm_id = str(provider_row.provider_id or provider_row.working_odds_provider_id or provider_row.provider_slug)

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
                failed.append(f"fixture {fx.id}: mapping SportAPI assente")
                continue

            event_id = int(mapping.provider_event_id)
            working_id: int | None = None
            raw: Any = None
            last_err: str | None = None

            for pid in candidate_ids:
                try:
                    raw = self._client.get_event_odds(event_id, pid)
                    norm_probe = extract_1x2_from_event_odds(raw)
                    if norm_probe.get("market_matched") or raw:
                        working_id = pid
                        break
                except SportApiError as exc:
                    last_err = str(exc)
                    continue
                except SportApiDisabledError as exc:
                    failed.append(str(exc))
                    break

            if working_id is None:
                msg = last_err or f"Quote non trovate event_id={event_id}"
                failed.append(f"fixture {fx.id}: {msg}")
                continue

            norm = extract_1x2_from_event_odds(raw)
            if not norm.get("market_matched"):
                failed.append(f"fixture {fx.id}: mercato 1X2 non trovato")
                continue

            markets_found.add(MARKET_MATCH_WINNER_1X2)
            bookmakers_found.add(bm_name)

            upsert_fixture_odds(
                db,
                competition_id=int(comp.id),
                fixture_id=int(fx.id),
                provider_source=PROVIDER_SOURCE_SPORTAPI,
                provider_bookmaker_id=bm_id,
                bookmaker_name=bm_name,
                normalized_market=MARKET_MATCH_WINNER_1X2,
                home_odds=norm.get("home_odd"),
                draw_odds=norm.get("draw_odd"),
                away_odds=norm.get("away_odd"),
                provider_market_id=norm.get("market_name_original"),
                raw_payload_json=norm if isinstance(norm, dict) else None,
                odds_updated_at=datetime.now(timezone.utc),
            )

            snap = SportApiFixtureOddsSnapshot(
                fixture_id=int(fx.id),
                api_fixture_id=int(fx.api_fixture_id) if fx.api_fixture_id else None,
                sportapi_event_id=event_id,
                provider_slug=provider_row.provider_slug,
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
            odds_saved += 1

            if provider_row.working_odds_provider_id != working_id:
                provider_row.working_odds_provider_id = working_id

        db.commit()

        return {
            "status": "success",
            "competition_id": int(comp.id),
            "round_label": selection.final_round,
            "market": market,
            "provider_source": PROVIDER_SOURCE_SPORTAPI if use_sportapi else provider_source,
            "provider_slug": provider_row.provider_slug,
            "fixtures_checked": fixtures_checked,
            "odds_saved": odds_saved,
            "bookmakers_found": sorted(bookmakers_found),
            "markets_found": sorted(markets_found),
            "failed": failed,
            "warnings": warnings + list(selection.warnings),
        }
