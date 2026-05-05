from __future__ import annotations

from typing import Any

from app.models import PlayerAvailabilityEvent, PlayerSotProfile

from .math_utils import cap, round2


def compute_availability_adjustment(
    *,
    top_profiles: list[PlayerSotProfile],
    availability_events: list[PlayerAvailabilityEvent],
) -> tuple[float, dict[str, Any]]:
    if not availability_events:
        return 0.0, {"status": "not_available", "availability_status": "not_available"}
    if not top_profiles:
        return 0.0, {
            "status": "not_reliable",
            "availability_status": "not_reliable",
            "reliability_note": "Nessun top player disponibile per matching affidabile.",
        }
    penalties = 0.0
    matched: list[dict[str, Any]] = []
    top_by_rank = sorted(top_profiles, key=lambda p: float(p.impact_score or 0), reverse=True)
    for ev in availability_events:
        matched_profile = None
        for idx, p in enumerate(top_by_rank[:3], start=1):
            if (ev.player_id is not None and ev.player_id == p.player_id) or (
                ev.player_name and p.player and ev.player_name.lower() in p.player.name.lower()
            ):
                matched_profile = (idx, p)
                break
        if matched_profile is None:
            continue
        rank, profile = matched_profile
        if rank == 1:
            pen = -0.35
        else:
            pen = -0.25
        penalties += pen
        matched.append(
            {
                "player_id": profile.player_id,
                "player_name": ev.player_name,
                "rank_in_top": rank,
                "penalty": pen,
            },
        )
    penalties = cap(penalties, -0.45, 0.0)
    return round2(penalties), {
        "status": "applied" if matched else "not_reliable",
        "availability_status": "available" if matched else "not_reliable",
        "unavailable_players_considered": len(availability_events),
        "matched_top_players": matched,
        "penalty": round2(penalties),
        "reliability_note": (
            "Penalità applicata solo su matching affidabile con top player."
            if matched
            else "Eventi availability presenti ma matching top player non affidabile."
        ),
    }

