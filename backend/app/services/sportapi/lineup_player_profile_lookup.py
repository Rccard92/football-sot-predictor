"""Lookup profili giocatore per Lineup Impact — player_season_profiles scoped per competition."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Fixture, Player, PlayerRegistry, PlayerSeasonProfile, PlayerSotProfile, PlayerTeamSeason, Team
from app.services.sportapi.sportapi_player_name_normalize import (
    fuzzy_player_name_score,
    normalize_player_name,
    player_names_match,
)

MatchRecommendation = str  # AUTO_SAFE | REVIEW | NO_MATCH


def _recommendation(score: float) -> MatchRecommendation:
    if score >= 90:
        return "AUTO_SAFE"
    if score >= 75:
        return "REVIEW"
    return "NO_MATCH"


def _float_or_none(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


@dataclass
class MockPlayer:
    id: int
    api_player_id: int
    name: str
    team_id: int | None


@dataclass
class MockSotProfile:
    team_id: int
    shots_on_target_per90: float | None
    team_sot_share_pct: float | None
    total_minutes: float | None


@dataclass
class LineupProfileEntry:
    api_player_id: int
    profile_key: int
    name: str
    normalized_name: str | None
    team_id: int
    player_profile_id: str | None
    shots_on_target_per90: float | None
    shots_total_per90: float | None
    team_sot_share_pct: float | None
    shooting_impact_score: float | None
    reliability_score: int | None
    total_minutes: float | None
    position: str | None
    legacy_player_id: int | None
    mock_player: MockPlayer
    mock_profile: MockSotProfile


def _share_pct_from_profile(p: PlayerSeasonProfile) -> float | None:
    if p.team_sot_share is not None:
        return round(float(p.team_sot_share) * 100.0, 4)
    return None


def _legacy_player_id_by_api(db: Session, api_player_ids: set[int]) -> dict[int, int]:
    if not api_player_ids:
        return {}
    rows = db.scalars(select(Player).where(Player.api_player_id.in_(list(api_player_ids)))).all()
    return {int(p.api_player_id): int(p.id) for p in rows}


def _pack_entry(
    *,
    profile: PlayerSeasonProfile,
    registry: PlayerRegistry,
    position: str | None,
    team_id: int,
    legacy_by_api: dict[int, int],
) -> LineupProfileEntry:
    api_id = int(profile.api_player_id)
    legacy_id = legacy_by_api.get(api_id)
    profile_key = int(legacy_id) if legacy_id is not None else api_id
    sot90 = _float_or_none(profile.shots_on_per90)
    share_pct = _share_pct_from_profile(profile)
    name = registry.name
    mock_player = MockPlayer(
        id=profile_key,
        api_player_id=api_id,
        name=name,
        team_id=int(team_id),
    )
    mock_profile = MockSotProfile(
        team_id=int(team_id),
        shots_on_target_per90=sot90,
        team_sot_share_pct=share_pct,
        total_minutes=_float_or_none(profile.minutes_total),
    )
    return LineupProfileEntry(
        api_player_id=api_id,
        profile_key=profile_key,
        name=name,
        normalized_name=registry.normalized_name or normalize_player_name(name),
        team_id=int(team_id),
        player_profile_id=str(profile.id),
        shots_on_target_per90=sot90,
        shots_total_per90=_float_or_none(profile.shots_total_per90),
        team_sot_share_pct=share_pct,
        shooting_impact_score=_float_or_none(profile.shooting_impact_score),
        reliability_score=int(profile.reliability_score) if profile.reliability_score is not None else None,
        total_minutes=_float_or_none(profile.minutes_total),
        position=position,
        legacy_player_id=legacy_id,
        mock_player=mock_player,
        mock_profile=mock_profile,
    )


def _season_profile_filters(
    *,
    competition_id: int | None,
    season: int,
    league_id: int,
    api_team_id: int,
) -> tuple:
    filters = [
        PlayerSeasonProfile.season == int(season),
        PlayerSeasonProfile.league_id == int(league_id),
        PlayerSeasonProfile.api_team_id == int(api_team_id),
    ]
    if competition_id is not None:
        filters.append(PlayerSeasonProfile.competition_id == int(competition_id))
    return tuple(filters)


def load_team_profile_rows(
    db: Session,
    *,
    competition_id: int | None,
    season: int,
    league_id: int,
    api_team_id: int,
    team_id: int,
) -> list[LineupProfileEntry]:
    base_filter = _season_profile_filters(
        competition_id=competition_id,
        season=season,
        league_id=league_id,
        api_team_id=api_team_id,
    )
    rows = db.execute(
        select(PlayerSeasonProfile, PlayerRegistry, PlayerTeamSeason.position)
        .join(PlayerRegistry, PlayerRegistry.id == PlayerSeasonProfile.player_id)
        .outerjoin(
            PlayerTeamSeason,
            (PlayerTeamSeason.season == PlayerSeasonProfile.season)
            & (PlayerTeamSeason.league_id == PlayerSeasonProfile.league_id)
            & (PlayerTeamSeason.api_team_id == PlayerSeasonProfile.api_team_id)
            & (PlayerTeamSeason.api_player_id == PlayerSeasonProfile.api_player_id),
        )
        .where(*base_filter),
    ).all()
    if not rows:
        return []
    api_ids = {int(pr.api_player_id) for pr, _, _ in rows}
    legacy_by_api = _legacy_player_id_by_api(db, api_ids)
    return [
        _pack_entry(
            profile=pr,
            registry=reg,
            position=pos,
            team_id=int(team_id),
            legacy_by_api=legacy_by_api,
        )
        for pr, reg, pos in rows
    ]


def _load_legacy_sot_profiles(
    db: Session,
    *,
    season_id: int,
    team_id: int,
) -> list[LineupProfileEntry]:
    rows = db.execute(
        select(PlayerSotProfile, Player)
        .join(Player, Player.id == PlayerSotProfile.player_id)
        .where(
            PlayerSotProfile.season_id == int(season_id),
            PlayerSotProfile.team_id == int(team_id),
        ),
    ).all()
    out: list[LineupProfileEntry] = []
    for pr, pl in rows:
        api_id = int(pl.api_player_id)
        profile_key = int(pl.id)
        mock_player = MockPlayer(id=profile_key, api_player_id=api_id, name=pl.name, team_id=pl.team_id)
        mock_profile = MockSotProfile(
            team_id=int(pr.team_id),
            shots_on_target_per90=float(pr.shots_on_target_per90) if pr.shots_on_target_per90 is not None else None,
            team_sot_share_pct=float(pr.team_sot_share_pct) if pr.team_sot_share_pct is not None else None,
            total_minutes=float(pr.total_minutes) if pr.total_minutes is not None else None,
        )
        out.append(
            LineupProfileEntry(
                api_player_id=api_id,
                profile_key=profile_key,
                name=pl.name,
                normalized_name=normalize_player_name(pl.name),
                team_id=int(team_id),
                player_profile_id=None,
                shots_on_target_per90=mock_profile.shots_on_target_per90,
                shots_total_per90=None,
                team_sot_share_pct=mock_profile.team_sot_share_pct,
                shooting_impact_score=None,
                reliability_score=None,
                total_minutes=mock_profile.total_minutes,
                position=None,
                legacy_player_id=profile_key,
                mock_player=mock_player,
                mock_profile=mock_profile,
            ),
        )
    return out


def load_fixture_profiles(
    db: Session,
    fx: Fixture,
    *,
    home: Team | None = None,
    away: Team | None = None,
) -> tuple[dict[int, tuple[MockPlayer, MockSotProfile]], int, dict[str, list[LineupProfileEntry]]]:
    """Ritorna (profiles_by_key, total_count, team_entries)."""
    if fx.season is None and fx.season_id is not None:
        from app.models import Season

        fx.season = db.get(Season, int(fx.season_id))
    home = home or db.get(Team, int(fx.home_team_id))
    away = away or db.get(Team, int(fx.away_team_id))
    competition_id = int(fx.competition_id) if fx.competition_id is not None else None
    season_year = int(fx.season.year) if fx.season else 0
    league_id = int(fx.league_id or 0)

    home_entries: list[LineupProfileEntry] = []
    away_entries: list[LineupProfileEntry] = []

    if home and season_year and league_id:
        home_entries = load_team_profile_rows(
            db,
            competition_id=competition_id,
            season=season_year,
            league_id=league_id,
            api_team_id=int(home.api_team_id),
            team_id=int(home.id),
        )
    if away and season_year and league_id:
        away_entries = load_team_profile_rows(
            db,
            competition_id=competition_id,
            season=season_year,
            league_id=league_id,
            api_team_id=int(away.api_team_id),
            team_id=int(away.id),
        )

    if not home_entries and not away_entries and fx.season_id is not None:
        if home:
            home_entries = _load_legacy_sot_profiles(db, season_id=int(fx.season_id), team_id=int(home.id))
        if away:
            away_entries = _load_legacy_sot_profiles(db, season_id=int(fx.season_id), team_id=int(away.id))

    profiles: dict[int, tuple[MockPlayer, MockSotProfile]] = {}
    for entry in home_entries + away_entries:
        profiles[int(entry.profile_key)] = (entry.mock_player, entry.mock_profile)

    total = len(home_entries) + len(away_entries)
    return profiles, total, {"home": home_entries, "away": away_entries}


def count_competition_profiles_for_teams(
    db: Session,
    *,
    competition_id: int | None,
    season: int,
    league_id: int,
    api_team_ids: list[int],
) -> int:
    if not api_team_ids:
        return 0
    stmt = select(func.count()).select_from(PlayerSeasonProfile).where(
        PlayerSeasonProfile.season == int(season),
        PlayerSeasonProfile.league_id == int(league_id),
        PlayerSeasonProfile.api_team_id.in_([int(t) for t in api_team_ids]),
    )
    if competition_id is not None:
        stmt = stmt.where(PlayerSeasonProfile.competition_id == int(competition_id))
    return int(db.scalar(stmt) or 0)


def team_roster_for_matching(
    db: Session,
    fx: Fixture,
    *,
    team_id: int,
    api_team_id: int,
    team_entries: list[LineupProfileEntry] | None = None,
) -> list[dict[str, Any]]:
    competition_id = int(fx.competition_id) if fx.competition_id is not None else None
    season_year = int(fx.season.year) if fx.season else 0
    league_id = int(fx.league_id or 0)
    entries = team_entries
    if entries is None and season_year and league_id:
        entries = load_team_profile_rows(
            db,
            competition_id=competition_id,
            season=season_year,
            league_id=league_id,
            api_team_id=int(api_team_id),
            team_id=int(team_id),
        )
    if not entries and fx.season_id is not None:
        entries = _load_legacy_sot_profiles(db, season_id=int(fx.season_id), team_id=int(team_id))

    out: list[dict[str, Any]] = []
    for e in entries or []:
        out.append(
            {
                "player_id": int(e.profile_key),
                "api_player_id": int(e.api_player_id),
                "name": e.name,
                "normalized_name": e.normalized_name,
                "team_id": int(e.team_id),
                "season_id": int(fx.season_id or 0),
                "league_id": int(league_id),
                "competition_id": competition_id,
                "shots_on_target_per90": e.shots_on_target_per90,
                "team_sot_share_pct": e.team_sot_share_pct,
                "total_minutes": e.total_minutes,
                "shooting_impact_score": e.shooting_impact_score,
                "reliability_score": e.reliability_score,
                "player_profile_id": e.player_profile_id,
                "position": e.position,
                "raw_json": None,
                "jersey_number": None,
            },
        )
    return out


def score_profile_match(
    *,
    sportapi_name: str,
    sportapi_short: str | None,
    sportapi_position: str | None,
    sportapi_jersey: int | None,
    candidate: dict[str, Any],
    same_team: bool,
    same_competition: bool,
) -> tuple[float, dict[str, Any], str]:
    breakdown: dict[str, Any] = {}
    total = 0.0
    reason_parts: list[str] = []

    cand_name = str(candidate.get("name") or "")
    cand_norm = str(candidate.get("normalized_name") or normalize_player_name(cand_name))

    if player_names_match(sportapi_name, cand_name, extra=sportapi_short):
        breakdown["name"] = 50
        total += 50
        reason_parts.append("nome esatto normalizzato")
    else:
        fuzzy = fuzzy_player_name_score(sportapi_name, cand_name, extra=sportapi_short)
        if fuzzy >= 0.88:
            breakdown["name_fuzzy"] = 45
            total += 45
            reason_parts.append("fuzzy nome squadra")
        elif fuzzy >= 0.75:
            breakdown["name_fuzzy"] = 35
            total += 35
            reason_parts.append("fuzzy nome parziale")
        else:
            breakdown["name"] = 0

    if same_team:
        breakdown["team"] = 20
        total += 20
    else:
        breakdown["team"] = 0
        if not same_competition:
            return 0.0, breakdown, "squadra/competition diversa"

    if same_competition:
        breakdown["competition"] = 10
        total += 10

    if (
        sportapi_jersey is not None
        and candidate.get("jersey_number") is not None
        and int(sportapi_jersey) == int(candidate["jersey_number"])
    ):
        breakdown["jersey"] = 10
        total += 10

    if sportapi_position and candidate.get("position"):
        sp = str(sportapi_position).strip().upper()[:1]
        cp = str(candidate["position"]).strip().upper()[:1]
        if sp == cp:
            breakdown["role"] = 10
            total += 10

    if normalize_player_name(sportapi_name) == cand_norm:
        breakdown["normalized_exact"] = 5
        total += 5

    reason = "; ".join(reason_parts) if reason_parts else "score composito"
    return round(min(total, 100.0), 2), breakdown, reason


def find_best_profile_match(
    sp: dict[str, Any],
    *,
    team_roster: list[dict[str, Any]],
    competition_roster: list[dict[str, Any]] | None,
    team_id: int,
    competition_id: int | None,
) -> tuple[dict[str, Any] | None, float, dict[str, Any], str]:
    sportapi_name = str(sp.get("player_name") or "")
    sportapi_short = sp.get("short_name")
    sportapi_pos = sp.get("position")
    sportapi_jersey = sp.get("jersey_number")

    best: dict[str, Any] | None = None
    best_score = 0.0
    best_breakdown: dict[str, Any] = {}
    best_reason = "nessun candidato"

    for cand in team_roster:
        score, breakdown, reason = score_profile_match(
            sportapi_name=sportapi_name,
            sportapi_short=str(sportapi_short) if sportapi_short else None,
            sportapi_position=str(sportapi_pos) if sportapi_pos else None,
            sportapi_jersey=int(sportapi_jersey) if sportapi_jersey is not None else None,
            candidate=cand,
            same_team=int(cand.get("team_id") or 0) == int(team_id),
            same_competition=True,
        )
        if score > best_score:
            best_score = score
            best = cand
            best_breakdown = breakdown
            best_reason = reason

    if best_score < 75 and competition_roster and competition_id is not None:
        for cand in competition_roster:
            if int(cand.get("team_id") or 0) == int(team_id):
                continue
            score, breakdown, reason = score_profile_match(
                sportapi_name=sportapi_name,
                sportapi_short=str(sportapi_short) if sportapi_short else None,
                sportapi_position=str(sportapi_pos) if sportapi_pos else None,
                sportapi_jersey=int(sportapi_jersey) if sportapi_jersey is not None else None,
                candidate=cand,
                same_team=False,
                same_competition=int(cand.get("competition_id") or 0) == int(competition_id),
            )
            if score >= 75 and score > best_score:
                best_score = score
                best = cand
                best_breakdown = breakdown
                best_reason = f"cross-team competition: {reason}"

    return best, best_score, best_breakdown, best_reason


def lineup_role_label(sp: dict[str, Any]) -> str:
    if sp.get("is_missing"):
        return "indisponibile"
    side = str(sp.get("team_side") or "")
    if sp.get("_lineup_role") == "starter":
        return "titolare"
    if sp.get("_lineup_role") == "bench":
        return "panchina"
    return "titolare" if not sp.get("is_missing") else "indisponibile"


def build_mapping_debug_row(
    sp: dict[str, Any],
    match: dict[str, Any],
    *,
    team_name: str,
) -> dict[str, Any]:
    rec = str(match.get("recommendation") or "NO_MATCH")
    return {
        "sportapi_player_name": match.get("sportapi_player_name") or sp.get("player_name"),
        "team_name": team_name,
        "team_side": match.get("team_side") or sp.get("team_side"),
        "role": match.get("sportapi_position") or sp.get("position"),
        "lineup_status": lineup_role_label(sp),
        "matched_profile_name": match.get("matched_profile_name") or match.get("api_sports_player_name"),
        "player_profile_id": match.get("player_profile_id"),
        "api_sports_player_id": match.get("api_sports_player_id"),
        "match_score": match.get("confidence_score"),
        "match_status": rec,
        "shots_on_per90": match.get("shots_on_per90"),
        "team_sot_share": match.get("team_sot_share"),
        "shooting_impact_score": match.get("shooting_impact_score"),
        "reliability_score": match.get("reliability_score"),
        "reason": match.get("match_reason") or match.get("reason"),
    }


def compute_lineup_mapping_stats(
    sportapi_lineups: dict[str, Any],
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    starter_ids: set[int] = set()
    for side_key in ("home", "away"):
        side = sportapi_lineups.get(side_key) or {}
        for p in side.get("starters") or []:
            starter_ids.add(int(p["provider_player_id"]))

    matched_auto = 0
    matched_any = 0
    for m in matches:
        spid = int(m.get("sportapi_player_id") or 0)
        if spid not in starter_ids:
            continue
        rec = str(m.get("recommendation") or "")
        if rec in ("AUTO_SAFE", "REVIEW") and m.get("api_sports_player_id"):
            matched_any += 1
        if rec == "AUTO_SAFE" and m.get("api_sports_player_id"):
            matched_auto += 1

    total = len(starter_ids)
    rate = round(matched_auto / total, 4) if total else 0.0
    return {
        "starters_total": total,
        "starters_matched_auto_safe": matched_auto,
        "starters_matched_any": matched_any,
        "mapping_rate": rate,
    }


def build_lineup_player_mapping_debug(
    db: Session,
    fx: Fixture,
    *,
    sportapi_lineups: dict[str, Any] | None = None,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.sportapi.sportapi_lineup_present import build_sportapi_lineups_audit
    from app.services.sportapi.sportapi_player_matching_service import SportApiPlayerMatchingService

    home = db.get(Team, int(fx.home_team_id))
    away = db.get(Team, int(fx.away_team_id))
    hn = home.name if home else "Casa"
    an = away.name if away else "Trasferta"

    lineups = sportapi_lineups or build_sportapi_lineups_audit(db, int(fx.id), home_team_name=hn, away_team_name=an)
    if matches is None:
        svc = SportApiPlayerMatchingService()
        players = svc.collect_sportapi_players_from_lineups(lineups)
        for p in players:
            if not p.get("is_missing"):
                is_starter = any(
                    int(x.get("provider_player_id", -1)) == int(p["provider_player_id"])
                    for x in (lineups.get(str(p.get("team_side"))) or {}).get("starters") or []
                )
                p["_lineup_role"] = "starter" if is_starter else "bench"
        match_payload = svc.match_players_for_fixture(db, int(fx.id), sportapi_players=players)
        matches = match_payload.get("matches") or []

    _, total_profiles, team_entries = load_fixture_profiles(db, fx, home=home, away=away)
    home_count = len(team_entries.get("home") or [])
    away_count = len(team_entries.get("away") or [])

    match_by_spid = {int(m["sportapi_player_id"]): m for m in matches}
    rows: list[dict[str, Any]] = []
    matched = 0
    unmatched = 0

    svc = SportApiPlayerMatchingService()
    all_players = svc.collect_sportapi_players_from_lineups(lineups)
    for sp in all_players:
        spid = int(sp["provider_player_id"])
        side = str(sp.get("team_side") or "home")
        team_name = hn if side == "home" else an
        m = match_by_spid.get(spid) or {}
        row = build_mapping_debug_row(sp, m, team_name=team_name)
        rows.append(row)
        if str(row.get("match_status")) == "AUTO_SAFE":
            matched += 1
        elif str(row.get("match_status")) == "NO_MATCH":
            unmatched += 1

    mapping_stats = compute_lineup_mapping_stats(lineups, matches)

    return {
        "competition_id": int(fx.competition_id) if fx.competition_id is not None else None,
        "fixture_id": int(fx.id),
        "home_team": hn,
        "away_team": an,
        "lineup_players_count": len(all_players),
        "player_profiles_count": total_profiles,
        "profiles_available_home": home_count,
        "profiles_available_away": away_count,
        "matched_players": matched,
        "unmatched_players": unmatched,
        "mapping_rate": mapping_stats.get("mapping_rate"),
        "lineup_mapping_stats": mapping_stats,
        "rows": rows,
    }
