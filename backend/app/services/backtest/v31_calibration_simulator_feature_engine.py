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

LEAGUE_AVG_SOT_PER_SIDE = 3.35


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
    baseline_sot: float | None
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class FixtureSignals:
    fixture_id: int
    round_number: int
    home_team_name: str
    away_team_name: str
    home: SideSignals
    away: SideSignals
    warning_count: int
    team_stats_status: str
    missing_fields: list[str] = field(default_factory=list)
    confidence_score: float = 0.5


def _side_macros(macro_side: dict[str, Any] | None, prefix: str) -> SideSignals:
    side = macro_side if isinstance(macro_side, dict) else {}
    macros: dict[str, float | None] = {}
    missing: list[str] = []
    for key in V31_MACRO_AREA_KEYS:
        val = _f(side.get(key))
        macros[key] = val
        if val is None:
            missing.append(f"{prefix}.{key}")
    return SideSignals(macros=macros, baseline_sot=None, missing_fields=missing)


def _side_baseline(team_side: dict[str, Any] | None, macro_side: SideSignals) -> float | None:
    team = team_side if isinstance(team_side, dict) else {}
    avg = _f(team.get("avg_sot_for"))
    if avg is not None and avg > 0:
        return avg
    off = macro_side.macros.get("offensive_production_index")
    if off is not None:
        return LEAGUE_AVG_SOT_PER_SIDE * float(off)
    return None


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

    home_macros = _side_macros(
        macros_block.get("home") if isinstance(macros_block, dict) else None,
        "home",
    )
    away_macros = _side_macros(
        macros_block.get("away") if isinstance(macros_block, dict) else None,
        "away",
    )
    home_macros.baseline_sot = _side_baseline(
        team_raw.get("home") if isinstance(team_raw, dict) else None,
        home_macros,
    )
    away_macros.baseline_sot = _side_baseline(
        team_raw.get("away") if isinstance(team_raw, dict) else None,
        away_macros,
    )

    all_missing = list(dict.fromkeys(home_macros.missing_fields + away_macros.missing_fields))
    if home_macros.baseline_sot is None:
        all_missing.append("home.baseline_sot")
    if away_macros.baseline_sot is None:
        all_missing.append("away.baseline_sot")

    wc = int(dq.get("warning_count") or 0)
    ts_status = str(dq.get("team_stats_status") or "unknown")

    conf = 1.0
    if ts_status not in ("ok", "partial"):
        conf -= 0.25
    conf -= min(0.35, 0.05 * wc)
    conf -= min(0.25, 0.02 * len(all_missing))
    conf = max(0.15, min(1.0, conf))

    return FixtureSignals(
        fixture_id=fid,
        round_number=rn,
        home_team_name=str(meta.get("home_team_name") or "Casa"),
        away_team_name=str(meta.get("away_team_name") or "Trasferta"),
        home=home_macros,
        away=away_macros,
        warning_count=wc,
        team_stats_status=ts_status,
        missing_fields=all_missing,
        confidence_score=_round4(conf),
    )
