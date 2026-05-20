"""Determina se un giocatore API-Sports è ancora nella rosa attuale della squadra."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Player, PlayerTeamSeason

RosterPlayerStatus = Literal["ACTIVE", "TRANSFERRED_OUT", "NOT_IN_CURRENT_SQUAD", "UNKNOWN"]

_EXCLUSION_STATUSES = frozenset({"TRANSFERRED_OUT", "NOT_IN_CURRENT_SQUAD"})


@dataclass
class RosterStatusResult:
    status: RosterPlayerStatus
    roster_source: str | None = None
    active_on_other_team: bool = False
    other_api_team_id: int | None = None


@dataclass
class TeamRosterContext:
    season_year: int
    league_id: int
    api_team_id: int
    internal_team_id: int
    active_api_player_ids: set[int]
    all_team_rows_count: int
    has_squad_data: bool
    active_on_other_teams: dict[int, int]  # api_player_id -> other api_team_id


def _exclusion_reason_it(status: RosterPlayerStatus, *, other_team: bool = False) -> str:
    if status == "NOT_IN_CURRENT_SQUAD":
        return "Non più in rosa attuale (API-Sports)"
    if status == "TRANSFERRED_OUT":
        if other_team:
            return "Trasferito in un'altra squadra della lega"
        return "Non più in rosa attuale"
    return "Stato rosa sconosciuto"


class ActiveRosterResolver:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._context_cache: dict[tuple[int, int, int, int], TeamRosterContext] = {}

    def load_team_context(
        self,
        *,
        season_year: int,
        league_id: int,
        api_team_id: int,
        internal_team_id: int,
    ) -> TeamRosterContext:
        key = (int(season_year), int(league_id), int(api_team_id), int(internal_team_id))
        if key in self._context_cache:
            return self._context_cache[key]

        rows = list(
            self._db.scalars(
                select(PlayerTeamSeason).where(
                    PlayerTeamSeason.season == int(season_year),
                    PlayerTeamSeason.league_id == int(league_id),
                    PlayerTeamSeason.api_team_id == int(api_team_id),
                ),
            ).all(),
        )
        active_ids = {int(r.api_player_id) for r in rows if r.is_active}
        all_count = len(rows)

        other_rows = self._db.scalars(
            select(PlayerTeamSeason).where(
                PlayerTeamSeason.season == int(season_year),
                PlayerTeamSeason.league_id == int(league_id),
                PlayerTeamSeason.api_team_id != int(api_team_id),
                PlayerTeamSeason.is_active.is_(True),
            ),
        ).all()
        other_map = {int(r.api_player_id): int(r.api_team_id) for r in other_rows}

        ctx = TeamRosterContext(
            season_year=int(season_year),
            league_id=int(league_id),
            api_team_id=int(api_team_id),
            internal_team_id=int(internal_team_id),
            active_api_player_ids=active_ids,
            all_team_rows_count=all_count,
            has_squad_data=all_count > 0,
            active_on_other_teams=other_map,
        )
        self._context_cache[key] = ctx
        return ctx

    def roster_sync_hint(self, ctx: TeamRosterContext) -> str:
        if not ctx.has_squad_data:
            return "missing"
        if not ctx.active_api_player_ids:
            return "stale"
        return "ok"

    def resolve_player(
        self,
        *,
        api_player_id: int,
        ctx: TeamRosterContext,
        legacy_team_id: int | None = None,
    ) -> RosterStatusResult:
        api_pid = int(api_player_id)

        if ctx.has_squad_data:
            if api_pid in ctx.active_api_player_ids:
                return RosterStatusResult(status="ACTIVE", roster_source="player_team_seasons")
            other = ctx.active_on_other_teams.get(api_pid)
            if other is not None:
                return RosterStatusResult(
                    status="TRANSFERRED_OUT",
                    roster_source="player_team_seasons",
                    active_on_other_team=True,
                    other_api_team_id=other,
                )
            return RosterStatusResult(status="NOT_IN_CURRENT_SQUAD", roster_source="player_team_seasons")

        if legacy_team_id is not None and int(legacy_team_id) == int(ctx.internal_team_id):
            return RosterStatusResult(status="ACTIVE", roster_source="legacy_team_id")

        return RosterStatusResult(status="UNKNOWN", roster_source=None)

    def filter_top_candidates(
        self,
        *,
        candidates: list[dict[str, Any]],
        ctx: TeamRosterContext,
        top_n: int = 5,
        scan_depth: int = 20,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        candidates: dict con player_id, api_player_id, player_name, team_sot_share_pct, shots_on_target_per90, ...
        Ritorna (top_for_impact, excluded_players).
        """
        sorted_cands = sorted(
            candidates,
            key=lambda c: float(c.get("shots_on_target_per90") or 0),
            reverse=True,
        )[:scan_depth]

        excluded: list[dict[str, Any]] = []
        active_pool: list[dict[str, Any]] = []
        unknown_pool: list[dict[str, Any]] = []

        for c in sorted_cands:
            api_pid = c.get("api_player_id")
            if api_pid is None:
                continue
            res = self.resolve_player(
                api_player_id=int(api_pid),
                ctx=ctx,
                legacy_team_id=c.get("legacy_team_id"),
            )
            entry = {**c, "roster_status": res.status, "roster_source": res.roster_source}
            if res.status in _EXCLUSION_STATUSES:
                excluded.append(
                    {
                        **entry,
                        "exclusion_reason": _exclusion_reason_it(
                            res.status,
                            other_team=res.active_on_other_team,
                        ),
                    },
                )
                continue
            if res.status == "ACTIVE":
                active_pool.append(entry)
            elif res.status == "UNKNOWN":
                unknown_pool.append(entry)

        top: list[dict[str, Any]] = []
        for c in active_pool:
            if len(top) >= top_n:
                break
            top.append({**c, "included_as_unknown": False})
        if len(top) < top_n and not ctx.has_squad_data:
            for c in unknown_pool:
                if len(top) >= top_n:
                    break
                top.append({**c, "included_as_unknown": True, "roster_status": "UNKNOWN"})

        return top, excluded
