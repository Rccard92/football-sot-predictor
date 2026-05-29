"""Matching giocatori SportAPI ↔ profili player_season_profiles (preview audit; no auto-save sotto 90)."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerProviderMapping, Team
from app.models.fixture_provider_mapping import FixtureProviderMapping, PROVIDER_SPORTAPI
from app.services.sportapi.lineup_player_profile_lookup import (
    _recommendation,
    find_best_profile_match,
    load_fixture_profiles,
    team_roster_for_matching,
)
from app.services.sportapi.sportapi_player_name_normalize import player_names_match

MatchRecommendation = Literal["AUTO_SAFE", "REVIEW", "NO_MATCH"]


def score_player_match(
    *,
    sportapi_name: str,
    sportapi_short: str | None,
    sportapi_position: str | None,
    sportapi_jersey: int | None,
    sportapi_raw: dict[str, Any] | None,
    candidate_name: str,
    candidate_team_id: int,
    expected_team_id: int,
    season_id: int,
    fixture_season_id: int,
    fixture_league_id: int,
    league_id: int,
    candidate_jersey: int | None = None,
    candidate_raw: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    breakdown: dict[str, Any] = {}
    total = 0.0

    if player_names_match(sportapi_name, candidate_name, extra=sportapi_short):
        breakdown["name"] = 50
        total += 50
    else:
        breakdown["name"] = 0

    if int(candidate_team_id) == int(expected_team_id):
        breakdown["team"] = 20
        total += 20
    else:
        breakdown["team"] = 0

    if int(season_id) == int(fixture_season_id) and int(league_id) == int(fixture_league_id):
        breakdown["season_league"] = 10
        total += 10
    else:
        breakdown["season_league"] = 0

    if (
        sportapi_jersey is not None
        and candidate_jersey is not None
        and int(sportapi_jersey) == int(candidate_jersey)
    ):
        breakdown["jersey"] = 10
        total += 10
    else:
        breakdown["jersey"] = 0

    if sportapi_position:
        breakdown["role"] = 10
        total += 10
    else:
        breakdown["role"] = 0

    return round(total, 2), breakdown


class SportApiPlayerMatchingService:
    def match_players_for_fixture(
        self,
        db: Session,
        fixture_id: int,
        *,
        sportapi_players: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Preview matching per tutti i giocatori SportAPI della fixture (lineup + missing)."""
        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return {"status": "error", "message": "Fixture non trovata", "matches": []}

        season_row = fx.season
        season_year = int(season_row.year) if season_row else None
        competition_id = int(fx.competition_id) if fx.competition_id is not None else None

        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == int(fx.id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        sportapi_home_team_id = mapping.provider_home_team_id if mapping else None
        sportapi_away_team_id = mapping.provider_away_team_id if mapping else None

        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))

        _, _, team_entries = load_fixture_profiles(db, fx, home=home, away=away)
        home_entries = team_entries.get("home") or []
        away_entries = team_entries.get("away") or []

        roster_home = team_roster_for_matching(
            db,
            fx,
            team_id=int(fx.home_team_id),
            api_team_id=int(home.api_team_id) if home else 0,
            team_entries=home_entries,
        )
        roster_away = team_roster_for_matching(
            db,
            fx,
            team_id=int(fx.away_team_id),
            api_team_id=int(away.api_team_id) if away else 0,
            team_entries=away_entries,
        )
        competition_roster = roster_home + roster_away if competition_id is not None else None

        players_in = sportapi_players or []
        matches: list[dict[str, Any]] = []
        counts = {"AUTO_SAFE": 0, "REVIEW": 0, "NO_MATCH": 0}

        for sp in players_in:
            side = str(sp.get("team_side") or sp.get("side") or "home")
            sportapi_team_id = sportapi_home_team_id if side == "home" else sportapi_away_team_id
            team_id = int(fx.home_team_id) if side == "home" else int(fx.away_team_id)
            roster = roster_home if side == "home" else roster_away

            cached = self._lookup_cached_mapping(
                db,
                int(sp["provider_player_id"]),
                sportapi_team_id,
                season_year,
                roster=roster,
            )
            if cached:
                m = cached
            else:
                m = self._best_match_for_sportapi_player(
                    sp,
                    roster=roster,
                    competition_roster=competition_roster,
                    team_id=team_id,
                    fixture=fx,
                    sportapi_team_id=sportapi_team_id,
                    competition_id=competition_id,
                )
            rec = m["recommendation"]
            counts[rec] = counts.get(rec, 0) + 1
            matches.append(m)

        return {
            "status": "ok",
            "fixture_id": int(fx.id),
            "competition_id": competition_id,
            "season_year": season_year,
            "matches": matches,
            "summary": counts,
            "note": "Mapping sotto 90 non salvato automaticamente; simulazione audit only.",
        }

    def _lookup_cached_mapping(
        self,
        db: Session,
        sportapi_player_id: int,
        sportapi_team_id: int | None,
        season: int | None,
        *,
        roster: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        stmt = select(PlayerProviderMapping).where(
            PlayerProviderMapping.sportapi_player_id == int(sportapi_player_id),
        )
        if sportapi_team_id is not None and season is not None:
            stmt = stmt.where(
                PlayerProviderMapping.api_sports_team_id == int(sportapi_team_id),
                PlayerProviderMapping.season == int(season),
            )
        row = db.scalar(stmt)
        if row is None or row.api_sports_player_id is None:
            return None
        score = float(row.confidence_score or 0)
        api_id = int(row.api_sports_player_id)
        cand = next((c for c in (roster or []) if int(c.get("api_player_id") or 0) == api_id), None)
        return {
            "sportapi_player_id": int(sportapi_player_id),
            "sportapi_player_name": row.player_name_sportapi,
            "api_sports_player_id": api_id,
            "api_sports_player_name": row.player_name_api_sports or (cand["name"] if cand else None),
            "player_id": int(cand["player_id"]) if cand else None,
            "player_profile_id": cand.get("player_profile_id") if cand else None,
            "matched_profile_name": row.player_name_api_sports or (cand["name"] if cand else None),
            "confidence_score": score,
            "recommendation": _recommendation(score),
            "matched_by": row.matched_by or "cached_mapping",
            "score_breakdown": {"cached": True},
            "from_db_mapping": True,
            "match_reason": "mapping salvato in DB",
            "shots_on_per90": cand.get("shots_on_target_per90") if cand else None,
            "team_sot_share": (
                float(cand["team_sot_share_pct"]) / 100.0
                if cand and cand.get("team_sot_share_pct") is not None
                else None
            ),
            "shooting_impact_score": cand.get("shooting_impact_score") if cand else None,
            "reliability_score": cand.get("reliability_score") if cand else None,
        }

    def _best_match_for_sportapi_player(
        self,
        sp: dict[str, Any],
        *,
        roster: list[dict[str, Any]],
        competition_roster: list[dict[str, Any]] | None,
        team_id: int,
        fixture: Fixture,
        sportapi_team_id: int | None,
        competition_id: int | None,
    ) -> dict[str, Any]:
        sportapi_pid = int(sp["provider_player_id"])
        sportapi_name = str(sp.get("player_name") or "")
        sportapi_short = sp.get("short_name")
        sportapi_pos = sp.get("position")
        sportapi_jersey = sp.get("jersey_number")

        best, best_score, best_breakdown, best_reason = find_best_profile_match(
            sp,
            team_roster=roster,
            competition_roster=competition_roster,
            team_id=int(team_id),
            competition_id=competition_id,
        )

        rec = _recommendation(best_score)
        share = None
        if best and best.get("team_sot_share_pct") is not None:
            share = float(best["team_sot_share_pct"]) / 100.0

        return {
            "sportapi_player_id": sportapi_pid,
            "sportapi_player_name": sportapi_name,
            "sportapi_short_name": sportapi_short,
            "sportapi_position": sportapi_pos,
            "sportapi_jersey": sportapi_jersey,
            "team_side": sp.get("team_side"),
            "is_missing": bool(sp.get("is_missing")),
            "api_sports_player_id": int(best["api_player_id"]) if best else None,
            "api_sports_player_name": best["name"] if best else None,
            "player_id": int(best["player_id"]) if best else None,
            "player_profile_id": best.get("player_profile_id") if best else None,
            "matched_profile_name": best["name"] if best else None,
            "confidence_score": best_score if best else 0.0,
            "recommendation": rec,
            "matched_by": "auto_name_team" if rec == "AUTO_SAFE" else "auto_preview",
            "score_breakdown": best_breakdown,
            "from_db_mapping": False,
            "match_reason": best_reason if best else "nessun profilo candidato nella squadra",
            "reason": best_reason if best else "nessun profilo candidato nella squadra",
            "shots_on_per90": best.get("shots_on_target_per90") if best else None,
            "team_sot_share": share,
            "shooting_impact_score": best.get("shooting_impact_score") if best else None,
            "reliability_score": best.get("reliability_score") if best else None,
        }

    def collect_sportapi_players_from_lineups(self, sportapi_lineups: dict[str, Any]) -> list[dict[str, Any]]:
        """Estrae giocatori da payload build_sportapi_lineups_audit."""
        out: list[dict[str, Any]] = []
        for side_key in ("home", "away"):
            side = sportapi_lineups.get(side_key) or {}
            for p in side.get("starters") or []:
                out.append({**p, "team_side": side_key, "is_missing": False, "_lineup_role": "starter"})
            for p in side.get("substitutes") or []:
                out.append({**p, "team_side": side_key, "is_missing": False, "_lineup_role": "bench"})
            mp = side.get("missing_players") or {}
            for group in ("injured", "suspended", "other"):
                for m in mp.get(group) or []:
                    out.append({**m, "team_side": side_key, "is_missing": True, "_lineup_role": "indisponibile"})
        return out

    def confirm_player_mapping(
        self,
        db: Session,
        *,
        sportapi_player_id: int,
        api_sports_player_id: int,
        sportapi_name: str,
        api_sports_name: str | None,
        api_sports_team_id: int | None,
        sportapi_team_id: int | None,
        league_id: int | None,
        season: int | None,
        confidence_score: float,
        matched_by: str = "admin_manual",
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Salva mapping solo se chiamato esplicitamente (es. futuro admin confirm)."""
        if confidence_score < 90:
            return {
                "status": "rejected",
                "message": "confidence_score < 90: salvataggio non consentito senza override esplicito",
            }
        stmt = select(PlayerProviderMapping).where(
            PlayerProviderMapping.sportapi_player_id == int(sportapi_player_id),
        )
        if api_sports_team_id is not None:
            stmt = stmt.where(PlayerProviderMapping.api_sports_team_id == int(api_sports_team_id))
        if season is not None:
            stmt = stmt.where(PlayerProviderMapping.season == int(season))
        row = db.scalar(stmt)
        if row is None:
            row = PlayerProviderMapping(
                sportapi_player_id=int(sportapi_player_id),
                player_name_sportapi=sportapi_name[:255],
            )
            db.add(row)
        row.api_sports_player_id = int(api_sports_player_id)
        row.player_name_api_sports = (api_sports_name or "")[:255] or None
        row.api_sports_team_id = api_sports_team_id
        row.sportapi_team_id = sportapi_team_id
        row.league_id = league_id
        row.season = season
        row.confidence_score = float(confidence_score)
        row.matched_by = matched_by
        row.raw_payload = raw_payload
        db.commit()
        return {"status": "success", "mapping_id": int(row.id)}
