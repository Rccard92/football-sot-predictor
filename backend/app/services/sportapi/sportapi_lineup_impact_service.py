"""Simulazione Lineup Impact SOT — audit only, non usata nel modello."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixturePlayerStat, Player, PlayerSotProfile, PlayerTeamSeason, Season, Team, TeamSotPrediction
from app.services.player_data.active_roster_resolver import ActiveRosterResolver
from app.services.sportapi.sportapi_defensive_weakness_logic import (
    DEFENSIVE_TOP_N,
    compute_defensive_weakness_side,
    compute_raw_defensive_importance,
    is_defensive_relevant_position,
    defensive_role_group,
    normalize_defensive_scores,
)
from app.services.sportapi.sportapi_lineup_impact_logic import (
    build_reason_sentence,
    classify_lineup_status,
    clamp_factor,
    compute_impact_confidence,
    find_replacement,
    penalty_weight_for_status,
    resolve_display_name,
    status_note_it,
)
from app.services.sportapi.sportapi_lineup_present import build_sportapi_lineups_audit, to_display_role
from app.services.sportapi.sportapi_player_matching_service import SportApiPlayerMatchingService


def _share_frac(profile: PlayerSotProfile | None) -> float:
    if profile is None or profile.team_sot_share_pct is None:
        return 0.0
    return float(profile.team_sot_share_pct) / 100.0


class LineupImpactSimulationService:
    def simulate_for_fixture(
        self,
        db: Session,
        fixture_id: int,
        *,
        active_model_version: str | None = None,
        home_team_name: str | None = None,
        away_team_name: str | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return {"status": "error", "message": "Fixture non trovata", "simulation_only": True}

        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        hn = home_team_name or (home.name if home else "Casa")
        an = away_team_name or (away.name if away else "Trasferta")
        season = db.get(Season, int(fx.season_id))
        season_year = int(season.year) if season else 0
        league_id = int(season.league_id) if season else int(fx.league_id)

        sportapi_lineups = build_sportapi_lineups_audit(db, int(fx.id), home_team_name=hn, away_team_name=an)

        match_svc = SportApiPlayerMatchingService()
        sportapi_players = match_svc.collect_sportapi_players_from_lineups(sportapi_lineups)
        matching = match_svc.match_players_for_fixture(
            db,
            int(fx.id),
            sportapi_players=sportapi_players,
        )
        match_by_sportapi_id = {
            int(m["sportapi_player_id"]): m for m in (matching.get("matches") or [])
        }

        base_home, base_away = self._base_expected_sot(db, fx, active_model_version)
        confirmed = sportapi_lineups.get("confirmed")
        if confirmed is None:
            confirmed = False

        profiles_by_player_id = self._profiles_for_teams(
            db,
            int(fx.season_id),
            int(fx.home_team_id),
            int(fx.away_team_id),
        )
        profiles_missing = len(profiles_by_player_id) == 0

        roster_resolver = ActiveRosterResolver(db)
        home_ctx = roster_resolver.load_team_context(
            season_year=season_year,
            league_id=league_id,
            api_team_id=int(home.api_team_id) if home else 0,
            internal_team_id=int(fx.home_team_id),
        )
        away_ctx = roster_resolver.load_team_context(
            season_year=season_year,
            league_id=league_id,
            api_team_id=int(away.api_team_id) if away else 0,
            internal_team_id=int(fx.away_team_id),
        )

        home_top5, home_excluded, home_top_meta = self._resolve_top5_for_team(
            profiles_by_player_id,
            int(fx.home_team_id),
            roster_resolver,
            home_ctx,
        )
        away_top5, away_excluded, away_top_meta = self._resolve_top5_for_team(
            profiles_by_player_id,
            int(fx.away_team_id),
            roster_resolver,
            away_ctx,
        )
        top5_flags = {**{pid: True for pid in home_top5}, **{pid: True for pid in away_top5}}
        top5_meta = {**home_top_meta, **away_top_meta}

        home_off = self._simulate_side(
            side_data=sportapi_lineups.get("home") or {},
            team_id=int(fx.home_team_id),
            base_sot=base_home,
            confirmed=bool(confirmed),
            match_by_sportapi_id=match_by_sportapi_id,
            profiles_by_player_id=profiles_by_player_id,
            top5_flags=top5_flags,
            top5_meta=top5_meta,
            team_name=hn,
            excluded_players=home_excluded,
            roster_sync_hint=roster_resolver.roster_sync_hint(home_ctx),
            apply_final_adjusted=False,
        )
        away_off = self._simulate_side(
            side_data=sportapi_lineups.get("away") or {},
            team_id=int(fx.away_team_id),
            base_sot=base_away,
            confirmed=bool(confirmed),
            match_by_sportapi_id=match_by_sportapi_id,
            profiles_by_player_id=profiles_by_player_id,
            top5_flags=top5_flags,
            top5_meta=top5_meta,
            team_name=an,
            excluded_players=away_excluded,
            roster_sync_hint=roster_resolver.roster_sync_hint(away_ctx),
            apply_final_adjusted=False,
        )

        home_def = self._simulate_defensive_side(
            db=db,
            fx=fx,
            side_data=sportapi_lineups.get("home") or {},
            team_id=int(fx.home_team_id),
            team_name=hn,
            confirmed=bool(confirmed),
            match_by_sportapi_id=match_by_sportapi_id,
            profiles_by_player_id=profiles_by_player_id,
            roster_resolver=roster_resolver,
            roster_ctx=home_ctx,
            season_year=season_year,
            league_id=league_id,
        )
        away_def = self._simulate_defensive_side(
            db=db,
            fx=fx,
            side_data=sportapi_lineups.get("away") or {},
            team_id=int(fx.away_team_id),
            team_name=an,
            confirmed=bool(confirmed),
            match_by_sportapi_id=match_by_sportapi_id,
            profiles_by_player_id=profiles_by_player_id,
            roster_resolver=roster_resolver,
            roster_ctx=away_ctx,
            season_year=season_year,
            league_id=league_id,
        )

        off_home = float(home_off.get("offensive_lineup_factor") or 1.0)
        off_away = float(away_off.get("offensive_lineup_factor") or 1.0)
        def_weak_away = float(away_def.get("defensive_weakness_factor") or 1.0)
        def_weak_home = float(home_def.get("defensive_weakness_factor") or 1.0)

        home_off["opponent_defensive_weakness_factor"] = round(def_weak_away, 4)
        away_off["opponent_defensive_weakness_factor"] = round(def_weak_home, 4)

        bh = home_off.get("base_sot")
        ba = away_off.get("base_sot")
        if bh is not None:
            final_h = round(float(bh) * off_home * def_weak_away, 2)
            home_off["adjusted_sot"] = final_h
            home_off["adjusted_sot_simulated"] = final_h
            home_off["factor"] = round(off_home * def_weak_away, 4)
            home_off["attacking_lineup_factor"] = round(off_home, 4)
            if float(bh) > 0:
                home_off["impact_pct"] = round((final_h - float(bh)) / float(bh) * 100.0, 1)
        if ba is not None:
            final_a = round(float(ba) * off_away * def_weak_home, 2)
            away_off["adjusted_sot"] = final_a
            away_off["adjusted_sot_simulated"] = final_a
            away_off["factor"] = round(off_away * def_weak_home, 4)
            away_off["attacking_lineup_factor"] = round(off_away, 4)
            if float(ba) > 0:
                away_off["impact_pct"] = round((final_a - float(ba)) / float(ba) * 100.0, 1)

        home_off.update(
            {
                "defensive_weakness_factor": home_def.get("defensive_weakness_factor"),
                "gross_defensive_loss": home_def.get("gross_defensive_loss"),
                "defensive_replacement_credit": home_def.get("defensive_replacement_credit"),
                "net_defensive_loss": home_def.get("net_defensive_loss"),
                "defensive_key_players": home_def.get("defensive_key_players"),
                "defensive_reasons": home_def.get("defensive_reasons"),
            },
        )
        away_off.update(
            {
                "defensive_weakness_factor": away_def.get("defensive_weakness_factor"),
                "gross_defensive_loss": away_def.get("gross_defensive_loss"),
                "defensive_replacement_credit": away_def.get("defensive_replacement_credit"),
                "net_defensive_loss": away_def.get("net_defensive_loss"),
                "defensive_key_players": away_def.get("defensive_key_players"),
                "defensive_reasons": away_def.get("defensive_reasons"),
            },
        )

        bullets: list[str] = []
        bullets.extend(home_off.pop("explanation_bullets", []))
        bullets.extend(away_off.pop("explanation_bullets", []))
        bullets.extend(home_def.get("defensive_reasons") or [])
        bullets.extend(away_def.get("defensive_reasons") or [])
        for ex in home_excluded[:2]:
            bullets.append(
                f"{hn} — {ex.get('player_name')} escluso dal calcolo: {ex.get('exclusion_reason')}",
            )
        for ex in away_excluded[:2]:
            bullets.append(
                f"{an} — {ex.get('player_name')} escluso dal calcolo: {ex.get('exclusion_reason')}",
            )

        all_top = (home_off.get("top_sot_players") or []) + (away_off.get("top_sot_players") or [])
        home_hint = roster_resolver.roster_sync_hint(home_ctx)
        away_hint = roster_resolver.roster_sync_hint(away_ctx)
        roster_filter_active = home_hint == "ok" and away_hint == "ok"

        confidence_label, confidence_reasons = compute_impact_confidence(
            confirmed=bool(confirmed),
            top_players=all_top,
            profiles_missing=profiles_missing,
            roster_sync_hints=[home_hint, away_hint],
            excluded_count=len(home_excluded) + len(away_excluded),
            roster_unknown_in_top=sum(
                1 for p in all_top if p.get("included_as_unknown") or p.get("roster_status") == "UNKNOWN"
            ),
            defensive_stats_limited=bool(
                home_def.get("defensive_stats_limited") or away_def.get("defensive_stats_limited")
            ),
        )

        return {
            "status": "ok" if sportapi_lineups.get("available") else "no_lineups",
            "fixture_id": int(fx.id),
            "simulation_only": True,
            "used_in_model": settings.use_sportapi_lineup_impact_in_model,
            "profiles_missing": profiles_missing,
            "sportapi_lineups_available": bool(sportapi_lineups.get("available")),
            "confirmed": confirmed,
            "confidence_label": confidence_label,
            "confidence_reasons": confidence_reasons,
            "roster_filter_active": roster_filter_active,
            "home": home_off,
            "away": away_off,
            "player_matching_summary": matching.get("summary") or {},
            "sportapi_player_matching": matching.get("matches") or [],
            "explanation_bullets": bullets,
            "defensive_opponent_factor": {
                "home_opponent_factor": round(def_weak_away, 4),
                "away_opponent_factor": round(def_weak_home, 4),
            },
            "note": "Simulazione audit; non modifica team_sot_predictions.",
        }

    def _base_expected_sot(
        self,
        db: Session,
        fx: Fixture,
        model_version: str | None,
    ) -> tuple[float | None, float | None]:
        if not model_version:
            return None, None
        rows = list(
            db.scalars(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id == int(fx.id),
                    TeamSotPrediction.model_version == str(model_version),
                ),
            ).all(),
        )
        home = next((r for r in rows if int(r.team_id) == int(fx.home_team_id)), None)
        away = next((r for r in rows if int(r.team_id) == int(fx.away_team_id)), None)
        bh = float(home.predicted_sot) if home and home.predicted_sot is not None else None
        ba = float(away.predicted_sot) if away and away.predicted_sot is not None else None
        return bh, ba

    def _profiles_for_teams(
        self,
        db: Session,
        season_id: int,
        home_team_id: int,
        away_team_id: int,
    ) -> dict[int, tuple[Player, PlayerSotProfile]]:
        rows = db.execute(
            select(PlayerSotProfile, Player)
            .join(Player, Player.id == PlayerSotProfile.player_id)
            .where(
                PlayerSotProfile.season_id == int(season_id),
                PlayerSotProfile.team_id.in_([int(home_team_id), int(away_team_id)]),
            ),
        ).all()
        return {int(pl.id): (pl, pr) for pr, pl in rows}

    def _resolve_top5_for_team(
        self,
        profiles: dict[int, tuple[Player, PlayerSotProfile]],
        team_id: int,
        resolver: ActiveRosterResolver,
        ctx: Any,
    ) -> tuple[set[int], list[dict[str, Any]], dict[int, dict[str, Any]]]:
        candidates: list[dict[str, Any]] = []
        for pid, (pl, pr) in profiles.items():
            if int(pr.team_id) != int(team_id) or pr.shots_on_target_per90 is None:
                continue
            candidates.append(
                {
                    "player_id": int(pid),
                    "api_player_id": int(pl.api_player_id),
                    "player_name": pl.name,
                    "legacy_team_id": pl.team_id,
                    "team_sot_share_pct": pr.team_sot_share_pct,
                    "shots_on_target_per90": pr.shots_on_target_per90,
                },
            )
        top, scan_excluded = resolver.filter_top_candidates(
            candidates=candidates,
            ctx=ctx,
            top_n=5,
            allow_legacy_active=False,
        )
        full_excluded = resolver.collect_excluded_players(
            candidates=candidates,
            ctx=ctx,
            allow_legacy_active=False,
        )
        excluded_by_id: dict[int, dict[str, Any]] = {}
        for ex in scan_excluded + full_excluded:
            pid = ex.get("player_id")
            if pid is not None:
                excluded_by_id[int(pid)] = ex
        excluded = list(excluded_by_id.values())
        excluded.sort(key=lambda x: float(x.get("team_sot_share_pct") or 0), reverse=True)

        meta = {
            int(t["player_id"]): {
                "roster_status": t.get("roster_status"),
                "included_as_unknown": bool(t.get("included_as_unknown")),
            }
            for t in top
        }
        return {int(t["player_id"]) for t in top}, excluded, meta

    def _lineup_indices(
        self,
        side_data: dict[str, Any],
        match_by_sportapi_id: dict[int, dict[str, Any]],
    ) -> tuple[set[int], set[int], set[int], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
        sportapi_starter_pids: set[int] = set()
        sportapi_bench_pids: set[int] = set()
        sportapi_missing_pids: set[int] = set()
        sportapi_row_by_pid: dict[int, dict[str, Any]] = {}
        missing_meta_by_pid: dict[int, dict[str, Any]] = {}

        for p in side_data.get("starters") or []:
            pid = int(p["provider_player_id"])
            sportapi_starter_pids.add(pid)
            sportapi_row_by_pid[pid] = p
        for p in side_data.get("substitutes") or []:
            pid = int(p["provider_player_id"])
            sportapi_bench_pids.add(pid)
            sportapi_row_by_pid[pid] = p
        mp = side_data.get("missing_players") or {}
        for group in ("injured", "suspended", "other"):
            for m in mp.get(group) or []:
                pid = int(m["provider_player_id"])
                sportapi_missing_pids.add(pid)
                sportapi_row_by_pid[pid] = m
                missing_meta_by_pid[pid] = {
                    "absence_group": group,
                    "description": m.get("description"),
                }
        return (
            sportapi_starter_pids,
            sportapi_bench_pids,
            sportapi_missing_pids,
            sportapi_row_by_pid,
            missing_meta_by_pid,
        )

    def _aggregate_defensive_stats(
        self,
        db: Session,
        *,
        team_id: int,
        season_id: int,
    ) -> dict[int, dict[str, Any]]:
        rows = db.execute(
            select(
                FixturePlayerStat.player_id,
                func.sum(FixturePlayerStat.minutes).label("total_minutes"),
                func.count(FixturePlayerStat.id).label("appearances"),
                func.sum(
                    case((FixturePlayerStat.substitute.is_(False), 1), else_=0),
                ).label("starts"),
                func.avg(FixturePlayerStat.rating).label("avg_rating"),
                func.sum(FixturePlayerStat.tackles_total).label("tackles_total"),
                func.sum(FixturePlayerStat.interceptions).label("interceptions"),
                func.sum(FixturePlayerStat.tackles_blocks).label("tackles_blocks"),
                func.sum(FixturePlayerStat.duels_won).label("duels_won"),
                func.max(FixturePlayerStat.position).label("position"),
            )
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(
                FixturePlayerStat.team_id == int(team_id),
                Fixture.season_id == int(season_id),
                Fixture.status.in_(FINISHED_STATUSES),
            )
            .group_by(FixturePlayerStat.player_id),
        ).all()

        out: dict[int, dict[str, Any]] = {}
        for row in rows:
            pid = int(row.player_id)
            tackles = int(row.tackles_total or 0)
            interceptions = int(row.interceptions or 0)
            blocks = int(row.tackles_blocks or 0)
            duels = int(row.duels_won or 0)
            has_def_stats = tackles + interceptions + blocks + duels > 0
            out[pid] = {
                "total_minutes": int(row.total_minutes or 0),
                "appearances": int(row.appearances or 0),
                "starts": int(row.starts or 0),
                "avg_rating": float(row.avg_rating) if row.avg_rating is not None else None,
                "tackles_total": tackles,
                "interceptions": interceptions,
                "tackles_blocks": blocks,
                "duels_won": duels,
                "position": row.position,
                "stats_source": "full" if has_def_stats else "minutes_role_only",
            }
        return out

    def _pts_positions(
        self,
        db: Session,
        *,
        season_year: int,
        league_id: int,
        api_team_id: int,
        api_player_ids: set[int],
    ) -> dict[int, str | None]:
        if not api_player_ids:
            return {}
        rows = db.scalars(
            select(PlayerTeamSeason).where(
                PlayerTeamSeason.season == int(season_year),
                PlayerTeamSeason.league_id == int(league_id),
                PlayerTeamSeason.api_team_id == int(api_team_id),
                PlayerTeamSeason.api_player_id.in_(list(api_player_ids)),
            ),
        ).all()
        return {int(r.api_player_id): r.position for r in rows}

    def _simulate_defensive_side(
        self,
        *,
        db: Session,
        fx: Fixture,
        side_data: dict[str, Any],
        team_id: int,
        team_name: str,
        confirmed: bool,
        match_by_sportapi_id: dict[int, dict[str, Any]],
        profiles_by_player_id: dict[int, tuple[Player, PlayerSotProfile]],
        roster_resolver: ActiveRosterResolver,
        roster_ctx: Any,
        season_year: int,
        league_id: int,
    ) -> dict[str, Any]:
        (
            sportapi_starter_pids,
            sportapi_bench_pids,
            sportapi_missing_pids,
            sportapi_row_by_pid,
            missing_meta_by_pid,
        ) = self._lineup_indices(side_data, match_by_sportapi_id)

        match_by_player_id: dict[int, dict[str, Any]] = {}
        for _spid, mat in match_by_sportapi_id.items():
            if mat.get("player_id"):
                match_by_player_id[int(mat["player_id"])] = mat

        team = db.get(Team, int(team_id))
        api_team_id = int(team.api_team_id) if team else 0
        def_agg = self._aggregate_defensive_stats(db, team_id=int(team_id), season_id=int(fx.season_id))

        candidates: list[dict[str, Any]] = []
        for pid, (pl, _pr) in profiles_by_player_id.items():
            if int(_pr.team_id) != int(team_id):
                continue
            agg = def_agg.get(int(pid))
            if not agg:
                continue
            pos = agg.get("position")
            pts_pos = None
            api_pid = int(pl.api_player_id)
            pts_positions = self._pts_positions(
                db,
                season_year=season_year,
                league_id=league_id,
                api_team_id=api_team_id,
                api_player_ids={api_pid},
            )
            pos = pts_positions.get(api_pid) or pos
            if not is_defensive_relevant_position(pos):
                continue
            roster = roster_resolver.resolve_player(
                api_player_id=api_pid,
                ctx=roster_ctx,
                legacy_team_id=pl.team_id,
                allow_legacy_active=False,
            )
            if roster_ctx.has_squad_data:
                if roster.status != "ACTIVE":
                    continue
            elif roster.status not in ("ACTIVE", "UNKNOWN"):
                continue
            raw_imp = compute_raw_defensive_importance(
                position=pos,
                total_minutes=int(agg["total_minutes"]),
                starts=int(agg["starts"]),
                appearances=int(agg["appearances"]),
                avg_rating=agg.get("avg_rating"),
                tackles_total=int(agg["tackles_total"]),
                interceptions=int(agg["interceptions"]),
                tackles_blocks=int(agg["tackles_blocks"]),
                duels_won=int(agg["duels_won"]),
            )
            candidates.append(
                {
                    "player_id": int(pid),
                    "api_player_id": api_pid,
                    "player_name": pl.name,
                    "position": pos,
                    "defensive_role": defensive_role_group(pos),
                    "raw_defensive_importance": raw_imp,
                    "stats_source": agg.get("stats_source"),
                    "roster_status": roster.status,
                },
            )

        candidates.sort(key=lambda x: float(x.get("raw_defensive_importance") or 0), reverse=True)
        candidates = candidates[:DEFENSIVE_TOP_N]
        normalize_defensive_scores(candidates)

        key_players: list[dict[str, Any]] = []
        for c in candidates:
            pid = int(c["player_id"])
            m = match_by_player_id.get(pid)
            provider_id = int(m["sportapi_player_id"]) if m and m.get("sportapi_player_id") else None
            sportapi_row = sportapi_row_by_pid.get(provider_id) if provider_id else None
            meta = missing_meta_by_pid.get(provider_id) if provider_id else None
            display_name = resolve_display_name(
                player_name_api=c.get("player_name"),
                mapping_name_api=m.get("api_sports_player_name") if m else None,
                sportapi_name=(sportapi_row or {}).get("player_name") if sportapi_row else None,
                sportapi_short=(sportapi_row or {}).get("short_name") if sportapi_row else None,
                api_player_id=int(c["api_player_id"]),
                sportapi_player_id=provider_id,
            )
            if c.get("roster_status") == "UNKNOWN":
                lineup_status = "UNMAPPED"
            else:
                lineup_status = classify_lineup_status(
                    player_id=pid,
                    mapping_recommendation=m.get("recommendation") if m else None,
                    mapping_confidence=float(m["confidence_score"])
                    if m and m.get("confidence_score") is not None
                    else None,
                    sportapi_provider_id=provider_id,
                    sportapi_starter_pids=sportapi_starter_pids,
                    sportapi_bench_pids=sportapi_bench_pids,
                    sportapi_missing_pids=sportapi_missing_pids,
                )
            note = status_note_it(
                lineup_status,
                absence_group=(meta or {}).get("absence_group"),
                description=(meta or {}).get("description"),
            )
            key_players.append(
                {
                    **c,
                    "player_name": display_name,
                    "status": lineup_status,
                    "status_note": note,
                    "sportapi_player_id": provider_id,
                },
            )

        starter_pool: list[dict[str, Any]] = []
        bench_pool: list[dict[str, Any]] = []
        for spid in sportapi_starter_pids:
            mat = match_by_sportapi_id.get(spid)
            if not mat or mat.get("recommendation") != "AUTO_SAFE" or not mat.get("player_id"):
                continue
            apid = int(mat["player_id"])
            row = sportapi_row_by_pid.get(spid) or {}
            agg = def_agg.get(apid, {})
            pos = row.get("position") or agg.get("position")
            if not is_defensive_relevant_position(pos):
                continue
            imp_row = next((k for k in candidates if int(k["player_id"]) == apid), None)
            imp = float(imp_row["defensive_importance"]) if imp_row else 0.3
            _pl, _ = profiles_by_player_id.get(apid, (None, None))
            starter_pool.append(
                {
                    "player_id": apid,
                    "player_name": resolve_display_name(
                        player_name_api=_pl.name if _pl else None,
                        mapping_name_api=mat.get("api_sports_player_name"),
                        sportapi_name=row.get("player_name"),
                        api_player_id=int(_pl.api_player_id) if _pl else None,
                        sportapi_player_id=spid,
                    ),
                    "defensive_role": defensive_role_group(pos),
                    "defensive_importance": imp,
                },
            )
        for spid in sportapi_bench_pids:
            mat = match_by_sportapi_id.get(spid)
            if not mat or mat.get("recommendation") != "AUTO_SAFE" or not mat.get("player_id"):
                continue
            apid = int(mat["player_id"])
            row = sportapi_row_by_pid.get(spid) or {}
            agg = def_agg.get(apid, {})
            pos = row.get("position") or agg.get("position")
            if not is_defensive_relevant_position(pos):
                continue
            imp_row = next((k for k in candidates if int(k["player_id"]) == apid), None)
            imp = float(imp_row["defensive_importance"]) if imp_row else 0.2
            _pl, _ = profiles_by_player_id.get(apid, (None, None))
            bench_pool.append(
                {
                    "player_id": apid,
                    "player_name": resolve_display_name(
                        player_name_api=_pl.name if _pl else None,
                        mapping_name_api=mat.get("api_sports_player_name"),
                        sportapi_name=row.get("player_name"),
                        api_player_id=int(_pl.api_player_id) if _pl else None,
                        sportapi_player_id=spid,
                    ),
                    "defensive_role": defensive_role_group(pos),
                    "defensive_importance": imp,
                },
            )

        return compute_defensive_weakness_side(
            team_name=team_name,
            confirmed=confirmed,
            key_players=key_players,
            starter_pool=starter_pool,
            bench_pool=bench_pool,
        )

    def _simulate_side(
        self,
        *,
        side_data: dict[str, Any],
        team_id: int,
        base_sot: float | None,
        confirmed: bool,
        match_by_sportapi_id: dict[int, dict[str, Any]],
        profiles_by_player_id: dict[int, tuple[Player, PlayerSotProfile]],
        top5_flags: dict[int, bool],
        top5_meta: dict[int, dict[str, Any]],
        team_name: str,
        excluded_players: list[dict[str, Any]],
        roster_sync_hint: str,
        apply_final_adjusted: bool = True,
    ) -> dict[str, Any]:
        lineup_weight = 1.0 if confirmed else 0.60

        (
            sportapi_starter_pids,
            sportapi_bench_pids,
            sportapi_missing_pids,
            sportapi_row_by_pid,
            missing_meta_by_pid,
        ) = self._lineup_indices(side_data, match_by_sportapi_id)

        missing_mapped: list[dict[str, Any]] = []
        missing_unmapped: list[dict[str, Any]] = []
        mp = side_data.get("missing_players") or {}
        for group in ("injured", "suspended", "other"):
            for m in mp.get(group) or []:
                pid = int(m["provider_player_id"])
                match = match_by_sportapi_id.get(pid)
                entry = {
                    "player_name": m.get("player_name"),
                    "absence_group": group,
                    "mapping": match,
                }
                if match and match.get("recommendation") == "AUTO_SAFE" and match.get("player_id"):
                    missing_mapped.append(entry)
                else:
                    missing_unmapped.append(entry)

        match_by_player_id: dict[int, dict[str, Any]] = {}
        for _spid, mat in match_by_sportapi_id.items():
            if mat.get("player_id"):
                match_by_player_id[int(mat["player_id"])] = mat

        top_sot_players: list[dict[str, Any]] = []
        for pid, (pl, pr) in profiles_by_player_id.items():
            if int(pr.team_id) != int(team_id):
                continue
            if not top5_flags.get(int(pid)):
                continue
            m = match_by_player_id.get(int(pid))
            share = _share_frac(pr)
            sot90 = float(pr.shots_on_target_per90) if pr.shots_on_target_per90 is not None else None
            provider_id = int(m["sportapi_player_id"]) if m and m.get("sportapi_player_id") else None
            sportapi_row = sportapi_row_by_pid.get(provider_id) if provider_id else None
            meta = missing_meta_by_pid.get(provider_id) if provider_id else None

            display_name = resolve_display_name(
                player_name_api=pl.name if pl else None,
                mapping_name_api=m.get("api_sports_player_name") if m else None,
                sportapi_name=(sportapi_row or {}).get("player_name") if sportapi_row else None,
                sportapi_short=(sportapi_row or {}).get("short_name") if sportapi_row else None,
                api_player_id=int(pl.api_player_id) if pl and pl.api_player_id else None,
                sportapi_player_id=provider_id,
            )

            pmeta = top5_meta.get(int(pid), {})
            included_unknown = bool(pmeta.get("included_as_unknown"))
            roster_status = pmeta.get("roster_status") or "ACTIVE"

            status = classify_lineup_status(
                player_id=int(pid),
                mapping_recommendation=m.get("recommendation") if m else None,
                mapping_confidence=float(m["confidence_score"])
                if m and m.get("confidence_score") is not None
                else None,
                sportapi_provider_id=provider_id,
                sportapi_starter_pids=sportapi_starter_pids,
                sportapi_bench_pids=sportapi_bench_pids,
                sportapi_missing_pids=sportapi_missing_pids,
            )

            display_role = to_display_role(
                (sportapi_row or {}).get("position")
                if sportapi_row
                else (m.get("sportapi_position") if m else None),
            )
            absence_group = (meta or {}).get("absence_group")
            description = (meta or {}).get("description")
            note = status_note_it(status, absence_group=absence_group, description=description)

            pw = penalty_weight_for_status(status, confirmed)
            if status == "UNMAPPED" or included_unknown:
                penalty_share = 0.0
            else:
                penalty_share = share * pw

            top_sot_players.append(
                {
                    "player_id": int(pid),
                    "player_name": display_name,
                    "api_sports_player_id": int(pl.api_player_id) if pl and pl.api_player_id else None,
                    "sportapi_player_id": provider_id,
                    "sportapi_player_name": m.get("sportapi_player_name") if m else None,
                    "mapping_confidence": m.get("confidence_score") if m else None,
                    "mapping_recommendation": m.get("recommendation") if m else None,
                    "team_sot_share": round(share, 4),
                    "team_sot_share_pct": round(share * 100, 2),
                    "sot_per_90": round(sot90, 3) if sot90 is not None else None,
                    "display_role": display_role,
                    "status": status,
                    "status_note": note,
                    "penalty_weight": pw,
                    "penalty_share": round(penalty_share, 4),
                    "replacement_player_id": None,
                    "replacement_player_name": None,
                    "replacement_share": None,
                    "replacement_credit": 0.0,
                    "net_loss_share": round(penalty_share, 4),
                    "is_top5_sot_team": True,
                    "roster_status": roster_status,
                    "included_as_unknown": included_unknown,
                },
            )

        top_sot_players.sort(key=lambda x: float(x.get("team_sot_share") or 0), reverse=True)

        starter_pool: list[dict[str, Any]] = []
        bench_pool: list[dict[str, Any]] = []
        for spid in sportapi_starter_pids:
            mat = match_by_sportapi_id.get(spid)
            if not mat or mat.get("recommendation") != "AUTO_SAFE" or not mat.get("player_id"):
                continue
            apid = int(mat["player_id"])
            _pl, pr = profiles_by_player_id.get(apid, (None, None))
            if not pr:
                continue
            row = sportapi_row_by_pid.get(spid) or {}
            starter_pool.append(
                {
                    "player_id": apid,
                    "player_name": resolve_display_name(
                        player_name_api=_pl.name if _pl else None,
                        mapping_name_api=mat.get("api_sports_player_name"),
                        sportapi_name=row.get("player_name"),
                        sportapi_short=row.get("short_name"),
                        api_player_id=int(_pl.api_player_id) if _pl and _pl.api_player_id else None,
                        sportapi_player_id=spid,
                    ),
                    "display_role": row.get("display_role") or to_display_role(row.get("position")),
                    "team_sot_share": _share_frac(pr),
                    "sot_per_90": float(pr.shots_on_target_per90) if pr.shots_on_target_per90 else 0.0,
                },
            )
        for spid in sportapi_bench_pids:
            mat = match_by_sportapi_id.get(spid)
            if not mat or mat.get("recommendation") != "AUTO_SAFE" or not mat.get("player_id"):
                continue
            apid = int(mat["player_id"])
            _pl, pr = profiles_by_player_id.get(apid, (None, None))
            if not pr:
                continue
            row = sportapi_row_by_pid.get(spid) or {}
            bench_pool.append(
                {
                    "player_id": apid,
                    "player_name": resolve_display_name(
                        player_name_api=_pl.name if _pl else None,
                        mapping_name_api=mat.get("api_sports_player_name"),
                        sportapi_name=row.get("player_name"),
                        sportapi_short=row.get("short_name"),
                        api_player_id=int(_pl.api_player_id) if _pl and _pl.api_player_id else None,
                        sportapi_player_id=spid,
                    ),
                    "display_role": row.get("display_role") or to_display_role(row.get("position")),
                    "team_sot_share": _share_frac(pr),
                    "sot_per_90": float(pr.shots_on_target_per90) if pr.shots_on_target_per90 else 0.0,
                },
            )

        used_replacements: set[int] = set()
        gross_penalty = 0.0
        replacement_credit_total = 0.0
        side_reasons: list[str] = []
        offensive_reasons: list[str] = []

        for player in top_sot_players:
            status = player["status"]
            penalty_share = float(player["penalty_share"])
            if status == "UNMAPPED" or penalty_share <= 0:
                player["net_loss_share"] = 0.0
                continue

            gross_penalty += penalty_share
            rep, credit, _rep_status = find_replacement(
                target_role=str(player["display_role"]),
                target_share=float(player["team_sot_share"]),
                starter_pool=starter_pool,
                bench_pool=bench_pool,
                used_replacement_player_ids=used_replacements,
            )
            if rep:
                rid = int(rep["player_id"])
                used_replacements.add(rid)
                player["replacement_player_id"] = rid
                player["replacement_player_name"] = rep.get("player_name")
                player["replacement_share"] = round(float(rep.get("team_sot_share") or 0), 4)
                player["replacement_credit"] = round(credit, 4)
                replacement_credit_total += credit

            net_loss = max(0.0, penalty_share - float(player["replacement_credit"]))
            player["net_loss_share"] = round(net_loss, 4)

            reason = build_reason_sentence(
                team_name=team_name,
                player_name=str(player["player_name"]),
                status=status,
                confirmed=confirmed,
                sot_share_pct=float(player["team_sot_share_pct"]),
                penalty_share=penalty_share,
                replacement_name=player.get("replacement_player_name"),
                replacement_credit=float(player["replacement_credit"]),
                note=str(player["status_note"]),
            )
            if reason:
                side_reasons.append(reason)
                offensive_reasons.append(reason)

        net_lineup_loss = max(0.0, gross_penalty - replacement_credit_total)
        unmapped_count = sum(1 for p in top_sot_players if p["status"] == "UNMAPPED")
        unresolved_names = sum(
            1 for p in top_sot_players if str(p.get("player_name", "")).startswith("Nome non disponibile")
        )
        confidence_multiplier = 1.0
        if unmapped_count >= 2 or unresolved_names >= 2:
            confidence_multiplier = 0.95

        raw_factor = 1.0 - (net_lineup_loss * lineup_weight)
        offensive_factor = clamp_factor(raw_factor, confirmed, confidence_multiplier=confidence_multiplier)

        base = float(base_sot) if base_sot is not None else None
        adjusted = None
        impact_pct = None
        if apply_final_adjusted and base is not None:
            adjusted = round(base * offensive_factor, 2)
            if base > 0 and adjusted is not None:
                impact_pct = round((adjusted - base) / base * 100.0, 1)

        summary_by_status = dict(Counter(p["status"] for p in top_sot_players))

        bullets: list[str] = []
        if apply_final_adjusted and team_name and base is not None and adjusted is not None:
            bullets.append(
                f"{team_name}: base SOT {base:.1f} → simulato {adjusted:.1f} ({impact_pct:+.1f}%)",
            )
        bullets.extend(side_reasons[:6])
        if not confirmed:
            bullets.append(f"{team_name}: formazione probabile — peso impatto {lineup_weight:.0%}")

        formatted_excluded = [
            {
                "player_name": ex.get("player_name"),
                "team_sot_share_pct": ex.get("team_sot_share_pct"),
                "roster_status": ex.get("roster_status"),
                "exclusion_reason": ex.get("exclusion_reason"),
                "shots_on_target_per90": ex.get("shots_on_target_per90"),
            }
            for ex in excluded_players
        ]

        return {
            "team_name": team_name,
            "formation": side_data.get("formation"),
            "base_sot": base,
            "adjusted_sot": adjusted,
            "base_expected_sot": base,
            "adjusted_sot_simulated": adjusted,
            "impact_pct": impact_pct,
            "confirmed": confirmed,
            "lineup_confidence_weight": lineup_weight,
            "offensive_lineup_factor": round(offensive_factor, 4),
            "factor": round(offensive_factor, 4),
            "opponent_defensive_weakness_factor": 1.0,
            "gross_penalty_share": round(gross_penalty, 4),
            "replacement_credit_share": round(replacement_credit_total, 4),
            "net_lineup_loss_share": round(net_lineup_loss, 4),
            "net_missing_sot_share": round(net_lineup_loss, 4),
            "missing_top5_sot_share": round(gross_penalty, 4),
            "top_sot_players": top_sot_players,
            "summary_by_status": summary_by_status,
            "reasons": side_reasons,
            "offensive_reasons": offensive_reasons,
            "excluded_players": formatted_excluded,
            "roster_sync_hint": roster_sync_hint,
            "top5_sot_players": top_sot_players,
            "top5_present": [],
            "top5_missing": [],
            "missing_players_mapped": missing_mapped,
            "missing_players_unmapped": missing_unmapped,
            "explanation_bullets": bullets,
        }
