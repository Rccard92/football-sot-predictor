"""Sync quote API-Football per Cecchino (whitelist Bet365/Betfair/Pinnacle)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Fixture
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.bookmakers.fixture_bookmaker_odds_repository import upsert_selection_odds
from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2
from app.services.competition_service import CompetitionService
from app.services.next_round_selection import select_next_round_fixtures

logger = logging.getLogger(__name__)

SLEEP_BETWEEN_CALLS_S = 0.35


class CecchinoBookmakerSyncService:
    def __init__(
        self,
        comp_svc: CompetitionService | None = None,
        client: ApiFootballClient | None = None,
    ) -> None:
        self._comp_svc = comp_svc or CompetitionService()
        self._client = client or ApiFootballClient()

    def sync(
        self,
        db: Session,
        competition_id: int,
        *,
        fixture_id: int | None = None,
        bookmaker_ids: list[int] | None = None,
        markets: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        comp = self._comp_svc.get_by_id_or_raise(db, competition_id)
        settings = get_settings()
        if not settings.api_football_key.strip():
            return {
                "status": "error",
                "competition_id": int(comp.id),
                "message": "API_FOOTBALL_KEY non configurata",
                "fixtures_checked": 0,
                "odds_saved": 0,
                "bookmakers_requested": [],
                "markets_found": [],
                "missing_markets": [],
                "failed": [],
                "warnings": [],
            }

        wanted_markets = markets or [MARKET_1X2, "DOUBLE_CHANCE", "OVER_UNDER_GOALS"]
        bm_defs = CECCHINO_BOOKMAKERS
        if bookmaker_ids:
            ids_set = {int(x) for x in bookmaker_ids}
            bm_defs = [b for b in CECCHINO_BOOKMAKERS if int(b["provider_bookmaker_id"]) in ids_set]

        if fixture_id is not None:
            fx = db.get(Fixture, int(fixture_id))
            if fx is None or int(fx.competition_id) != int(comp.id):
                return {
                    "status": "error",
                    "message": f"Fixture {fixture_id} non trovata per competition {comp.id}",
                    "fixtures_checked": 0,
                    "odds_saved": 0,
                    "bookmakers_requested": [b["name"] for b in bm_defs],
                    "markets_found": [],
                    "missing_markets": wanted_markets,
                    "failed": [],
                    "warnings": [],
                }
            fixtures = [fx]
        else:
            all_fixtures = list(
                db.scalars(
                    select(Fixture)
                    .where(Fixture.competition_id == comp.id)
                    .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
                ).all(),
            )
            sel = select_next_round_fixtures(all_fixtures, limit=limit, only_next_round=True)
            fixtures = sel.fixtures

        odds_saved = 0
        markets_found: set[str] = set()
        missing_all: set[str] = set()
        failed: list[str] = []
        warnings: list[str] = []

        for idx, fx in enumerate(fixtures):
            if not fx.api_fixture_id:
                failed.append(f"fixture {fx.id}: api_fixture_id assente")
                continue
            api_fid = int(fx.api_fixture_id)

            for bidx, bm in enumerate(bm_defs):
                if idx > 0 or bidx > 0:
                    time.sleep(SLEEP_BETWEEN_CALLS_S)
                bid = int(bm["provider_bookmaker_id"])
                try:
                    raw = self._client.get_fixture_odds(api_fid, bid)
                except ApiFootballError as exc:
                    failed.append(f"fixture {fx.id} bookmaker {bm['name']}: {exc}")
                    continue

                parsed_rows, missing = parse_api_football_odds_response(
                    raw,
                    requested_markets=wanted_markets,
                )
                missing_all.update(missing)
                if not parsed_rows:
                    warnings.append(f"fixture {fx.id} {bm['name']}: nessuna quota")
                    continue

                for pr in parsed_rows:
                    upsert_selection_odds(
                        db,
                        competition_id=int(comp.id),
                        fixture_id=int(fx.id),
                        provider_source=PROVIDER_API_FOOTBALL,
                        provider_bookmaker_id=str(bid),
                        bookmaker_name=bm["name"],
                        normalized_market=pr["normalized_market"],
                        selection_key=pr["selection_key"],
                        selection_label=pr.get("selection_label"),
                        odds_value=pr["odds_value"],
                        market_label=pr.get("market_label"),
                        provider_fixture_id=api_fid,
                        provider_market_id=pr.get("provider_market_id"),
                        raw_payload_json=pr.get("raw_payload_json"),
                        odds_updated_at=datetime.now(timezone.utc),
                    )
                    odds_saved += 1
                    markets_found.add(pr["normalized_market"])

        db.commit()

        return {
            "status": "success",
            "competition_id": int(comp.id),
            "fixtures_checked": len(fixtures),
            "bookmakers_requested": [b["name"] for b in bm_defs],
            "odds_saved": odds_saved,
            "markets_found": sorted(markets_found),
            "missing_markets": sorted(missing_all),
            "failed": failed,
            "warnings": warnings,
        }
