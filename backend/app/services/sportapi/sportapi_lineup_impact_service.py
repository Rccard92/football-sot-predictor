"""Simulazione Lineup Impact SOT — audit only, non usata nel modello."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Fixture, Player, PlayerSotProfile, Team, TeamSotPrediction
from app.services.sportapi.sportapi_lineup_present import build_sportapi_lineups_audit
from app.services.sportapi.sportapi_player_matching_service import SportApiPlayerMatchingService


def _clamp_factor(factor: float, confirmed: bool) -> float:
    if confirmed:
        return max(0.65, min(1.30, factor))
    return max(0.75, min(1.20, factor))


def _share_pct(profile: PlayerSotProfile | None) -> float:
    if profile is None or profile.team_sot_share_pct is None:
        return 0.0
    return float(profile.team_sot_share_pct) / 100.0


def _pack_player_profile(
    pl: Player | None,
    pr: PlayerSotProfile | None,
    *,
    mapped: dict[str, Any],
) -> dict[str, Any]:
    share = _share_pct(pr)
    sot90 = float(pr.shots_on_target_per90) if pr and pr.shots_on_target_per90 is not None else None
    return {
        "sportapi_player_id": mapped.get("sportapi_player_id"),
        "sportapi_player_name": mapped.get("sportapi_player_name"),
        "api_sports_player_id": mapped.get("api_sports_player_id"),
        "player_id": mapped.get("player_id"),
        "player_name": mapped.get("api_sports_player_name"),
        "mapping_confidence": mapped.get("confidence_score"),
        "mapping_recommendation": mapped.get("recommendation"),
        "team_sot_share": round(share, 4),
        "team_sot_share_pct": round(share * 100, 2),
        "sot_per_90": round(sot90, 3) if sot90 is not None else None,
        "is_top5_sot_team": False,
    }


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
        top5_flags = self._top5_flags(profiles_by_player_id, int(fx.home_team_id), int(fx.away_team_id))

        home_side = self._simulate_side(
            side_data=sportapi_lineups.get("home") or {},
            team_id=int(fx.home_team_id),
            base_sot=base_home,
            confirmed=bool(confirmed),
            match_by_sportapi_id=match_by_sportapi_id,
            profiles_by_player_id=profiles_by_player_id,
            top5_flags=top5_flags,
            team_name=hn,
        )
        away_side = self._simulate_side(
            side_data=sportapi_lineups.get("away") or {},
            team_id=int(fx.away_team_id),
            base_sot=base_away,
            confirmed=bool(confirmed),
            match_by_sportapi_id=match_by_sportapi_id,
            profiles_by_player_id=profiles_by_player_id,
            top5_flags=top5_flags,
            team_name=an,
        )

        bullets: list[str] = []
        bullets.extend(home_side.pop("explanation_bullets", []))
        bullets.extend(away_side.pop("explanation_bullets", []))

        return {
            "status": "ok" if sportapi_lineups.get("available") else "no_lineups",
            "simulation_only": True,
            "used_in_model": settings.use_sportapi_lineup_impact_in_model,
            "profiles_missing": len(profiles_by_player_id) == 0,
            "sportapi_lineups_available": bool(sportapi_lineups.get("available")),
            "confirmed": confirmed,
            "home": home_side,
            "away": away_side,
            "player_matching_summary": matching.get("summary") or {},
            "sportapi_player_matching": matching.get("matches") or [],
            "explanation_bullets": bullets,
            "defensive_opponent_factor": None,
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

    def _top5_flags(
        self,
        profiles: dict[int, tuple[Player, PlayerSotProfile]],
        home_team_id: int,
        away_team_id: int,
    ) -> dict[int, bool]:
        flags: dict[int, bool] = {}
        for tid in (home_team_id, away_team_id):
            team_profiles = [
                (pid, pr)
                for pid, (_pl, pr) in profiles.items()
                if int(pr.team_id) == int(tid) and pr.shots_on_target_per90 is not None
            ]
            team_profiles.sort(
                key=lambda x: float(x[1].shots_on_target_per90 or 0),
                reverse=True,
            )
            for pid, _ in team_profiles[:5]:
                flags[int(pid)] = True
        return flags

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
        team_name: str,
    ) -> dict[str, Any]:
        lineup_weight = 1.0 if confirmed else 0.60

        starter_ids: set[int] = set()
        bench_ids: set[int] = set()
        missing_mapped: list[dict[str, Any]] = []
        missing_unmapped: list[dict[str, Any]] = []

        for p in side_data.get("starters") or []:
            m = match_by_sportapi_id.get(int(p["provider_player_id"]))
            if m and m.get("player_id"):
                starter_ids.add(int(m["player_id"]))

        for p in side_data.get("substitutes") or []:
            m = match_by_sportapi_id.get(int(p["provider_player_id"]))
            if m and m.get("player_id"):
                bench_ids.add(int(m["player_id"]))

        mp = side_data.get("missing_players") or {}
        for group in ("injured", "suspended", "other"):
            for m in mp.get(group) or []:
                match = match_by_sportapi_id.get(int(m["provider_player_id"]))
                entry = {
                    "player_name": m.get("player_name"),
                    "absence_group": group,
                    "mapping": match,
                }
                if match and match.get("recommendation") == "AUTO_SAFE" and match.get("player_id"):
                    missing_mapped.append(entry)
                else:
                    missing_unmapped.append(entry)

        top5_sot: list[dict[str, Any]] = []
        for pid, (pl, pr) in profiles_by_player_id.items():
            if int(pr.team_id) != int(team_id):
                continue
            m = None
            for spid, mat in match_by_sportapi_id.items():
                if mat.get("player_id") == pid:
                    m = mat
                    break
            packed = _pack_player_profile(pl, pr, mapped=m or {})
            packed["is_top5_sot_team"] = top5_flags.get(int(pid), False)
            if top5_flags.get(int(pid)):
                top5_sot.append(packed)
        top5_sot.sort(key=lambda x: float(x.get("team_sot_share") or 0), reverse=True)

        top5_present = [p for p in top5_sot if p.get("player_id") in starter_ids or p.get("player_id") in bench_ids]
        top5_missing = [
            p
            for p in top5_sot
            if p.get("player_id") not in starter_ids and p.get("player_id") not in bench_ids
        ]

        missing_top5_share = sum(float(p.get("team_sot_share") or 0) for p in top5_missing)

        starters_share = 0.0
        for pid in starter_ids:
            _pl, pr = profiles_by_player_id.get(pid, (None, None))
            if pr:
                starters_share += _share_pct(pr)

        bench_share = 0.0
        bench_count = 0
        for pid in bench_ids:
            _pl, pr = profiles_by_player_id.get(pid, (None, None))
            if pr:
                bench_share += _share_pct(pr)
                bench_count += 1
        bench_avg = bench_share / bench_count if bench_count else 0.0

        substitute_estimated_share = bench_avg if bench_count else 0.0
        net_missing = missing_top5_share - substitute_estimated_share
        net_missing = max(0.0, net_missing)

        raw_factor = 1.0 - (net_missing * lineup_weight)
        attacking_factor = _clamp_factor(raw_factor, confirmed)

        base = float(base_sot) if base_sot is not None else None
        adjusted = round(base * attacking_factor, 2) if base is not None else None
        impact_pct = None
        if base is not None and base > 0 and adjusted is not None:
            impact_pct = round((adjusted - base) / base * 100.0, 1)

        bullets: list[str] = []
        if team_name and base is not None and adjusted is not None:
            bullets.append(
                f"{team_name}: base SOT {base:.1f} → simulato {adjusted:.1f} ({impact_pct:+.1f}%)",
            )
        for p in top5_missing[:3]:
            nm = p.get("player_name") or "?"
            sh = p.get("team_sot_share_pct")
            if sh is not None:
                bullets.append(f"{team_name} — {nm} assente: top SOT share {sh:.0f}%")
        if not confirmed:
            bullets.append(f"{team_name}: formazione probabile — peso impatto {lineup_weight:.0%}")

        return {
            "team_name": team_name,
            "formation": side_data.get("formation"),
            "base_expected_sot": base,
            "adjusted_sot_simulated": adjusted,
            "impact_pct": impact_pct,
            "confirmed": confirmed,
            "lineup_confidence_weight": lineup_weight,
            "attacking_lineup_factor": round(attacking_factor, 4),
            "net_missing_sot_share": round(net_missing, 4),
            "missing_top5_sot_share": round(missing_top5_share, 4),
            "starters_sot_share": round(starters_share, 4),
            "bench_sot_share": round(bench_share, 4),
            "top5_sot_players": top5_sot,
            "top5_present": top5_present,
            "top5_missing": top5_missing,
            "missing_players_mapped": missing_mapped,
            "missing_players_unmapped": missing_unmapped,
            "explanation_bullets": bullets,
        }
