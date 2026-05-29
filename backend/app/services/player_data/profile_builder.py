"""Costruisce player_season_profiles da player_match_stats (solo DB, nessuna API)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, PlayerMatchStat, PlayerRegistry, PlayerSeasonProfile, Team
from app.services.ingestion_service import IngestionService
from app.services.player_data.profile_aggregation_helpers import (
    MINUTES_FOR_IMPACT,
    MatchRowView,
    PlayerSeasonAgg,
    build_recent_windows,
    build_team_fixture_order,
    compute_reliability_score,
    compute_shooting_impact_score,
    team_share,
    to_decimal,
    to_decimal_minutes,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _kickoff_past(fixture: Fixture, now: datetime) -> bool:
    ko = fixture.kickoff_at
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return ko < now


def build_serie_a_player_season_profiles(
    db: Session,
    season_year: int,
    *,
    competition_id: int | None = None,
    league_id_override: int | None = None,
) -> dict[str, Any]:
    logger.info(
        "player_season_profiles build start season=%s competition_id=%s",
        season_year,
        competition_id,
    )
    ing = IngestionService()
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    try:
        if league_id_override is not None:
            from app.models import Season

            season_row = db.scalar(
                select(Season).where(
                    Season.league_id == league_id_override,
                    Season.year == season_year,
                )
            )
            if season_row is None:
                raise ValueError(f"Stagione {season_year} non trovata per league_id={league_id_override}")
        else:
            season_row = ing._serie_a_season_row(db, season_year)
    except ValueError as exc:
        return {
            "status": "error",
            "season": season_year,
            "message": str(exc),
            "players_considered": 0,
            "profiles_created_or_updated": 0,
            "profiles_with_shooting_impact": 0,
            "profiles_without_enough_minutes": 0,
            "teams_processed": 0,
            "top_players_sample": [],
            "warnings": [],
            "errors": [{"message": str(exc)}],
            "profile_build_version": "v1",
            "source": "player_match_stats",
            "null_zero_policy": "minutes_gt_0_null_events_treated_as_zero",
            "minimum_minutes_for_impact": MINUTES_FOR_IMPACT,
        }

    year = int(season_row.year)
    league_id = int(season_row.league_id)
    now = _utc_now()

    rows_db = db.execute(
        select(PlayerMatchStat, Fixture)
        .join(Fixture, Fixture.id == PlayerMatchStat.fixture_id)
        .where(
            PlayerMatchStat.season == year,
            PlayerMatchStat.league_id == league_id,
            Fixture.status.in_(FINISHED_STATUSES),
            *(
                [PlayerMatchStat.competition_id == competition_id]
                if competition_id is not None
                else []
            ),
        ),
    ).all()

    views: list[MatchRowView] = []
    for stat, fx in rows_db:
        if not _kickoff_past(fx, now):
            continue
        views.append(
            MatchRowView(
                fixture_id=int(stat.fixture_id),
                api_team_id=int(stat.api_team_id),
                api_player_id=int(stat.api_player_id),
                player_id=stat.player_id,
                team_id=int(stat.team_id) if stat.team_id is not None else None,
                kickoff_at=fx.kickoff_at,
                minutes=stat.minutes,
                substitute=stat.substitute,
                rating=float(stat.rating) if stat.rating is not None else None,
                shots_total=stat.shots_total,
                shots_on=stat.shots_on,
                goals_total=stat.goals_total,
                goals_assists=stat.goals_assists,
                passes_key=stat.passes_key,
            ),
        )

    team_fixture_order = build_team_fixture_order(views)
    recent_windows = build_recent_windows(team_fixture_order)

    aggs: dict[tuple[int, int], PlayerSeasonAgg] = {}
    for v in views:
        key = (v.api_team_id, v.api_player_id)
        if key not in aggs:
            aggs[key] = PlayerSeasonAgg(
                api_team_id=v.api_team_id,
                api_player_id=v.api_player_id,
                player_id=v.player_id,
                team_id=v.team_id,
            )
        aggs[key].rows.append(v)
        if v.team_id is not None:
            aggs[key].team_id = v.team_id

    # Metriche base per giocatore
    player_metrics: dict[tuple[int, int], dict[str, Any]] = {}
    heuristic_teams: set[int] = set()

    for key, agg in aggs.items():
        played = agg.played_rows()
        if not played:
            continue
        recent_ids = recent_windows.get(agg.api_team_id, set())
        base = agg.aggregate_base(recent_ids)
        if base.get("starts_used_minutes_heuristic"):
            heuristic_teams.add(agg.api_team_id)
        player_metrics[key] = base

    if heuristic_teams:
        warnings.append(
            {
                "code": "starts_estimated_method",
                "message": "starts_estimated usato euristica minutes>=60 per alcune squadre",
                "starts_estimated_method": "minutes_gte_60",
                "api_team_ids": sorted(heuristic_teams),
            },
        )

    # Denominatori squadra (solo righe giocate)
    team_shots: dict[int, int] = defaultdict(int)
    team_sot: dict[int, int] = defaultdict(int)
    for key, base in player_metrics.items():
        api_team_id = key[0]
        team_shots[api_team_id] += int(base["shots_total"])
        team_sot[api_team_id] += int(base["shots_on"])

    # Quote squadra + preparazione peer lists per impact
    by_team: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for key in player_metrics:
        by_team[key[0]].append(key)

    enriched: dict[tuple[int, int], dict[str, Any]] = {}
    for key, base in player_metrics.items():
        api_team_id, api_player_id = key
        t_shots = team_shots[api_team_id]
        t_sot = team_sot[api_team_id]
        base = dict(base)
        base["team_shots_share"] = team_share(int(base["shots_total"]), t_shots)
        base["team_sot_share"] = team_share(int(base["shots_on"]), t_sot)
        base["team_denominators"] = {"team_shots_total": t_shots, "team_sot_total": t_sot}
        enriched[key] = base

    # Shooting impact per squadra
    for api_team_id, keys in by_team.items():
        peers_son = [enriched[k]["shots_on_per90"] for k in keys]
        peers_sot = [enriched[k]["shots_total_per90"] for k in keys]
        peers_share = [enriched[k]["team_sot_share"] for k in keys]
        peers_recent = [enriched[k]["recent_shots_on_last5"] for k in keys]
        peers_rating = [enriched[k]["avg_rating"] for k in keys]

        for key in keys:
            b = enriched[key]
            impact = compute_shooting_impact_score(
                minutes_total=int(b["minutes_total"]),
                shots_on_per90=b["shots_on_per90"],
                shots_total_per90=b["shots_total_per90"],
                team_sot_share=b["team_sot_share"],
                recent_shots_on_last5=b["recent_shots_on_last5"],
                avg_rating=b["avg_rating"],
                peer_shots_on_per90=peers_son,
                peer_shots_total_per90=peers_sot,
                peer_team_sot_share=peers_share,
                peer_recent_shots_on_last5=peers_recent,
                peer_avg_rating=peers_rating,
            )
            b["shooting_impact_score"] = impact
            b["reliability_score"] = compute_reliability_score(
                minutes_total=int(b["minutes_total"]),
                matches_played=int(b["matches_played"]),
                recent_minutes_last5=b["recent_minutes_last5"],
                avg_rating=b["avg_rating"],
                has_shot_data=bool(b["has_shot_data"]),
            )

    # UPSERT
    profiles_created_or_updated = 0
    profiles_with_shooting_impact = 0
    profiles_without_enough_minutes = 0

    for key, b in enriched.items():
        api_team_id, api_player_id = key
        agg = aggs[key]
        try:
            existing = db.scalar(
                select(PlayerSeasonProfile).where(
                    PlayerSeasonProfile.season == year,
                    PlayerSeasonProfile.league_id == league_id,
                    PlayerSeasonProfile.api_team_id == api_team_id,
                    PlayerSeasonProfile.api_player_id == api_player_id,
                ),
            )
            common = dict(
                season=year,
                league_id=league_id,
                competition_id=competition_id,
                team_id=agg.team_id,
                api_team_id=api_team_id,
                player_id=agg.player_id,
                api_player_id=api_player_id,
                matches_played=int(b["matches_played"]),
                minutes_total=to_decimal_minutes(float(b["minutes_total"])),
                minutes_avg=to_decimal(b["minutes_avg"]),
                starts_estimated=int(b["starts_estimated"]),
                shots_total=int(b["shots_total"]),
                shots_on=int(b["shots_on"]),
                shots_total_per90=to_decimal(b["shots_total_per90"]),
                shots_on_per90=to_decimal(b["shots_on_per90"]),
                shot_accuracy=to_decimal(b["shot_accuracy"]),
                goals_total=int(b["goals_total"]),
                assists_total=int(b["assists_total"]),
                key_passes_total=int(b["key_passes_total"]),
                key_passes_per90=to_decimal(b["key_passes_per90"]),
                recent_minutes_last5=(
                    to_decimal_minutes(b["recent_minutes_last5"])
                    if b["recent_minutes_last5"] is not None
                    else None
                ),
                recent_shots_total_last5=b["recent_shots_total_last5"],
                recent_shots_on_last5=b["recent_shots_on_last5"],
                recent_rating_last5=to_decimal(b["recent_rating_last5"]),
                avg_rating=to_decimal(b["avg_rating"]),
                team_shots_share=to_decimal(b["team_shots_share"]),
                team_sot_share=to_decimal(b["team_sot_share"]),
                shooting_impact_score=to_decimal(b["shooting_impact_score"]),
                reliability_score=int(b["reliability_score"]),
            )
            if existing is None:
                db.add(PlayerSeasonProfile(**common))
            else:
                for k, v in common.items():
                    setattr(existing, k, v)
            profiles_created_or_updated += 1
            if b["shooting_impact_score"] is not None:
                profiles_with_shooting_impact += 1
            if int(b["minutes_total"]) < MINUTES_FOR_IMPACT:
                profiles_without_enough_minutes += 1
        except Exception as exc:
            logger.warning(
                "player_season_profiles upsert failed team=%s player=%s: %s",
                api_team_id,
                api_player_id,
                exc,
            )
            errors.append(
                {
                    "api_team_id": api_team_id,
                    "api_player_id": api_player_id,
                    "error": str(exc),
                },
            )

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("player_season_profiles commit failed")
        return {
            "status": "error",
            "season": season_year,
            "message": str(exc),
            "players_considered": len(enriched),
            "profiles_created_or_updated": 0,
            "profiles_with_shooting_impact": 0,
            "profiles_without_enough_minutes": 0,
            "teams_processed": len(by_team),
            "top_players_sample": [],
            "warnings": warnings,
            "errors": [{"message": str(exc)}],
            "profile_build_version": "v1",
            "source": "player_match_stats",
            "null_zero_policy": "minutes_gt_0_null_events_treated_as_zero",
            "minimum_minutes_for_impact": MINUTES_FOR_IMPACT,
        }

    top_sample = _top_players_sample(db, year, league_id, limit=10)

    out = {
        "status": "success",
        "season": season_year,
        "players_considered": len(enriched),
        "profiles_created_or_updated": profiles_created_or_updated,
        "profiles_with_shooting_impact": profiles_with_shooting_impact,
        "profiles_without_enough_minutes": profiles_without_enough_minutes,
        "teams_processed": len(by_team),
        "top_players_sample": top_sample,
        "warnings": warnings,
        "errors": errors[:200],
        "profile_build_version": "v1",
        "source": "player_match_stats",
        "null_zero_policy": "minutes_gt_0_null_events_treated_as_zero",
        "minimum_minutes_for_impact": MINUTES_FOR_IMPACT,
    }
    logger.info(
        "player_season_profiles build end season=%s profiles=%s impact=%s",
        season_year,
        profiles_created_or_updated,
        profiles_with_shooting_impact,
    )
    return out


def _top_players_sample(
    db: Session,
    year: int,
    league_id: int,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(PlayerSeasonProfile, PlayerRegistry, Team)
        .join(PlayerRegistry, PlayerRegistry.id == PlayerSeasonProfile.player_id)
        .outerjoin(Team, Team.id == PlayerSeasonProfile.team_id)
        .where(
            PlayerSeasonProfile.season == year,
            PlayerSeasonProfile.league_id == league_id,
            PlayerSeasonProfile.shooting_impact_score.isnot(None),
        )
        .order_by(PlayerSeasonProfile.shooting_impact_score.desc())
        .limit(limit),
    ).all()

    sample: list[dict[str, Any]] = []
    for pr, reg, tm in rows:
        sample.append(
            {
                "team_name": tm.name if tm else None,
                "player_name": reg.name,
                "shots_on_per90": float(pr.shots_on_per90) if pr.shots_on_per90 is not None else None,
                "shots_total_per90": float(pr.shots_total_per90) if pr.shots_total_per90 is not None else None,
                "team_sot_share": float(pr.team_sot_share) if pr.team_sot_share is not None else None,
                "shooting_impact_score": float(pr.shooting_impact_score)
                if pr.shooting_impact_score is not None
                else None,
                "reliability_score": pr.reliability_score,
            },
        )
    return sample


def build_player_season_profiles_for_competition(db: Session, competition_id: int) -> dict[str, Any]:
    from app.models import Competition

    comp = db.get(Competition, competition_id)
    if comp is None:
        return {"status": "error", "message": f"Competition {competition_id} non trovata"}
    if comp.league_id is None:
        return {"status": "error", "message": "Competition senza league_id: eseguire bootstrap"}
    result = build_serie_a_player_season_profiles(
        db,
        comp.season,
        competition_id=comp.id,
        league_id_override=comp.league_id,
    )
    result["competition_id"] = comp.id
    result["competition_key"] = comp.key
    return result
