"""Penalità Player layer da record availability applicabili alla fixture."""

from __future__ import annotations

from typing import Any

from app.models import PlayerAvailability, PlayerSeasonProfile

UNAVAILABLE_STATUSES = frozenset(
    {"out", "injured", "suspended", "doubtful", "unavailable", "unknown"},
)

MAX_PENALTY = -0.45
PENALTY_RANK1 = -0.35
PENALTY_RANK_OTHER = -0.25


def _cap_penalty(total: float) -> float:
    if total < MAX_PENALTY:
        return MAX_PENALTY
    if total > 0.0:
        return 0.0
    return round(total, 2)


def _is_unavailable_status(status: str | None) -> bool:
    if not status:
        return False
    return status.strip().lower() in UNAVAILABLE_STATUSES


def compute_player_availability_adjustment(
    applicable_records: list[PlayerAvailability],
    top_shooter_api_ids: list[int],
    profiles_by_api: dict[int, PlayerSeasonProfile],
    *,
    fixture_id: int,
    api_fixture_id: int,
    generic_records_ignored: int = 0,
) -> tuple[float, dict[str, Any]]:
    if not applicable_records:
        return 0.0, {
            "status": "no_applicable_records_for_fixture",
            "scope": "fixture_applicable_only",
            "fixture_id": int(fixture_id),
            "api_fixture_id": int(api_fixture_id),
            "records_considered": 0,
            "generic_records_ignored": int(generic_records_ignored),
            "top_shooters_unavailable": [],
            "penalty": 0.0,
        }

    if not top_shooter_api_ids:
        return 0.0, {
            "status": "no_applicable_records_for_fixture",
            "scope": "fixture_applicable_only",
            "fixture_id": int(fixture_id),
            "api_fixture_id": int(api_fixture_id),
            "records_considered": len(applicable_records),
            "generic_records_ignored": int(generic_records_ignored),
            "top_shooters_unavailable": [],
            "penalty": 0.0,
            "note": "Nessun top shooter identificato per la squadra.",
        }

    unavailable_api_ids: set[int] = set()
    for row in applicable_records:
        if not _is_unavailable_status(row.availability_status):
            continue
        if row.api_player_id is not None:
            unavailable_api_ids.add(int(row.api_player_id))

    rank_map = {int(pid): idx + 1 for idx, pid in enumerate(top_shooter_api_ids)}
    penalties = 0.0
    matched: list[dict[str, Any]] = []

    for api_pid in top_shooter_api_ids:
        if int(api_pid) not in unavailable_api_ids:
            continue
        rank = rank_map.get(int(api_pid), 99)
        pen = PENALTY_RANK1 if rank == 1 else PENALTY_RANK_OTHER
        penalties += pen
        prof = profiles_by_api.get(int(api_pid))
        row_name = next(
            (
                r.player_name
                for r in applicable_records
                if r.api_player_id is not None and int(r.api_player_id) == int(api_pid)
            ),
            None,
        )
        matched.append(
            {
                "api_player_id": int(api_pid),
                "player_name": row_name,
                "rank_in_top": rank,
                "penalty": pen,
                "availability_status": next(
                    (
                        r.availability_status
                        for r in applicable_records
                        if r.api_player_id is not None and int(r.api_player_id) == int(api_pid)
                    ),
                    None,
                ),
            },
        )

    total = _cap_penalty(penalties)
    status = "applied" if matched else "no_applicable_records_for_fixture"

    return total, {
        "status": status,
        "scope": "fixture_applicable_only",
        "fixture_id": int(fixture_id),
        "api_fixture_id": int(api_fixture_id),
        "records_considered": len(applicable_records),
        "generic_records_ignored": int(generic_records_ignored),
        "top_shooters_unavailable": matched,
        "penalty": total,
        "matched_top_players": matched,
    }
