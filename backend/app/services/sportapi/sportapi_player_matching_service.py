"""Matching giocatori SportAPI ↔ API-Football (preview audit; no auto-save sotto 90)."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, Player, PlayerProviderMapping, PlayerSotProfile, Season
from app.models.fixture_provider_mapping import FixtureProviderMapping, PROVIDER_SPORTAPI
from app.services.sportapi.sportapi_player_name_normalize import player_names_match

MatchRecommendation = Literal["AUTO_SAFE", "REVIEW", "NO_MATCH"]


def _recommendation(score: float) -> MatchRecommendation:
    if score >= 90:
        return "AUTO_SAFE"
    if score >= 75:
        return "REVIEW"
    return "NO_MATCH"


def _roles_compatible(sportapi_pos: str | None, api_name: str | None) -> bool:
    sp = (sportapi_pos or "").strip().upper()[:1]
    if not sp:
        return True
    # API-Football position in profile often in fixture stats; loose check
    return True


def _birth_compatible(sportapi_raw: dict[str, Any] | None, player_raw: dict[str, Any] | None) -> bool:
    if not isinstance(sportapi_raw, dict) or not isinstance(player_raw, dict):
        return False
    sp = sportapi_raw.get("dateOfBirth") or sportapi_raw.get("date_of_birth")
    pp = player_raw.get("birth") or player_raw.get("dateOfBirth")
    if sp is None or pp is None:
        return False
    return str(sp)[:10] == str(pp)[:10]


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

    if _roles_compatible(sportapi_position, None):
        if sportapi_position:
            breakdown["role"] = 10
            total += 10
        else:
            breakdown["role"] = 0
    else:
        breakdown["role"] = 0

    if _birth_compatible(sportapi_raw, candidate_raw):
        breakdown["birth_date"] = 10
        total += 10
    else:
        breakdown["birth_date"] = 0

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

        season_row = db.get(Season, int(fx.season_id))
        season_year = int(season_row.year) if season_row else None

        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == int(fx.id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        sportapi_home_team_id = mapping.provider_home_team_id if mapping else None
        sportapi_away_team_id = mapping.provider_away_team_id if mapping else None

        roster_home = self._team_roster(db, int(fx.home_team_id), int(fx.season_id), int(fx.league_id))
        roster_away = self._team_roster(db, int(fx.away_team_id), int(fx.season_id), int(fx.league_id))

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
            )
            if cached:
                m = cached
            else:
                m = self._best_match_for_sportapi_player(
                    sp,
                    roster=roster,
                    team_id=team_id,
                    fixture=fx,
                    sportapi_team_id=sportapi_team_id,
                )
            rec = m["recommendation"]
            counts[rec] = counts.get(rec, 0) + 1
            matches.append(m)

        return {
            "status": "ok",
            "fixture_id": int(fx.id),
            "season_year": season_year,
            "matches": matches,
            "summary": counts,
            "note": "Mapping sotto 90 non salvato automaticamente; simulazione audit only.",
        }

    def _team_roster(
        self,
        db: Session,
        team_id: int,
        season_id: int,
        league_id: int,
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            select(PlayerSotProfile, Player)
            .join(Player, Player.id == PlayerSotProfile.player_id)
            .where(
                PlayerSotProfile.team_id == int(team_id),
                PlayerSotProfile.season_id == int(season_id),
            ),
        ).all()
        out: list[dict[str, Any]] = []
        for pr, pl in rows:
            out.append(
                {
                    "player_id": int(pl.id),
                    "api_player_id": int(pl.api_player_id),
                    "name": pl.name,
                    "team_id": int(pr.team_id),
                    "season_id": int(pr.season_id),
                    "league_id": int(league_id),
                    "shots_on_target_per90": pr.shots_on_target_per90,
                    "team_sot_share_pct": pr.team_sot_share_pct,
                    "total_minutes": pr.total_minutes,
                    "raw_json": pl.raw_json if isinstance(pl.raw_json, dict) else None,
                    "jersey_number": None,
                },
            )
        if not out:
            players = list(
                db.scalars(
                    select(Player).where(Player.team_id == int(team_id)),
                ).all(),
            )
            for pl in players:
                out.append(
                    {
                        "player_id": int(pl.id),
                        "api_player_id": int(pl.api_player_id),
                        "name": pl.name,
                        "team_id": int(team_id),
                        "season_id": int(season_id),
                        "league_id": int(league_id),
                        "shots_on_target_per90": None,
                        "team_sot_share_pct": None,
                        "total_minutes": None,
                        "raw_json": pl.raw_json if isinstance(pl.raw_json, dict) else None,
                        "jersey_number": None,
                    },
                )
        return out

    def _lookup_cached_mapping(
        self,
        db: Session,
        sportapi_player_id: int,
        sportapi_team_id: int | None,
        season: int | None,
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
        return {
            "sportapi_player_id": int(sportapi_player_id),
            "sportapi_player_name": row.player_name_sportapi,
            "api_sports_player_id": int(row.api_sports_player_id),
            "api_sports_player_name": row.player_name_api_sports,
            "player_id": None,
            "confidence_score": score,
            "recommendation": _recommendation(score),
            "matched_by": row.matched_by or "cached_mapping",
            "score_breakdown": {"cached": True},
            "from_db_mapping": True,
        }

    def _best_match_for_sportapi_player(
        self,
        sp: dict[str, Any],
        *,
        roster: list[dict[str, Any]],
        team_id: int,
        fixture: Fixture,
        sportapi_team_id: int | None,
    ) -> dict[str, Any]:
        sportapi_pid = int(sp["provider_player_id"])
        sportapi_name = str(sp.get("player_name") or "")
        sportapi_short = sp.get("short_name")
        sportapi_pos = sp.get("position")
        sportapi_jersey = sp.get("jersey_number")
        raw = sp.get("_raw_payload") if isinstance(sp.get("_raw_payload"), dict) else None

        best_score = 0.0
        best: dict[str, Any] | None = None
        best_breakdown: dict[str, Any] = {}

        for cand in roster:
            score, breakdown = score_player_match(
                sportapi_name=sportapi_name,
                sportapi_short=str(sportapi_short) if sportapi_short else None,
                sportapi_position=str(sportapi_pos) if sportapi_pos else None,
                sportapi_jersey=int(sportapi_jersey) if sportapi_jersey is not None else None,
                sportapi_raw=raw,
                candidate_name=cand["name"],
                candidate_team_id=int(cand["team_id"]),
                expected_team_id=int(team_id),
                season_id=int(cand["season_id"]),
                fixture_season_id=int(fixture.season_id),
                fixture_league_id=int(fixture.league_id),
                league_id=int(cand["league_id"]),
                candidate_jersey=cand.get("jersey_number"),
                candidate_raw=cand.get("raw_json"),
            )
            if score > best_score:
                best_score = score
                best = cand
                best_breakdown = breakdown

        rec = _recommendation(best_score)
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
            "confidence_score": best_score if best else 0.0,
            "recommendation": rec,
            "matched_by": "auto_name_team" if rec == "AUTO_SAFE" else "auto_preview",
            "score_breakdown": best_breakdown,
            "from_db_mapping": False,
        }

    def collect_sportapi_players_from_lineups(self, sportapi_lineups: dict[str, Any]) -> list[dict[str, Any]]:
        """Estrae giocatori da payload build_sportapi_lineups_audit."""
        out: list[dict[str, Any]] = []
        for side_key in ("home", "away"):
            side = sportapi_lineups.get(side_key) or {}
            for p in side.get("starters") or []:
                out.append({**p, "team_side": side_key, "is_missing": False})
            for p in side.get("substitutes") or []:
                out.append({**p, "team_side": side_key, "is_missing": False})
            mp = side.get("missing_players") or {}
            for group in ("injured", "suspended", "other"):
                for m in mp.get(group) or []:
                    out.append({**m, "team_side": side_key, "is_missing": True})
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
