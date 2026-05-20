"""Simulazione Lineup Impact SOT — audit only, non usata nel modello."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Fixture, Player, PlayerSotProfile, Team, TeamSotPrediction
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
        profiles_missing = len(profiles_by_player_id) == 0

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

        all_top = (home_side.get("top_sot_players") or []) + (away_side.get("top_sot_players") or [])
        confidence_label, confidence_reasons = compute_impact_confidence(
            confirmed=bool(confirmed),
            top_players=all_top,
            profiles_missing=profiles_missing,
        )

        payload = {
            "status": "ok" if sportapi_lineups.get("available") else "no_lineups",
            "simulation_only": True,
            "used_in_model": settings.use_sportapi_lineup_impact_in_model,
            "profiles_missing": profiles_missing,
            "sportapi_lineups_available": bool(sportapi_lineups.get("available")),
            "confirmed": confirmed,
            "confidence_label": confidence_label,
            "confidence_reasons": confidence_reasons,
            "home": home_side,
            "away": away_side,
            "player_matching_summary": matching.get("summary") or {},
            "sportapi_player_matching": matching.get("matches") or [],
            "explanation_bullets": bullets,
            "defensive_opponent_factor": None,
            "note": "Simulazione audit; non modifica team_sot_predictions.",
        }
        return payload

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
        missing_mapped: list[dict[str, Any]] = []
        missing_unmapped: list[dict[str, Any]] = []
        for group in ("injured", "suspended", "other"):
            for m in mp.get(group) or []:
                pid = int(m["provider_player_id"])
                sportapi_missing_pids.add(pid)
                sportapi_row_by_pid[pid] = m
                missing_meta_by_pid[pid] = {"absence_group": group, "description": m.get("description")}
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

            status = classify_lineup_status(
                player_id=int(pid),
                mapping_recommendation=m.get("recommendation") if m else None,
                mapping_confidence=float(m["confidence_score"]) if m and m.get("confidence_score") is not None else None,
                sportapi_provider_id=provider_id,
                sportapi_starter_pids=sportapi_starter_pids,
                sportapi_bench_pids=sportapi_bench_pids,
                sportapi_missing_pids=sportapi_missing_pids,
            )

            display_role = to_display_role(
                (sportapi_row or {}).get("position") if sportapi_row else (m.get("sportapi_position") if m else None),
            )
            absence_group = (meta or {}).get("absence_group")
            description = (meta or {}).get("description")
            note = status_note_it(status, absence_group=absence_group, description=description)

            pw = penalty_weight_for_status(status, confirmed)
            penalty_share = share * pw if status != "UNMAPPED" else 0.0

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

        net_lineup_loss = max(0.0, gross_penalty - replacement_credit_total)
        unmapped_count = sum(1 for p in top_sot_players if p["status"] == "UNMAPPED")
        unresolved_names = sum(
            1 for p in top_sot_players if str(p.get("player_name", "")).startswith("Nome non disponibile")
        )
        confidence_multiplier = 1.0
        if unmapped_count >= 2 or unresolved_names >= 2:
            confidence_multiplier = 0.95

        raw_factor = 1.0 - (net_lineup_loss * lineup_weight)
        factor = clamp_factor(raw_factor, confirmed, confidence_multiplier=confidence_multiplier)

        base = float(base_sot) if base_sot is not None else None
        adjusted = round(base * factor, 2) if base is not None else None
        impact_pct = None
        if base is not None and base > 0 and adjusted is not None:
            impact_pct = round((adjusted - base) / base * 100.0, 1)

        summary_by_status = dict(Counter(p["status"] for p in top_sot_players))

        bullets: list[str] = []
        if team_name and base is not None and adjusted is not None:
            bullets.append(
                f"{team_name}: base SOT {base:.1f} → simulato {adjusted:.1f} ({impact_pct:+.1f}%)",
            )
        bullets.extend(side_reasons[:6])
        if not confirmed:
            bullets.append(f"{team_name}: formazione probabile — peso impatto {lineup_weight:.0%}")

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
            "factor": round(factor, 4),
            "attacking_lineup_factor": round(factor, 4),
            "gross_penalty_share": round(gross_penalty, 4),
            "replacement_credit_share": round(replacement_credit_total, 4),
            "net_lineup_loss_share": round(net_lineup_loss, 4),
            "net_missing_sot_share": round(net_lineup_loss, 4),
            "missing_top5_sot_share": round(gross_penalty, 4),
            "top_sot_players": top_sot_players,
            "summary_by_status": summary_by_status,
            "reasons": side_reasons,
            "top5_sot_players": top_sot_players,
            "top5_present": [],
            "top5_missing": [],
            "missing_players_mapped": missing_mapped,
            "missing_players_unmapped": missing_unmapped,
            "explanation_bullets": bullets,
        }
