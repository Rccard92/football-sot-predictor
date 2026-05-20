"""Matching fixture API-Football -> evento SportAPI (solo debug admin)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings, sportapi_configured
from app.services.sportapi.sportapi_client import SportApiClient, SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_fixture_resolve import FIXTURE_NOT_FOUND_MSG, resolve_fixture_or_error
from app.services.sportapi.sportapi_normalize import (
    extract_round_number,
    normalize_team_name,
    team_names_match,
)
from app.services.sportapi.sportapi_payload import (
    event_home_away_names,
    event_id,
    event_start_timestamp,
    event_team_ids,
    event_tournament_info,
    extract_events_list,
    is_football_event,
)

logger = logging.getLogger(__name__)

PROVIDER_SPORTAPI = "sportapi"
MAX_TIME_DELTA_S = 900


def _recommendation(score: float) -> str:
    if score >= 90:
        return "AUTO_SAFE"
    if score >= 75:
        return "REVIEW"
    return "NO_MATCH"


def _score_candidate(
    *,
    fixture_ts: int,
    home_name: str,
    away_name: str,
    league_name: str,
    round_num: int | None,
    ev: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    breakdown: dict[str, Any] = {}
    total = 0.0

    ev_ts = event_start_timestamp(ev)
    if ev_ts is not None and ev_ts == fixture_ts:
        breakdown["timestamp_exact"] = 40
        total += 40
    elif ev_ts is not None and abs(ev_ts - fixture_ts) <= MAX_TIME_DELTA_S:
        breakdown["timestamp_within_15m"] = 30
        total += 30
    else:
        breakdown["timestamp"] = 0

    ev_home, ev_away = event_home_away_names(ev)
    if team_names_match(home_name, ev_home):
        breakdown["home_team"] = 25
        total += 25
    else:
        breakdown["home_team"] = 0
    if team_names_match(away_name, ev_away):
        breakdown["away_team"] = 25
        total += 25
    else:
        breakdown["away_team"] = 0

    info = event_tournament_info(ev)
    tname = str(info.get("tournament_name") or "").lower()
    country = str(info.get("country") or "").lower()
    league_norm = normalize_team_name(league_name)
    if "serie a" in tname or "serie a" in league_norm or country in ("italy", "it", "ita"):
        breakdown["competition"] = 10
        total += 10
    else:
        breakdown["competition"] = 0

    ev_round = info.get("round")
    try:
        ev_round_n = int(ev_round) if ev_round is not None else None
    except (TypeError, ValueError):
        ev_round_n = None
    if round_num is not None and ev_round_n is not None and round_num == ev_round_n:
        breakdown["round"] = 5
        total += 5
    else:
        breakdown["round"] = 0

    return round(total, 2), breakdown


class SportApiMatchingService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def debug_match_fixture(self, db: Session, fixture_id: int) -> dict[str, Any]:
        settings = get_settings()
        fx, resolve_meta = resolve_fixture_or_error(db, int(fixture_id))
        if fx is None:
            err = resolve_meta or {}
            err.setdefault("message", FIXTURE_NOT_FOUND_MSG)
            err["input_id"] = int(fixture_id)
            return err

        resolved_via = resolve_meta.get("resolved_via") if resolve_meta else None

        league = fx.league
        kickoff = fx.kickoff_at
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        fixture_ts = int(kickoff.timestamp())
        match_date = kickoff.astimezone(timezone.utc).date().isoformat()

        fixture_payload = {
            "fixture_id": int(fx.id),
            "api_fixture_id": int(fx.api_fixture_id),
            "league_id": int(fx.league_id),
            "league_api_id": int(league.api_league_id) if league else None,
            "league_name": league.name if league else None,
            "season_id": int(fx.season_id),
            "round": fx.round,
            "timezone": fx.timezone,
            "home_team_id": int(fx.home_team_id),
            "home_team_name": fx.home_team.name if fx.home_team else None,
            "away_team_id": int(fx.away_team_id),
            "away_team_name": fx.away_team.name if fx.away_team else None,
            "kickoff_at": kickoff.isoformat(),
            "kickoff_timestamp": fixture_ts,
            "match_date": match_date,
            "resolved_via": resolved_via,
        }

        base = {
            "status": "ok",
            "sportapi_enabled": sportapi_configured(),
            "use_sportapi_lineups_in_model": settings.use_sportapi_lineups_in_model,
            "input_id": int(fixture_id),
            "resolved_via": resolved_via,
            "fixture": fixture_payload,
            "candidates": [],
            "best_candidate": None,
            "confidence_score": None,
            "matched_by": None,
            "recommendation": "NO_MATCH",
            "score_explanation": "Nessun candidato SportAPI.",
        }

        if not sportapi_configured():
            base["status"] = "disabled"
            base["message"] = "SportAPI disabilitata o chiave assente"
            return base

        try:
            raw = self._client.get_scheduled_events(match_date)
        except SportApiDisabledError as exc:
            base["status"] = "disabled"
            base["message"] = str(exc)
            return base
        except SportApiError as exc:
            logger.warning("sportapi scheduled events failed: %s", exc)
            base["status"] = "error"
            base["message"] = str(exc)
            return base

        events = [e for e in extract_events_list(raw) if is_football_event(e)]
        home_name = fixture_payload["home_team_name"] or ""
        away_name = fixture_payload["away_team_name"] or ""
        league_name = fixture_payload["league_name"] or ""
        round_num = extract_round_number(fx.round)

        candidates: list[dict[str, Any]] = []
        for ev in events:
            eid = event_id(ev)
            if eid is None:
                continue
            score, breakdown = _score_candidate(
                fixture_ts=fixture_ts,
                home_name=home_name,
                away_name=away_name,
                league_name=league_name,
                round_num=round_num,
                ev=ev,
            )
            ev_home, ev_away = event_home_away_names(ev)
            hi, ai = event_team_ids(ev)
            info = event_tournament_info(ev)
            candidates.append(
                {
                    "provider_event_id": eid,
                    "start_timestamp": event_start_timestamp(ev),
                    "home_team_name": ev_home,
                    "away_team_name": ev_away,
                    "tournament": info,
                    "confidence_score": score,
                    "score_breakdown": breakdown,
                    "recommendation": _recommendation(score),
                },
            )

        candidates.sort(key=lambda c: float(c.get("confidence_score") or 0), reverse=True)
        base["candidates"] = candidates
        base["scheduled_events_count"] = len(events)
        base["api_calls"] = 1

        if candidates:
            best = candidates[0]
            base["best_candidate"] = best
            base["confidence_score"] = best["confidence_score"]
            base["recommendation"] = best["recommendation"]
            base["score_explanation"] = (
                f"Miglior candidato event_id={best['provider_event_id']} "
                f"score={best['confidence_score']} breakdown={best['score_breakdown']}"
            )
            if best["recommendation"] == "AUTO_SAFE":
                base["matched_by"] = "auto_timestamp_teams"
            elif best["recommendation"] == "REVIEW":
                base["matched_by"] = "manual_review_recommended"

        return base
