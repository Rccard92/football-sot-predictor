"""Provider API-Football sidelined (by player, top profiles per squadra)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models import PlayerRegistry, PlayerSeasonProfile
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

logger = logging.getLogger(__name__)

SOURCE_DETAIL_SIDELINED_PLAYER = "api_football_sidelined_player"
MAX_PLAYERS_PER_TEAM = 20
MAX_SIDELINED_API_CALLS = 100


@dataclass(frozen=True)
class SidelinedPlayerPick:
    player_id: uuid.UUID
    api_player_id: int
    player_name: str
    team_id: int | None
    api_team_id: int


def _top_players_for_team(
    db,
    *,
    season: int,
    league_id: int,
    api_team_id: int,
    limit: int = MAX_PLAYERS_PER_TEAM,
) -> list[SidelinedPlayerPick]:
    """Top profili per squadra con nome da PlayerRegistry (non PlayerSeasonProfile)."""
    rows = list(
        db.scalars(
            select(PlayerSeasonProfile)
            .join(PlayerRegistry, PlayerRegistry.id == PlayerSeasonProfile.player_id)
            .where(
                PlayerSeasonProfile.season == int(season),
                PlayerSeasonProfile.league_id == int(league_id),
                PlayerSeasonProfile.api_team_id == int(api_team_id),
            )
            .options(joinedload(PlayerSeasonProfile.registry)),
        ).all(),
    )
    eligible = [p for p in rows if _eligible_profile(p)]
    eligible.sort(key=_sort_key_profile)
    out: list[SidelinedPlayerPick] = []
    for profile in eligible:
        if len(out) >= limit:
            break
        reg = profile.registry
        api_pid = profile.api_player_id
        if api_pid is None and reg is not None:
            api_pid = reg.api_player_id
        if api_pid is None:
            continue
        name = (reg.name if reg is not None else None) or "?"
        out.append(
            SidelinedPlayerPick(
                player_id=profile.player_id,
                api_player_id=int(api_pid),
                player_name=str(name),
                team_id=int(profile.team_id) if profile.team_id is not None else None,
                api_team_id=int(api_team_id),
            ),
        )
    return out


def _team_entries(fx) -> list[tuple[int, str | None, int | None]]:
    """(api_team_id, team_name, team_internal_id) — salta team senza api_team_id."""
    out: list[tuple[int, str | None, int | None]] = []
    if fx.home_team is not None and fx.home_team.api_team_id is not None:
        out.append(
            (
                int(fx.home_team.api_team_id),
                fx.home_team.name,
                int(fx.home_team_id) if fx.home_team_id is not None else None,
            ),
        )
    if fx.away_team is not None and fx.away_team.api_team_id is not None:
        out.append(
            (
                int(fx.away_team.api_team_id),
                fx.away_team.name,
                int(fx.away_team.id) if fx.away_team.id is not None else None,
            ),
        )
    return out


class ApiFootballSidelinedProvider(AvailabilityProvider):
    name = PROVIDER_SIDELINED

    def fetch_candidates(self, ctx: ProviderContext) -> ProviderFetchResult:
        result = ProviderFetchResult(provider_name=PROVIDER_SIDELINED, called=True, status="success")
        try:
            api = ctx.api_client or ApiFootballClient()
            if not hasattr(api, "get_sidelined_by_player"):
                result.called = False
                result.status = "not_available"
                result.error = "Client API-Football senza metodo get_sidelined_by_player"
                return result

            players_checked = 0
            api_calls_cap_hit = False

            for fx in ctx.upcoming_fixtures:
                api_fx_id = int(fx.api_fixture_id)
                for api_team_id, team_name, team_internal_id in _team_entries(fx):
                    player_list = _top_players_for_team(
                        ctx.db,
                        season=int(ctx.season_year),
                        league_id=int(ctx.league_internal_id),
                        api_team_id=api_team_id,
                    )
                    for pick in player_list:
                        if result.api_calls >= MAX_SIDELINED_API_CALLS:
                            api_calls_cap_hit = True
                            break
                        players_checked += 1
                        api_pid = pick.api_player_id
                        pname = pick.player_name
                        try:
                            raw_items = api.get_sidelined_by_player(api_pid)
                            result.api_calls += 1
                            if not isinstance(raw_items, list):
                                raw_items = []
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
                        except Exception as exc:  # noqa: BLE001
                            ctx.errors.append(
                                {
                                    "provider": PROVIDER_SIDELINED,
                                    "api_player_id": api_pid,
                                    "error": "fetch_failed",
                                    "message": str(exc)[:300],
                                },
                            )
                            continue

                        try:
                            parsed_rows = parse_sidelined_entries(
                                raw_items,
                                api_player_id=api_pid,
                                player_name=pname,
                                api_team_id=api_team_id,
                                team_name=team_name,
                            )
                        except Exception as exc:  # noqa: BLE001
                            ctx.errors.append(
                                {
                                    "provider": PROVIDER_SIDELINED,
                                    "api_player_id": api_pid,
                                    "error": "parse_failed",
                                    "message": str(exc)[:300],
                                },
                            )
                            continue

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
                                    team_id=team_internal_id or pick.team_id,
                                    api_team_id=api_team_id,
                                    team_name=team_name,
                                    player_id=pick.player_id,
                                    api_player_id=api_pid,
                                    player_name=str(row.get("player_name") or pname),
                                    availability_status=str(
                                        row.get("availability_status") or "unknown",
                                    ),
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
                    if api_calls_cap_hit:
                        break
                if api_calls_cap_hit:
                    break

            result.players_checked = players_checked
            if api_calls_cap_hit:
                result.error = (
                    f"Cap API sidelined raggiunto ({MAX_SIDELINED_API_CALLS} chiamate); "
                    "ridurre fixture o usare use_sidelined=false."
                )
                logger.warning("%s %s", PROVIDER_SIDELINED, result.error)
        except Exception as exc:  # noqa: BLE001
            logger.exception("sidelined provider fatal error")
            result.status = "error"
            result.error = str(exc)[:500]
        return result
