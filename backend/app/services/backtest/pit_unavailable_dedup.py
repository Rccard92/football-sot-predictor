"""Deduplica indisponibili normalizzati/raw (Step K / JK.1)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.fixture_missing_player import FixtureMissingPlayer
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.services.sportapi.sportapi_lineup_present import classify_missing_group

PROVIDER_SPORTAPI_SOURCE = PROVIDER_SPORTAPI


def normalize_player_name_for_dedup(name: str | None) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text.lower().strip())
    return text


def absence_group_for_missing_row(row: FixtureMissingPlayer) -> str:
    return classify_missing_group(
        reason=row.reason,
        description=row.description,
        external_type=row.external_type,
    )


def missing_player_dedup_key(row: FixtureMissingPlayer) -> tuple:
    side = str(row.team_side or "")
    grp = absence_group_for_missing_row(row)
    fid = int(row.fixture_id)
    provider = str(row.provider_name or PROVIDER_SPORTAPI)
    pid = row.provider_player_id
    if pid is not None:
        return (fid, side, int(pid), grp, provider)
    name = normalize_player_name_for_dedup(row.player_name)
    return (fid, side, name, grp, provider)


def raw_unavailable_dedup_key(row: Any, *, fixture_id: int) -> tuple:
    side = str(getattr(row, "team_side", "") or "")
    grp = str(getattr(row, "absence_group", None) or "other")
    pid = getattr(row, "provider_player_id", None)
    if pid is not None:
        return (int(fixture_id), side, int(pid), grp, PROVIDER_SPORTAPI)
    name = normalize_player_name_for_dedup(getattr(row, "player_name", None))
    return (int(fixture_id), side, name, grp, PROVIDER_SPORTAPI)


def dedupe_missing_player_rows(rows: list[FixtureMissingPlayer]) -> list[FixtureMissingPlayer]:
    seen: set[tuple] = set()
    out: list[FixtureMissingPlayer] = []
    for row in rows:
        key = missing_player_dedup_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def dedupe_raw_unavailable_rows(
    rows: list[Any],
    *,
    fixture_id: int,
) -> list[Any]:
    seen: set[tuple] = set()
    out: list[Any] = []
    for row in rows:
        key = raw_unavailable_dedup_key(row, fixture_id=int(fixture_id))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
