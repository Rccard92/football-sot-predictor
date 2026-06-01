"""Helper lettura trace/macro v2.1 da explanation_json persistito (diagnostica + simulatore)."""

from __future__ import annotations

from typing import Any

SPLIT_MACRO_ALIASES = ("home_away_split", "split")

V21_MACRO_AVG_KEYS = (
    "offensive_production_avg",
    "opponent_defensive_resistance_avg",
    "split_avg",
    "recent_form_avg",
    "chance_quality_avg",
    "player_layer_avg",
    "lineups_avg",
    "injuries_unavailable_avg",
    "pace_control_avg",
    "weighted_macro_multiplier_avg",
)


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _macro_entry(side_data: dict[str, Any] | None, macro_key: str) -> dict[str, Any] | None:
    if not isinstance(side_data, dict):
        return None
    macros = side_data.get("macros")
    if not isinstance(macros, list):
        return None
    for macro in macros:
        if isinstance(macro, dict) and macro.get("key") == macro_key:
            return macro
    return None


def macro_index(
    side_data: dict[str, Any] | None,
    macro_key: str,
    *,
    aliases: tuple[str, ...] = (),
) -> float | None:
    keys = (macro_key, *aliases)
    for key in keys:
        macro = _macro_entry(side_data, key)
        if macro is not None:
            idx = macro.get("macro_index")
            return float(idx) if idx is not None else None
    return None


def macro_status(
    side_data: dict[str, Any] | None,
    macro_key: str,
    *,
    aliases: tuple[str, ...] = (),
) -> str | None:
    keys = (macro_key, *aliases)
    for key in keys:
        macro = _macro_entry(side_data, key)
        if macro is not None:
            status = macro.get("status")
            return str(status) if status is not None else None
    return None


def extract_v21_split_status(explanation_slice: dict[str, Any] | None) -> str:
    """missing | partial_low_sample | available."""
    if not isinstance(explanation_slice, dict):
        return "missing"
    statuses: list[str] = []
    for side_key in ("home", "away"):
        side = explanation_slice.get(side_key)
        if not isinstance(side, dict):
            continue
        st = macro_status(side, "home_away_split", aliases=SPLIT_MACRO_ALIASES)
        if st is not None:
            statuses.append(st)
    if not statuses:
        return "missing"
    if any(s in ("neutral_fallback", "missing", "not_built_yet") for s in statuses):
        return "missing"
    if any(s == "partial_low_sample" for s in statuses):
        return "partial_low_sample"
    if all(s == "available" for s in statuses):
        return "available"
    return "partial_low_sample"


def extract_v21_macro_averages(explanation_slice: dict[str, Any] | None) -> dict[str, float | None]:
    if not isinstance(explanation_slice, dict):
        return {k: None for k in V21_MACRO_AVG_KEYS}
    home = explanation_slice.get("home") if isinstance(explanation_slice.get("home"), dict) else {}
    away = explanation_slice.get("away") if isinstance(explanation_slice.get("away"), dict) else {}

    def _avg(macro_key: str, *, aliases: tuple[str, ...] = ()) -> float | None:
        h = macro_index(home, macro_key, aliases=aliases)
        a = macro_index(away, macro_key, aliases=aliases)
        if h is None and a is None:
            return None
        if h is None:
            return _round4(a)
        if a is None:
            return _round4(h)
        return _round4((h + a) / 2.0)

    w_home = home.get("weighted_macro_multiplier")
    w_away = away.get("weighted_macro_multiplier")
    w_avg = None
    if w_home is not None or w_away is not None:
        wh = float(w_home) if w_home is not None else None
        wa = float(w_away) if w_away is not None else None
        if wh is not None and wa is not None:
            w_avg = _round4((wh + wa) / 2.0)
        elif wh is not None:
            w_avg = _round4(wh)
        elif wa is not None:
            w_avg = _round4(wa)

    return {
        "offensive_production_avg": _avg("offensive_production"),
        "opponent_defensive_resistance_avg": _avg("opponent_defensive_resistance"),
        "split_avg": _avg("home_away_split", aliases=SPLIT_MACRO_ALIASES),
        "recent_form_avg": _avg("recent_form"),
        "chance_quality_avg": _avg("chance_quality"),
        "player_layer_avg": _avg("player_layer"),
        "lineups_avg": _avg("lineups"),
        "injuries_unavailable_avg": _avg("injuries_unavailable"),
        "pace_control_avg": _avg("pace_control"),
        "weighted_macro_multiplier_avg": w_avg,
    }


def split_status_summary(v21_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"missing": 0, "partial_low_sample": 0, "available": 0}
    seen: set[tuple[int, int]] = set()
    for row in v21_rows:
        key = (int(row["analysis_id"]), int(row["fixture_id"]))
        if key in seen:
            continue
        seen.add(key)
        expl = row.get("explanation_v21")
        status = extract_v21_split_status(expl)
        counts[status] = counts.get(status, 0) + 1
    return counts


def extract_v21_calibration_fields(explanation_slice: dict[str, Any] | None) -> dict[str, Any]:
    """Campi flat per export CSV (alias split home_away_split)."""
    if not isinstance(explanation_slice, dict):
        return {
            "actuals_used_as_input": False,
            "leakage_guard": True,
        }
    home = explanation_slice.get("home") if isinstance(explanation_slice.get("home"), dict) else {}
    away = explanation_slice.get("away") if isinstance(explanation_slice.get("away"), dict) else {}
    macro_keys = (
        "offensive_production",
        "opponent_defensive_resistance",
        "home_away_split",
        "player_layer",
        "lineups",
        "injuries_unavailable",
        "chance_quality",
        "recent_form",
        "pace_control",
    )
    out: dict[str, Any] = {
        "base_anchor_sot_home": home.get("base_anchor_sot"),
        "base_anchor_sot_away": away.get("base_anchor_sot"),
        "weighted_macro_multiplier_home": home.get("weighted_macro_multiplier"),
        "weighted_macro_multiplier_away": away.get("weighted_macro_multiplier"),
        "fallback_count": explanation_slice.get("fallback_count"),
        "source_fixture_id_lineup_home": explanation_slice.get("source_fixture_id_lineup_home"),
        "source_fixture_id_lineup_away": explanation_slice.get("source_fixture_id_lineup_away"),
        "source_fixture_id_unavailable_home": explanation_slice.get("source_fixture_id_unavailable_home"),
        "source_fixture_id_unavailable_away": explanation_slice.get("source_fixture_id_unavailable_away"),
        "leakage_guard": explanation_slice.get("leakage_guard", True),
        "actuals_used_as_input": bool(explanation_slice.get("actuals_used_as_input", False)),
        "split_status": extract_v21_split_status(explanation_slice),
    }
    field_prefix = {
        "home_away_split": "split",
        "offensive_production": "offensive_production",
        "opponent_defensive_resistance": "opponent_defensive_resistance",
        "player_layer": "player_layer",
        "lineups": "lineups",
        "injuries_unavailable": "injuries_unavailable",
        "chance_quality": "chance_quality",
        "recent_form": "recent_form",
        "pace_control": "pace_control",
    }
    for mk in macro_keys:
        prefix = field_prefix.get(mk, mk)
        aliases = SPLIT_MACRO_ALIASES if mk == "home_away_split" else ()
        out[f"{prefix}_index_home"] = macro_index(home, mk, aliases=aliases)
        out[f"{prefix}_index_away"] = macro_index(away, mk, aliases=aliases)
    return out
