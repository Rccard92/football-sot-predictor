"""Matching fixture API-Football -> evento SportAPI (admin + batch competition)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings, sportapi_configured
from app.services.sportapi.sportapi_client import SportApiClient, SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_fixture_resolve import FIXTURE_NOT_FOUND_MSG, resolve_fixture_or_error
from app.services.sportapi.sportapi_normalize import (
    extract_round_number,
    normalize_team_name,
    team_names_match_fuzzy,
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


def _country_tokens(country: str | None) -> set[str]:
    if not country:
        return set()
    c = str(country).strip().lower()
    tokens = {c}
    if c in ("italy", "it", "ita", "italia"):
        tokens.update({"italy", "it", "ita", "italia"})
    if c in ("brazil", "br", "bra", "brasil"):
        tokens.update({"brazil", "br", "bra", "brasil"})
    return tokens


def _competition_name_tokens(competition_name: str | None, league_name: str | None) -> set[str]:
    parts: list[str] = []
    for raw in (competition_name, league_name):
        if raw and str(raw).strip():
            parts.append(normalize_team_name(str(raw)))
    tokens: set[str] = set()
    for p in parts:
        tokens.add(p)
        for chunk in p.split():
            if len(chunk) >= 3:
                tokens.add(chunk)
    return tokens


def _score_competition_bonus(
    *,
    competition_name: str | None,
    competition_country: str | None,
    league_name: str,
    ev: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    info = event_tournament_info(ev)
    tname = normalize_team_name(str(info.get("tournament_name") or ""))
    country = str(info.get("country") or "").lower()
    comp_tokens = _competition_name_tokens(competition_name, league_name)
    country_tokens = _country_tokens(competition_country)

    matched = False
    reasons: list[str] = []

    if country_tokens and country in country_tokens:
        matched = True
        reasons.append(f"country={country}")

    for token in comp_tokens:
        if not token:
            continue
        if token in tname or tname in token:
            matched = True
            reasons.append(f"tournament~{token}")
            break
        if "serie a" in token and "serie a" in tname:
            matched = True
            reasons.append("serie_a")
            break
        if "brasileir" in token and "brasileir" in tname:
            matched = True
            reasons.append("brasileirao")
            break

    if matched:
        return 10.0, {"competition": 10, "match_reason": "; ".join(reasons) or "competition_metadata"}
    return 0.0, {"competition": 0}


def _format_match_reason(breakdown: dict[str, Any]) -> str:
    parts: list[str] = []
    if breakdown.get("timestamp_exact"):
        parts.append("timestamp_exact")
    elif breakdown.get("timestamp_within_15m"):
        parts.append("timestamp_within_15m")
    if breakdown.get("home_team"):
        parts.append("home_team")
    if breakdown.get("away_team"):
        parts.append("away_team")
    if breakdown.get("competition"):
        parts.append(str(breakdown.get("match_reason") or "competition"))
    if breakdown.get("round"):
        parts.append("round")
    return ", ".join(parts) if parts else "low_score"


def _score_candidate(
    *,
    fixture_ts: int,
    home_name: str,
    away_name: str,
    league_name: str,
    round_num: int | None,
    ev: dict[str, Any],
    competition_name: str | None = None,
    competition_country: str | None = None,
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
    if team_names_match_fuzzy(home_name, ev_home):
        breakdown["home_team"] = 25
        total += 25
    else:
        breakdown["home_team"] = 0
    if team_names_match_fuzzy(away_name, ev_away):
        breakdown["away_team"] = 25
        total += 25
    else:
        breakdown["away_team"] = 0

    comp_bonus, comp_breakdown = _score_competition_bonus(
        competition_name=competition_name,
        competition_country=competition_country,
        league_name=league_name,
        ev=ev,
    )
    breakdown.update(comp_breakdown)
    total += comp_bonus

    info = event_tournament_info(ev)
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

    breakdown["match_reason"] = _format_match_reason(breakdown)
    return round(total, 2), breakdown


class SportApiMatchingService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def debug_match_fixture(
        self,
        db: Session,
        fixture_id: int,
        *,
        competition_name: str | None = None,
        competition_country: str | None = None,
    ) -> dict[str, Any]:
        return self._match_fixture_internal(
            db,
            int(fixture_id),
            competition_name=competition_name,
            competition_country=competition_country,
        )

    def match_fixture_for_competition(
        self,
        db: Session,
        fixture_id: int,
        comp: Any,
    ) -> dict[str, Any]:
        return self._match_fixture_internal(
            db,
            int(fixture_id),
            competition_name=getattr(comp, "name", None),
            competition_country=getattr(comp, "country", None),
            expected_competition_id=int(comp.id),
        )

    def _match_fixture_internal(
        self,
        db: Session,
        fixture_id: int,
        *,
        competition_name: str | None = None,
        competition_country: str | None = None,
        expected_competition_id: int | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        fx, resolve_meta = resolve_fixture_or_error(db, int(fixture_id))
        if fx is None:
            err = resolve_meta or {}
            err.setdefault("message", FIXTURE_NOT_FOUND_MSG)
            err["input_id"] = int(fixture_id)
            return err

        if expected_competition_id is not None and int(getattr(fx, "competition_id", 0) or 0) != int(
            expected_competition_id
        ):
            return {
                "status": "error",
                "message": f"Fixture {fixture_id} non appartiene a competition_id={expected_competition_id}",
                "input_id": int(fixture_id),
                "fixture_competition_id": getattr(fx, "competition_id", None),
            }

        resolved_via = resolve_meta.get("resolved_via") if resolve_meta else None

        league = fx.league
        kickoff = fx.kickoff_at
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        fixture_ts = int(kickoff.timestamp())
        match_date = kickoff.astimezone(timezone.utc).date().isoformat()

        league_name = league.name if league else None
        if competition_name and not league_name:
            league_name = competition_name

        fixture_payload = {
            "fixture_id": int(fx.id),
            "api_fixture_id": int(fx.api_fixture_id),
            "competition_id": int(fx.competition_id) if fx.competition_id is not None else None,
            "league_id": int(fx.league_id),
            "league_api_id": int(league.api_league_id) if league else None,
            "league_name": league_name,
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
            "raw_candidates": [],
            "best_candidate": None,
            "best_match": None,
            "confidence_score": None,
            "matched_by": None,
            "recommendation": "NO_MATCH",
            "score_explanation": "Nessun candidato SportAPI.",
            "match_reason": None,
            "would_save": False,
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
                league_name=league_name or "",
                round_num=round_num,
                ev=ev,
                competition_name=competition_name,
                competition_country=competition_country,
            )
            ev_home, ev_away = event_home_away_names(ev)
            hi, ai = event_team_ids(ev)
            info = event_tournament_info(ev)
            rec = _recommendation(score)
            candidates.append(
                {
                    "provider_event_id": eid,
                    "sportapi_event_id": eid,
                    "start_timestamp": event_start_timestamp(ev),
                    "home_team_name": ev_home,
                    "away_team_name": ev_away,
                    "tournament": info,
                    "confidence_score": score,
                    "score_breakdown": breakdown,
                    "recommendation": rec,
                    "match_reason": breakdown.get("match_reason"),
                    "raw_event": ev,
                },
            )

        candidates.sort(key=lambda c: float(c.get("confidence_score") or 0), reverse=True)
        base["candidates"] = candidates[:5]
        base["raw_candidates"] = candidates[:5]
        base["scheduled_events_count"] = len(events)
        base["api_calls"] = 1

        if candidates:
            best = candidates[0]
            base["best_candidate"] = best
            base["best_match"] = f"{best.get('home_team_name')} – {best.get('away_team_name')}"
            base["sportapi_event_id"] = best["provider_event_id"]
            base["confidence_score"] = best["confidence_score"]
            base["recommendation"] = best["recommendation"]
            base["match_reason"] = best.get("match_reason")
            base["would_save"] = best["recommendation"] == "AUTO_SAFE"
            base["score_explanation"] = (
                f"Miglior candidato event_id={best['provider_event_id']} "
                f"score={best['confidence_score']} reason={best.get('match_reason')}"
            )
            if best["recommendation"] == "AUTO_SAFE":
                base["matched_by"] = "auto_timestamp_teams"
            elif best["recommendation"] == "REVIEW":
                base["matched_by"] = "manual_review_recommended"

        return base
