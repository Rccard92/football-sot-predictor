"""Aggregazione statistiche concesse dall'avversario (partite precedenti dell'avversario)."""

from __future__ import annotations

from typing import Any

from app.models import Fixture, FixtureTeamStat

from app.services.predictions_v11.shared_stats import expected_goals_from_team_stat


def agg_conceded_by_opponent(
    *,
    fixtures: list[Fixture],
    stats_map: dict[tuple[int, int], FixtureTeamStat],
    opponent_id: int,
) -> dict[str, Any]:
    """
    Per ogni partita dell'avversario, legge le stats della squadra che ha affrontato l'avversario
  (ciò che l'avversario ha concesso in quella partita).
    """
    sot_sum = sot_n = 0
    shots_sum = shots_n = 0
    in_sum = in_n = 0
    out_sum = out_n = 0
    blocked_sum = blocked_n = 0

    for f in fixtures:
        oid = int(opponent_id)
        if int(f.home_team_id) == oid:
            other_id = int(f.away_team_id)
        elif int(f.away_team_id) == oid:
            other_id = int(f.home_team_id)
        else:
            continue

        st = stats_map.get((int(f.id), other_id))
        if st and st.shots_on_target is not None:
            sot_sum += int(st.shots_on_target)
            sot_n += 1
        if st and st.total_shots is not None:
            shots_sum += int(st.total_shots)
            shots_n += 1
        if st and st.shots_inside_box is not None:
            in_sum += int(st.shots_inside_box)
            in_n += 1
        if st and st.shots_outside_box is not None:
            out_sum += int(st.shots_outside_box)
            out_n += 1
        if st and st.blocked_shots is not None:
            blocked_sum += int(st.blocked_shots)
            blocked_n += 1

    def mean(sum_: int, n: int) -> float | None:
        return (sum_ / n) if n > 0 else None

    return {
        "matches_count": len(fixtures),
        "sot_mean": mean(sot_sum, sot_n),
        "sot_n": sot_n,
        "shots_mean": mean(shots_sum, shots_n),
        "shots_n": shots_n,
        "inside_mean": mean(in_sum, in_n),
        "inside_n": in_n,
        "outside_mean": mean(out_sum, out_n),
        "outside_n": out_n,
        "blocked_mean": mean(blocked_sum, blocked_n),
        "blocked_n": blocked_n,
    }


def agg_xg_conceded_by_opponent(
    *,
    fixtures: list[Fixture],
    stats_map: dict[tuple[int, int], FixtureTeamStat],
    opponent_id: int,
) -> dict[str, Any]:
    """Media xG prodotti dagli avversari dell'avversario (concession pool)."""
    xg_sum = 0.0
    xg_n = 0

    for f in fixtures:
        oid = int(opponent_id)
        if int(f.home_team_id) == oid:
            other_id = int(f.away_team_id)
        elif int(f.away_team_id) == oid:
            other_id = int(f.home_team_id)
        else:
            continue

        st = stats_map.get((int(f.id), other_id))
        xv, _ = expected_goals_from_team_stat(st)
        if xv is not None:
            xg_sum += float(xv)
            xg_n += 1

    def mean_xg() -> float | None:
        return (xg_sum / xg_n) if xg_n > 0 else None

    return {
        "matches_count": len(fixtures),
        "xg_mean": mean_xg(),
        "xg_n": xg_n,
    }
