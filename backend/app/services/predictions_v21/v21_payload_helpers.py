"""Helper puri su payload SportAPI/refresh — nessuna dipendenza da V21SideContext."""

from __future__ import annotations

from typing import Any


def missing_ids_from_refresh_payload(payload: dict[str, Any] | None, *, side: str) -> set[int]:
    if not isinstance(payload, dict):
        return set()
    ids: set[int] = set()
    block = payload.get("missingPlayers") or payload.get("missing_players")
    if isinstance(block, list):
        for item in block:
            if isinstance(item, dict):
                player = item.get("player") if isinstance(item.get("player"), dict) else item
                if isinstance(player, dict) and player.get("id") is not None:
                    ids.add(int(player["id"]))
    side_block = payload.get(side) if isinstance(payload.get(side), dict) else None
    if isinstance(side_block, dict):
        mp = side_block.get("missing_players") or {}
        if isinstance(mp, dict):
            for grp in mp.values():
                if isinstance(grp, list):
                    for p in grp:
                        if isinstance(p, dict) and p.get("provider_player_id") is not None:
                            ids.add(int(p["provider_player_id"]))
    return ids
