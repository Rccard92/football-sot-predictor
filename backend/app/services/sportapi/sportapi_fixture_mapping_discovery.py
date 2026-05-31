"""Discovery candidate SportAPI per mapping fixture (Step K.3)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import sportapi_configured
from app.models import Competition, Fixture, Team
from app.services.sportapi.sportapi_client import SportApiClient, SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_fixture_mapping_scoring import (
    ScoredMappingCandidate,
    extract_round_from_fixture,
    pick_best_candidate,
    score_mapping_candidate,
)
from app.services.sportapi.sportapi_payload import (
    event_id,
    extract_events_list,
    is_football_event,
)

logger = logging.getLogger(__name__)


class SportApiFixtureMappingDiscovery:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()
        self._events_cache: dict[str, list[dict[str, Any]]] = {}

    def fetch_scheduled_events_for_date(self, match_date: str) -> tuple[list[dict[str, Any]], int]:
        """Carica eventi football per data (cache in-memory per batch stagione)."""
        if match_date in self._events_cache:
            return self._events_cache[match_date], 0

        if not sportapi_configured():
            return [], 0

        try:
            raw = self._client.get_scheduled_events(match_date)
        except (SportApiDisabledError, SportApiError) as exc:
            logger.warning("sportapi scheduled-events failed date=%s: %s", match_date, exc)
            self._events_cache[match_date] = []
            return [], 1

        events = [e for e in extract_events_list(raw) if is_football_event(e)]
        self._events_cache[match_date] = events
        return events, 1

    def clear_events_cache(self) -> None:
        self._events_cache.clear()

    def discover_for_fixture(
        self,
        db: Session,
        *,
        fixture: Fixture,
        competition: Competition,
        cached_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        home = db.get(Team, int(fixture.home_team_id))
        away = db.get(Team, int(fixture.away_team_id))
        home_name = home.name if home else str(fixture.home_team_id)
        away_name = away.name if away else str(fixture.away_team_id)

        kickoff = fixture.kickoff_at
        if kickoff is None:
            return {
                "status": "error",
                "message": "Fixture senza kickoff_at",
                "candidates": [],
                "api_calls": 0,
            }
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        fixture_ts = int(kickoff.timestamp())
        match_date = kickoff.astimezone(timezone.utc).date().isoformat()
        round_num = extract_round_from_fixture(fixture.round)
        league_name = fixture.league.name if fixture.league else competition.name

        if not sportapi_configured():
            return {
                "status": "disabled",
                "message": "SportAPI non configurata",
                "candidates": [],
                "api_calls": 0,
            }

        api_calls = 0
        if cached_events is not None:
            events = cached_events
        else:
            events, api_calls = self.fetch_scheduled_events_for_date(match_date)

        scored: list[ScoredMappingCandidate] = []
        for ev in events:
            eid = event_id(ev)
            if eid is None:
                continue
            row = score_mapping_candidate(
                fixture_ts=fixture_ts,
                match_date=kickoff.astimezone(timezone.utc).date(),
                home_name=home_name,
                away_name=away_name,
                round_num=round_num,
                ev=ev,
            )
            if row.score > 0:
                scored.append(row)

        scored.sort(key=lambda c: c.score, reverse=True)
        best, ambiguous, amb_warnings = pick_best_candidate(scored)

        return {
            "status": "ok",
            "match_date": match_date,
            "home_name": home_name,
            "away_name": away_name,
            "league_name": league_name,
            "round_num": round_num,
            "candidates": scored,
            "best": best,
            "ambiguous_high": ambiguous,
            "warnings": amb_warnings,
            "scheduled_events_count": len(events),
            "api_calls": api_calls if cached_events is None else 0,
        }
