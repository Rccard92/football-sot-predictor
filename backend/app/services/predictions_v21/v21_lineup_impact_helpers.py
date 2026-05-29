"""Helper lineup impact leggeri per micro-variabili v2.1."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.predictions_v21.v21_feature_context import V21SideContext


def _player_name(p: dict[str, Any]) -> str:
    return str(p.get("player_name") or p.get("name") or "").strip().lower()


def starter_api_ids(ctx: V21SideContext) -> set[int]:
    ids: set[int] = set()
    for p in ctx.sportapi_side.get("starters") or []:
        if isinstance(p, dict) and p.get("provider_player_id") is not None:
            ids.add(int(p["provider_player_id"]))
    return ids


def squad_api_ids(ctx: V21SideContext) -> set[int]:
    ids = starter_api_ids(ctx)
    for p in ctx.sportapi_side.get("substitutes") or []:
        if isinstance(p, dict) and p.get("provider_player_id") is not None:
            ids.add(int(p["provider_player_id"]))
    return ids


def missing_api_ids(ctx: V21SideContext) -> set[int]:
    ids: set[int] = set()
    mp = ctx.sportapi_side.get("missing_players") or {}
    if isinstance(mp, dict):
        for grp in mp.values():
            if isinstance(grp, list):
                for p in grp:
                    if isinstance(p, dict) and p.get("provider_player_id") is not None:
                        ids.add(int(p["provider_player_id"]))
    return ids


def missing_name_set(ctx: V21SideContext) -> set[str]:
    names: set[str] = set()
    mp = ctx.sportapi_side.get("missing_players") or {}
    if isinstance(mp, dict):
        for grp in mp.values():
            if isinstance(grp, list):
                for p in grp:
                    if isinstance(p, dict):
                        n = _player_name(p)
                        if n:
                            names.add(n)
    return names


def profile_by_api_id(ctx: V21SideContext) -> dict[int, Any]:
    return {int(e.api_player_id): e for e in ctx.profile_entries}


def top_shooter_absence_score(ctx: V21SideContext, tops: list) -> float | None:
    if not tops:
        return None
    missing_ids = missing_api_ids(ctx)
    missing_names = missing_name_set(ctx)
    starters = starter_api_ids(ctx)
    lineups_ok = bool(ctx.sportapi_audit.get("available"))

    max_sot = max((float(e.shots_on_target_per90 or 0.0) for e in tops), default=0.0)
    if max_sot <= 0:
        return 0.0

    score = 0.0
    for entry in tops:
        api_id = int(entry.api_player_id)
        name = entry.name.strip().lower()
        absent = api_id in missing_ids or name in missing_names
        if not absent and lineups_ok and starters and api_id not in starters:
            absent = True
        if absent:
            weight = float(entry.shots_on_target_per90 or 0.0) / max_sot
            score += weight
    return min(1.0, round(score, 4))


def starter_vs_bench_absence_score(ctx: V21SideContext) -> float | None:
    missing_ids = missing_api_ids(ctx)
    if not missing_ids:
        return 0.0
    freq_map = ctx.lineup_history.get("starter_frequency_by_api_id") or {}
    profiles = profile_by_api_id(ctx)
    total = 0.0
    for api_id in missing_ids:
        freq = float(freq_map.get(int(api_id), 0.0))
        prof = profiles.get(int(api_id))
        impact = float(prof.shots_on_target_per90 or 0.5) if prof else 0.5
        total += freq * min(impact, 2.0)
    return min(1.0, round(total / max(len(missing_ids), 1), 4))


def important_returns_score(ctx: V21SideContext) -> tuple[float | None, str, str | None]:
    if ctx.refresh_snapshot_missing_api_ids is None:
        return None, "not_tracked_yet", "Rientri importanti non calcolabili senza storico snapshot."

    before_missing = ctx.refresh_snapshot_missing_api_ids
    if not before_missing:
        return 0.0, "available", None

    now_squad = squad_api_ids(ctx)
    profiles = profile_by_api_id(ctx)
    returned = before_missing & now_squad
    if not returned:
        return 0.0, "available", None

    max_sot = max((float(e.shots_on_target_per90 or 0.0) for e in ctx.profile_entries), default=1.0) or 1.0
    score = 0.0
    for api_id in returned:
        prof = profiles.get(int(api_id))
        impact = float(prof.shots_on_target_per90 or 0.0) / max_sot if prof else 0.3
        score += impact
    return min(1.0, round(score, 4)), "available", None
