"""Helper source_fixture_id da trace macro PIT (Step JK.1)."""

from __future__ import annotations

from typing import Any, Protocol


class _MacroLike(Protocol):
    key: str
    source_fixture_id: int | None


class _SideTraceLike(Protocol):
    macros: list[_MacroLike]


def _macro_source_id(side_trace: _SideTraceLike | None, macro_key: str) -> int | None:
    if side_trace is None:
        return None
    for macro in side_trace.macros:
        if macro.key == macro_key:
            return macro.source_fixture_id
    return None


def extract_source_fixture_ids(
    home_trace: _SideTraceLike | None,
    away_trace: _SideTraceLike | None,
    *,
    fallback_fixture_id: int,
) -> dict[str, int | None]:
    fb = int(fallback_fixture_id)
    home_lineup = _macro_source_id(home_trace, "lineups") or fb
    away_lineup = _macro_source_id(away_trace, "lineups") or fb
    home_unavail = _macro_source_id(home_trace, "injuries_unavailable") or fb
    away_unavail = _macro_source_id(away_trace, "injuries_unavailable") or fb
    return {
        "source_fixture_id_lineup_home": home_lineup,
        "source_fixture_id_lineup_away": away_lineup,
        "source_fixture_id_unavailable_home": home_unavail,
        "source_fixture_id_unavailable_away": away_unavail,
    }


def extract_source_fixture_ids_from_traces(
    home_traces: list[dict[str, Any]] | None,
    away_traces: list[dict[str, Any]] | None,
    *,
    fallback_fixture_id: int,
) -> dict[str, int | None]:
    def _find(traces: list[dict[str, Any]] | None, key: str) -> int | None:
        if not traces:
            return None
        for t in traces:
            if t.get("key") == key:
                sid = t.get("source_fixture_id")
                return int(sid) if sid is not None else None
        return None

    fb = int(fallback_fixture_id)
    return {
        "source_fixture_id_lineup_home": _find(home_traces, "lineups") or fb,
        "source_fixture_id_lineup_away": _find(away_traces, "lineups") or fb,
        "source_fixture_id_unavailable_home": _find(home_traces, "injuries_unavailable") or fb,
        "source_fixture_id_unavailable_away": _find(away_traces, "injuries_unavailable") or fb,
    }
