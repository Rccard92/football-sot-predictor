"""Estrazione segnali pre-match per simulatore v3.1 (solo row.features)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

V31_MACRO_AREA_KEYS = (
    "offensive_production_index",
    "opponent_defensive_resistance_index",
    "recent_form_index",
    "chance_quality_index",
    "pace_control_index",
    "home_away_split_index",
    "player_layer_index",
    "injuries_unavailable_index",
    "lineups_index",
    "weighted_macro_multiplier",
)


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _round1(v: float) -> float:
    return round(v, 1)


def _round4(v: float) -> float:
    return round(v, 4)


@dataclass
class SideSignals:
    macros: dict[str, float | None]
    team_raw: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class FixtureSignals:
    fixture_id: int
    round_number: int
    home_team_name: str
    away_team_name: str
    home: SideSignals
    away: SideSignals
    data_quality: dict[str, Any] = field(default_factory=dict)
    league_context: dict[str, Any] = field(default_factory=dict)
    player_layer: dict[str, Any] = field(default_factory=dict)
    lineups: dict[str, Any] = field(default_factory=dict)
    warning_count: int = 0
    team_stats_status: str = "unknown"
    missing_fields: list[str] = field(default_factory=list)


def _side_macros(macro_side: dict[str, Any] | None, prefix: str) -> SideSignals:
    side = macro_side if isinstance(macro_side, dict) else {}
    macros: dict[str, float | None] = {}
    missing: list[str] = []
    for key in V31_MACRO_AREA_KEYS:
        val = _f(side.get(key))
        macros[key] = val
        if val is None:
            missing.append(f"{prefix}.{key}")
    return SideSignals(macros=macros, team_raw={}, missing_fields=missing)


def _team_raw_dict(team_side: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(team_side, dict):
        return {}
    return dict(team_side)


def extract_fixture_signals(row: dict[str, Any]) -> FixtureSignals | None:
    """Estrae segnali da row.features — non legge target né comparisons."""
    meta = row.get("metadata") or {}
    feats = row.get("features") or {}
    if not isinstance(feats, dict):
        return None

    fid = int(meta.get("fixture_id") or 0)
    rn = int(meta.get("round_number") or 0)
    macros_block = feats.get("existing_macro_features") or {}
    team_raw = feats.get("team_raw_features") or {}
    dq = feats.get("data_quality") or {}
    if not isinstance(dq, dict):
        dq = {}

    home_macros = _side_macros(
        macros_block.get("home") if isinstance(macros_block, dict) else None,
        "home",
    )
    away_macros = _side_macros(
        macros_block.get("away") if isinstance(macros_block, dict) else None,
        "away",
    )
    home_macros.team_raw = _team_raw_dict(
        team_raw.get("home") if isinstance(team_raw, dict) else None,
    )
    away_macros.team_raw = _team_raw_dict(
        team_raw.get("away") if isinstance(team_raw, dict) else None,
    )

    all_missing = list(dict.fromkeys(home_macros.missing_fields + away_macros.missing_fields))

    return FixtureSignals(
        fixture_id=fid,
        round_number=rn,
        home_team_name=str(meta.get("home_team_name") or "Casa"),
        away_team_name=str(meta.get("away_team_name") or "Trasferta"),
        home=home_macros,
        away=away_macros,
        data_quality=dq,
        league_context=feats.get("league_context") if isinstance(feats.get("league_context"), dict) else {},
        player_layer=feats.get("player_layer") if isinstance(feats.get("player_layer"), dict) else {},
        lineups=feats.get("lineups") if isinstance(feats.get("lineups"), dict) else {},
        warning_count=int(dq.get("warning_count") or 0),
        team_stats_status=str(dq.get("team_stats_status") or "unknown"),
        missing_fields=all_missing,
    )
