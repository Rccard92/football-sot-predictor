from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlayerRegistry
from app.services.player_data.normalize import normalize_player_name


def upsert_player_registry(
    db: Session,
    *,
    api_player_id: int,
    name: str,
    normalized_name: str | None = None,
) -> PlayerRegistry:
    reg = db.scalar(select(PlayerRegistry).where(PlayerRegistry.api_player_id == api_player_id))
    disp = (name or "").strip() or f"Player {api_player_id}"
    norm = normalized_name if normalized_name is not None else normalize_player_name(disp)
    norm_out = norm[:255] if norm else None
    if reg is None:
        reg = PlayerRegistry(
            api_player_id=api_player_id,
            name=disp[:255],
            normalized_name=norm_out,
        )
        db.add(reg)
        db.flush()
        return reg
    reg.name = disp[:255]
    reg.normalized_name = norm_out
    return reg
