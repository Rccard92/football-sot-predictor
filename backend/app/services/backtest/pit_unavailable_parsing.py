"""Parser condiviso indisponibili da fixture target (Step J/K/JK.1)."""

from __future__ import annotations

from typing import Any

from app.services.backtest.pit_player_rolling_stats import RawPlayerRow

_UNAVAILABLE_TOP_KEYS = ("injured", "suspended", "unavailable", "missing")
_NESTED_TEAM_KEYS = ("home", "away", "team", "teams")


def detect_raw_json_unavailable_keys(raw: Any) -> list[str]:
    """Rileva chiavi top-level o nested legate a indisponibili in un payload JSON."""
    if not isinstance(raw, dict):
        return []
    found: set[str] = set()
    for key in _UNAVAILABLE_TOP_KEYS:
        if key in raw:
            found.add(key)
    for side_key in _NESTED_TEAM_KEYS:
        block = raw.get(side_key)
        if isinstance(block, dict):
            for key in _UNAVAILABLE_TOP_KEYS:
                if key in block:
                    found.add(f"{side_key}.{key}")
        elif isinstance(block, list):
            for item in block:
                if isinstance(item, dict):
                    for key in _UNAVAILABLE_TOP_KEYS:
                        if key in item:
                            found.add(f"{side_key}[].{key}")
    return sorted(found)


def _player_row_from_item(item: dict[str, Any], *, group: str) -> RawPlayerRow | None:
    if not isinstance(item, dict):
        return None
    name = item.get("name") or item.get("player_name") or item.get("player")
    if isinstance(name, dict):
        name = name.get("name")
    pid = item.get("id") or item.get("player_id") or item.get("provider_player_id")
    pos = item.get("position") or item.get("pos")
    if name is None and pid is None:
        return None
    return RawPlayerRow(
        player_name=str(name or pid or "?"),
        provider_player_id=int(pid) if pid is not None else None,
        api_player_id=int(item["api_player_id"]) if item.get("api_player_id") is not None else None,
        position=str(pos) if pos is not None else None,
        is_starter=False,
        is_unavailable=True,
        absence_group=group,
    )


def parse_unavailable_from_payload(raw: Any) -> list[RawPlayerRow]:
    """Parse injured/suspended/unavailable espliciti da raw JSON/payload, solo fixture target."""
    if not isinstance(raw, dict):
        return []
    rows: list[RawPlayerRow] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()

    def _add(row: RawPlayerRow | None) -> None:
        if row is None:
            return
        key = (row.player_name, str(row.provider_player_id), row.absence_group)
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    for key, group in (
        ("injured", "injured"),
        ("suspended", "suspended"),
        ("unavailable", "other"),
        ("missing", "other"),
    ):
        block = raw.get(key)
        if isinstance(block, list):
            for item in block:
                _add(_player_row_from_item(item, group=group))

    for side_key in _NESTED_TEAM_KEYS:
        side_block = raw.get(side_key)
        if isinstance(side_block, dict):
            for key, group in (
                ("injured", "injured"),
                ("suspended", "suspended"),
                ("unavailable", "other"),
                ("missing", "other"),
            ):
                block = side_block.get(key)
                if isinstance(block, list):
                    for item in block:
                        _add(_player_row_from_item(item, group=group))

    return rows
