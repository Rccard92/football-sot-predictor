"""Funzioni pure per aggregazione profili stagionali da player_match_stats."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

MINUTES_FOR_IMPACT = 180
SUBSTITUTE_NULL_THRESHOLD = 0.20

IMPACT_WEIGHTS: dict[str, float] = {
    "shots_on_per90": 0.35,
    "shots_total_per90": 0.25,
    "team_sot_share": 0.20,
    "recent_shots_on_last5": 0.10,
    "avg_rating": 0.10,
}


def is_played_minutes(minutes: int | None) -> bool:
    return minutes is not None and minutes > 0


def event_count(minutes: int | None, value: int | None) -> int | None:
    """Null evento con minuti giocati → 0; senza minuti validi → None (riga esclusa)."""
    if not is_played_minutes(minutes):
        return None
    if value is None:
        return 0
    return int(value)


def per90(total: int | float | None, minutes_total: int | float) -> float | None:
    if minutes_total <= 0 or total is None:
        return None
    return float(total) / float(minutes_total) * 90.0


def shot_accuracy(shots_on: int, shots_total: int) -> float | None:
    if shots_total <= 0:
        return None
    return float(shots_on) / float(shots_total)


def team_share(player_total: int, team_total: int) -> float | None:
    if team_total <= 0:
        return None
    return float(player_total) / float(team_total)


def recent_fixture_ids_before_latest(
    fixture_ids_chronological: list[int],
    *,
    window: int = 5,
) -> list[int]:
    """Ultime `window` fixture squadra prima dell'ultima disponibile."""
    if len(fixture_ids_chronological) <= 1:
        return []
    prior = fixture_ids_chronological[:-1]
    if not prior:
        return []
    return prior[-window:]


def substitute_null_ratio(appearances: list[bool | None]) -> float:
    if not appearances:
        return 0.0
    nulls = sum(1 for s in appearances if s is None)
    return nulls / len(appearances)


def count_starts_estimated(
    appearances: list[tuple[bool | None, int]],
    *,
    use_minutes_heuristic: bool,
) -> int:
    """Ogni appearance è (substitute, minutes)."""
    count = 0
    for sub, mins in appearances:
        if not is_played_minutes(mins):
            continue
        if use_minutes_heuristic:
            if mins >= 60:
                count += 1
        elif sub is False:
            count += 1
    return count


def min_max_normalize(value: float | None, peers: list[float | None]) -> float | None:
    if value is None:
        return None
    vals = [float(v) for v in peers if v is not None]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return 0.5
    return (float(value) - lo) / (hi - lo)


def compute_shooting_impact_score(
    *,
    minutes_total: int,
    shots_on_per90: float | None,
    shots_total_per90: float | None,
    team_sot_share: float | None,
    recent_shots_on_last5: int | None,
    avg_rating: float | None,
    peer_shots_on_per90: list[float | None],
    peer_shots_total_per90: list[float | None],
    peer_team_sot_share: list[float | None],
    peer_recent_shots_on_last5: list[int | None],
    peer_avg_rating: list[float | None],
) -> float | None:
    if minutes_total < MINUTES_FOR_IMPACT:
        return None
    if shots_on_per90 is None and shots_total_per90 is None:
        return None

    components: dict[str, float | None] = {
        "shots_on_per90": min_max_normalize(shots_on_per90, peer_shots_on_per90),
        "shots_total_per90": min_max_normalize(shots_total_per90, peer_shots_total_per90),
        "team_sot_share": min_max_normalize(team_sot_share, peer_team_sot_share),
        "recent_shots_on_last5": min_max_normalize(
            float(recent_shots_on_last5) if recent_shots_on_last5 is not None else None,
            [float(v) if v is not None else None for v in peer_recent_shots_on_last5],
        ),
        "avg_rating": min_max_normalize(avg_rating, peer_avg_rating),
    }

    weight_sum = 0.0
    score_sum = 0.0
    for key, norm in components.items():
        if norm is None:
            continue
        w = IMPACT_WEIGHTS[key]
        weight_sum += w
        score_sum += norm * w

    if weight_sum <= 0:
        return None
    return round((score_sum / weight_sum) * 100.0, 4)


def compute_reliability_score(
    *,
    minutes_total: int,
    matches_played: int,
    recent_minutes_last5: float | None,
    avg_rating: float | None,
    has_shot_data: bool,
) -> int:
    if minutes_total >= 900:
        base = 90
    elif minutes_total >= 450:
        base = 70
    elif minutes_total >= MINUTES_FOR_IMPACT:
        base = 40
    else:
        base = 12

    bonus = 0
    if matches_played >= 10:
        bonus += 3
    elif matches_played >= 5:
        bonus += 1

    if recent_minutes_last5 is not None and recent_minutes_last5 > 0:
        bonus += 3

    if avg_rating is not None:
        bonus += 2

    if has_shot_data:
        bonus += 2

    return max(0, min(100, base + bonus))


def to_decimal(value: float | None, places: int = 4) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(float(value), places)))


def to_decimal_minutes(value: float) -> Decimal:
    return Decimal(str(round(float(value), 2)))


@dataclass
class MatchRowView:
    """Vista normalizzata di una riga match per aggregazione."""

    fixture_id: int
    api_team_id: int
    api_player_id: int
    player_id: Any
    team_id: int | None
    kickoff_at: Any
    minutes: int | None
    substitute: bool | None
    rating: float | None
    shots_total: int | None
    shots_on: int | None
    goals_total: int | None
    goals_assists: int | None
    passes_key: int | None

    @property
    def played(self) -> bool:
        return is_played_minutes(self.minutes)

    def event_shots_total(self) -> int | None:
        return event_count(self.minutes, self.shots_total)

    def event_shots_on(self) -> int | None:
        return event_count(self.minutes, self.shots_on)

    def event_goals_total(self) -> int | None:
        return event_count(self.minutes, self.goals_total)

    def event_goals_assists(self) -> int | None:
        return event_count(self.minutes, self.goals_assists)

    def event_passes_key(self) -> int | None:
        return event_count(self.minutes, self.passes_key)


@dataclass
class PlayerSeasonAgg:
    api_team_id: int
    api_player_id: int
    player_id: Any
    team_id: int | None
    rows: list[MatchRowView] = field(default_factory=list)

    def played_rows(self) -> list[MatchRowView]:
        return [r for r in self.rows if r.played]

    def aggregate_base(
        self,
        recent_fixture_ids: set[int],
    ) -> dict[str, Any]:
        played = self.played_rows()
        matches_played = len(played)
        minutes_total = sum(int(r.minutes or 0) for r in played)
        minutes_avg = float(minutes_total) / matches_played if matches_played else None

        sub_appearances = [(r.substitute, int(r.minutes or 0)) for r in played]
        sub_null_ratio = substitute_null_ratio([s for s, _ in sub_appearances])
        use_heuristic = sub_null_ratio > SUBSTITUTE_NULL_THRESHOLD
        starts_estimated = count_starts_estimated(sub_appearances, use_minutes_heuristic=use_heuristic)

        shots_total = sum(r.event_shots_total() or 0 for r in played)
        shots_on = sum(r.event_shots_on() or 0 for r in played)
        goals_total = sum(r.event_goals_total() or 0 for r in played)
        assists_total = sum(r.event_goals_assists() or 0 for r in played)
        key_passes_total = sum(r.event_passes_key() or 0 for r in played)

        ratings = [float(r.rating) for r in played if r.rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        recent_rows = [r for r in played if r.fixture_id in recent_fixture_ids]
        recent_minutes = sum(int(r.minutes or 0) for r in recent_rows)
        recent_shots_total = sum(r.event_shots_total() or 0 for r in recent_rows)
        recent_shots_on = sum(r.event_shots_on() or 0 for r in recent_rows)
        recent_ratings = [float(r.rating) for r in recent_rows if r.rating is not None]
        recent_rating = sum(recent_ratings) / len(recent_ratings) if recent_ratings else None

        mt = float(minutes_total)
        sot_per90 = per90(shots_total, mt)
        son_per90 = per90(shots_on, mt)
        kp_per90 = per90(key_passes_total, mt)
        acc = shot_accuracy(shots_on, shots_total)

        return {
            "matches_played": matches_played,
            "minutes_total": minutes_total,
            "minutes_avg": minutes_avg,
            "starts_estimated": starts_estimated,
            "starts_used_minutes_heuristic": use_heuristic,
            "shots_total": shots_total,
            "shots_on": shots_on,
            "shots_total_per90": sot_per90,
            "shots_on_per90": son_per90,
            "shot_accuracy": acc,
            "goals_total": goals_total,
            "assists_total": assists_total,
            "key_passes_total": key_passes_total,
            "key_passes_per90": kp_per90,
            "avg_rating": avg_rating,
            "recent_minutes_last5": float(recent_minutes) if recent_rows else None,
            "recent_shots_total_last5": recent_shots_total if recent_rows else None,
            "recent_shots_on_last5": recent_shots_on if recent_rows else None,
            "recent_rating_last5": recent_rating,
            "has_shot_data": shots_total > 0 or shots_on > 0,
        }


def build_team_fixture_order(rows: Iterable[MatchRowView]) -> dict[int, list[int]]:
    """api_team_id -> fixture_ids ordinati per kickoff asc."""
    by_team: dict[int, dict[int, Any]] = {}
    for r in rows:
        if r.fixture_id not in by_team.setdefault(r.api_team_id, {}):
            by_team[r.api_team_id][r.fixture_id] = r.kickoff_at
    out: dict[int, list[int]] = {}
    for team_id, fx_map in by_team.items():
        ordered = sorted(fx_map.items(), key=lambda x: x[1] or "")
        out[team_id] = [fid for fid, _ in ordered]
    return out


def build_recent_windows(
    team_fixture_order: dict[int, list[int]],
    *,
    window: int = 5,
) -> dict[int, set[int]]:
    """api_team_id -> set fixture_id nella finestra recent."""
    return {
        team_id: set(recent_fixture_ids_before_latest(fids, window=window))
        for team_id, fids in team_fixture_order.items()
    }
