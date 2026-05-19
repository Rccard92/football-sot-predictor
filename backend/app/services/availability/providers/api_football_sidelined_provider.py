"""Provider API-Football sidelined (by player, top profiles per squadra)."""

from __future__ import annotations

from sqlalchemy import select

from app.models import PlayerSeasonProfile
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_helpers import _eligible_profile, _sort_key_profile
from app.services.availability.availability_sidelined_parsing import parse_sidelined_entries
from app.services.availability.providers.base import (
    SOURCE_API_FOOTBALL_SIDELINED,
    AvailabilityProvider,
    ProviderContext,
    ProviderFetchResult,
    PROVIDER_SIDELINED,
)
from app.services.availability.providers.types import NormalizedAvailabilityCandidate

SOURCE_DETAIL_SIDELINED_PLAYER = "api_football_sidelined_player"
MAX_PLAYERS_PER_TEAM = 20


def _top_api_player_ids(
    db,
    *,
    season: int,
    league_id: int,
    api_team_id: int,
    limit: int = MAX_PLAYERS_PER_TEAM,
) -> list[tuple[int, str]]:
    rows = list(
        db.scalars(
            select(PlayerSeasonProfile).where(
                PlayerSeasonProfile.season == int(season),
                PlayerSeasonProfile.league_id == int(league_id),
                PlayerSeasonProfile.api_team_id == int(api_team_id),
            ),
        ).all(),
    )
    eligible = [p for p in rows if _eligible_profile(p)]
    eligible.sort(key=_sort_key_profile)
    out: list[tuple[int, str]] = []
    for p in eligible[:limit]:
        if p.api_player_id is not None:
            out.append((int(p.api_player_id), p.player_name or "?"))
    return out


class ApiFootballSidelinedProvider(AvailabilityProvider):
    name = PROVIDER_SIDELINED

    def fetch_candidates(self, ctx: ProviderContext) -> ProviderFetchResult:
        api = ctx.api_client or ApiFootballClient()
        result = ProviderFetchResult(provider_name=PROVIDER_SIDELINED, called=True)
        players_checked = 0

        for fx in ctx.upcoming_fixtures:
            api_fx_id = int(fx.api_fixture_id)
            teams: list[tuple[int, str | None, str | None]] = []
            if fx.home_team is not None:
                teams.append(
                    (
                        int(fx.home_team.api_team_id),
                        fx.home_team.name,
                        "home",
                    ),
                )
            if fx.away_team is not None:
                teams.append(
                    (
                        int(fx.away_team.api_team_id),
                        fx.away_team.name,
                        "away",
                    ),
                )

            for api_team_id, team_name, _side in teams:
                team_internal_id = None
                if fx.home_team and int(fx.home_team.api_team_id) == api_team_id:
                    team_internal_id = int(fx.home_team_id)
                elif fx.away_team and int(fx.away_team.api_team_id) == api_team_id:
                    team_internal_id = int(fx.away_team_id)
                player_list = _top_api_player_ids(
                    ctx.db,
                    season=int(ctx.season_year),
                    league_id=int(ctx.league_internal_id),
                    api_team_id=api_team_id,
                )
                for api_pid, pname in player_list:
                    players_checked += 1
                    try:
                        raw_items = api.get_sidelined_by_player(api_pid)
                        result.api_calls += 1
                        result.raw_items_total += len(raw_items)
                    except ApiFootballError as exc:
                        ctx.errors.append(
                            {
                                "provider": PROVIDER_SIDELINED,
                                "api_player_id": api_pid,
                                "error": "api_error",
                                "message": str(exc)[:300],
                            },
                        )
                        continue

                    parsed_rows = parse_sidelined_entries(
                        raw_items,
                        api_player_id=api_pid,
                        player_name=pname,
                        api_team_id=api_team_id,
                        team_name=team_name,
                    )
                    for row in parsed_rows:
                        ko = fx.kickoff_at
                        fixture_date = ko.date() if hasattr(ko, "date") else None
                        raw = dict(row.get("raw_json") or {})
                        result.candidates.append(
                            NormalizedAvailabilityCandidate(
                                fixture_id=int(fx.id),
                                api_fixture_id=api_fx_id,
                                season=int(ctx.season_year),
                                league_id=int(ctx.league_internal_id),
                                api_league_id=int(ctx.api_league_id),
                                team_id=team_internal_id,
                                api_team_id=api_team_id,
                                team_name=team_name,
                                player_id=None,
                                api_player_id=api_pid,
                                player_name=str(row["player_name"]),
                                availability_status=str(row["availability_status"]),
                                availability_type=row.get("availability_type"),
                                reason=row.get("reason"),
                                source=SOURCE_API_FOOTBALL_SIDELINED,
                                source_detail=SOURCE_DETAIL_SIDELINED_PLAYER,
                                record_scope="provider_date_range_for_fixture",
                                confidence="LOW",
                                applicability_status="candidate",
                                applicability_reason=None,
                                start_date=row.get("start_date"),
                                end_date=row.get("end_date"),
                                fixture_date=fixture_date,
                                raw_json=raw,
                            ),
                        )

        result.players_checked = players_checked
        return result
