"""Parser indisponibili da payload lineups SportAPI (Step K.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.backtest.pit_player_rolling_stats import RawPlayerRow
from app.services.sportapi.sportapi_lineup_present import classify_missing_group
from app.services.sportapi.sportapi_payload import (
    lineups_block,
    missing_from_side,
    player_display_name,
    player_id_from_row,
    side_block,
)

NormalizedStatus = Literal["injured", "suspended", "unavailable", "doubtful", "unknown"]

_SIDE_UNAVAILABLE_KEYS: tuple[tuple[str, NormalizedStatus], ...] = (
    ("missingPlayers", "unavailable"),
    ("missing_players", "unavailable"),
    ("injured", "injured"),
    ("injuries", "injured"),
    ("suspended", "suspended"),
    ("unavailable", "unavailable"),
    ("missing", "unavailable"),
    ("absent", "unavailable"),
    ("sidelined", "unavailable"),
    ("doubts", "doubtful"),
    ("doubtful", "doubtful"),
)


@dataclass(frozen=True)
class NormalizedUnavailableRow:
    fixture_id: int
    provider_fixture_id: int
    team_id: int
    provider_team_id: int | None
    player_id: int | None
    provider_player_id: int | None
    player_name: str
    status: NormalizedStatus
    reason: str | None
    raw_status: str | None
    source_path: str
    source_provider: str = "sportapi"
    source_fixture_id: int = 0
    team_side: str = "home"
    position: str | None = None
    jersey_number: int | None = None
    description: str | None = None
    external_type: str | None = None
    expected_end_date: Any = None
    raw_json: dict[str, Any] = field(default_factory=dict)
    persistable: bool = True

    def __post_init__(self) -> None:
        if self.source_fixture_id == 0:
            object.__setattr__(self, "source_fixture_id", int(self.fixture_id))


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _normalize_status(
    *,
    hint: NormalizedStatus,
    reason: str | None,
    description: str | None,
    external_type: str | None,
) -> NormalizedStatus:
    if hint in ("injured", "suspended", "doubtful"):
        return hint
    grp = classify_missing_group(
        reason=reason,
        description=description,
        external_type=external_type,
    )
    if grp == "injured":
        return "injured"
    if grp == "suspended":
        return "suspended"
    if hint == "unavailable":
        return "unavailable"
    return "unknown"


def _player_id_from_item(item: dict[str, Any]) -> int | None:
    pid = player_id_from_row(item)
    if pid is not None:
        return pid
    return _int_or_none(item.get("id"))


def _row_from_item(
    item: dict[str, Any],
    *,
    internal_fixture_id: int,
    provider_event_id: int,
    team_id: int,
    provider_team_id: int | None,
    team_side: str,
    source_path: str,
    status_hint: NormalizedStatus,
) -> NormalizedUnavailableRow | None:
    if not isinstance(item, dict):
        return None
    pid = _player_id_from_item(item)
    name = player_display_name(item)
    reason = str(item.get("reason") or item.get("type") or "")[:64] or None
    description = str(item.get("description") or "")[:512] or None
    external_type = str(item.get("externalType") or item.get("external_type") or "")[:64] or None
    status = _normalize_status(
        hint=status_hint,
        reason=reason,
        description=description,
        external_type=external_type,
    )
    return NormalizedUnavailableRow(
        fixture_id=int(internal_fixture_id),
        provider_fixture_id=int(provider_event_id),
        team_id=int(team_id),
        provider_team_id=provider_team_id,
        player_id=None,
        provider_player_id=pid,
        player_name=name[:255],
        status=status,
        reason=reason,
        raw_status=str(item.get("reason") or item.get("type") or status_hint),
        source_path=source_path,
        source_fixture_id=int(internal_fixture_id),
        team_side=team_side,
        position=str(item.get("position") or item.get("pos") or "")[:32] or None,
        jersey_number=_int_or_none(item.get("jerseyNumber") or item.get("shirtNumber")),
        description=description,
        external_type=external_type,
        expected_end_date=item.get("expectedEndDate") or item.get("expected_end_date"),
        raw_json=dict(item),
        persistable=pid is not None,
    )


def _dedupe_key(row: NormalizedUnavailableRow) -> tuple[Any, ...]:
    if row.provider_player_id is not None:
        return (row.team_side, row.provider_player_id, row.status)
    return (row.team_side, row.player_name, row.status, row.source_path)


def _add_rows(
    out: list[NormalizedUnavailableRow],
    seen: set[tuple[Any, ...]],
    rows: list[NormalizedUnavailableRow],
) -> None:
    for row in rows:
        key = _dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)


def _parse_side_block(
    side_data: dict[str, Any],
    *,
    internal_fixture_id: int,
    provider_event_id: int,
    team_id: int,
    provider_team_id: int | None,
    team_side: str,
    path_prefix: str,
) -> list[NormalizedUnavailableRow]:
    rows: list[NormalizedUnavailableRow] = []
    for key, status_hint in _SIDE_UNAVAILABLE_KEYS:
        block = side_data.get(key)
        if not isinstance(block, list):
            continue
        for item in block:
            if not isinstance(item, dict):
                continue
            row = _row_from_item(
                item,
                internal_fixture_id=internal_fixture_id,
                provider_event_id=provider_event_id,
                team_id=team_id,
                provider_team_id=provider_team_id,
                team_side=team_side,
                source_path=f"{path_prefix}.{key}",
                status_hint=status_hint,
            )
            if row is not None:
                rows.append(row)

    for player in side_data.get("players") or []:
        if not isinstance(player, dict):
            continue
        if not (
            player.get("missing")
            or player.get("isMissing")
            or player.get("unavailable")
            or player.get("absent")
        ):
            continue
        row = _row_from_item(
            player,
            internal_fixture_id=internal_fixture_id,
            provider_event_id=provider_event_id,
            team_id=team_id,
            provider_team_id=provider_team_id,
            team_side=team_side,
            source_path=f"{path_prefix}.players[missing]",
            status_hint="unavailable",
        )
        if row is not None:
            rows.append(row)
    return rows


def parse_sportapi_unavailable_from_lineup_payload(
    payload: Any,
    *,
    internal_fixture_id: int,
    provider_event_id: int,
    home_team_id: int,
    away_team_id: int,
    provider_home_team_id: int | None,
    provider_away_team_id: int | None,
) -> list[NormalizedUnavailableRow]:
    """Estrae indisponibili da payload lineups SportAPI (multi-path, dedup)."""
    if not isinstance(payload, dict):
        return []

    lineups = lineups_block(payload)
    out: list[NormalizedUnavailableRow] = []
    seen: set[tuple[Any, ...]] = set()

    for side_key, team_id, provider_team_id in (
        ("home", home_team_id, provider_home_team_id),
        ("away", away_team_id, provider_away_team_id),
    ):
        side_data = side_block(lineups, side_key)
        if side_data:
            _add_rows(
                out,
                seen,
                _parse_side_block(
                    side_data,
                    internal_fixture_id=internal_fixture_id,
                    provider_event_id=provider_event_id,
                    team_id=team_id,
                    provider_team_id=provider_team_id,
                    team_side=side_key,
                    path_prefix=f"lineups.{side_key}",
                ),
            )

    if isinstance(payload, dict):
        for side_key, team_id, provider_team_id in (
            ("home", home_team_id, provider_home_team_id),
            ("away", away_team_id, provider_away_team_id),
        ):
            block = payload.get(side_key)
            side_from_lineups = side_block(lineups, side_key)
            if isinstance(block, dict) and block is not side_from_lineups:
                _add_rows(
                    out,
                    seen,
                    _parse_side_block(
                        block,
                        internal_fixture_id=internal_fixture_id,
                        provider_event_id=provider_event_id,
                        team_id=team_id,
                        provider_team_id=provider_team_id,
                        team_side=side_key,
                        path_prefix=f"payload.{side_key}",
                    ),
                )

    return out


def normalized_row_to_absence_group(status: NormalizedStatus) -> str:
    if status == "injured":
        return "injured"
    if status == "suspended":
        return "suspended"
    return "other"


def normalized_rows_to_raw_players(
    rows: list[NormalizedUnavailableRow],
    *,
    team_side: str | None = None,
) -> list[RawPlayerRow]:
    result: list[RawPlayerRow] = []
    for row in rows:
        if team_side is not None and row.team_side != team_side:
            continue
        result.append(
            RawPlayerRow(
                player_name=row.player_name,
                provider_player_id=row.provider_player_id,
                api_player_id=None,
                position=row.position,
                is_starter=False,
                is_unavailable=True,
                absence_group=normalized_row_to_absence_group(row.status),
            ),
        )
    return result


def collect_detected_paths(rows: list[NormalizedUnavailableRow]) -> list[str]:
    return sorted({r.source_path for r in rows})
