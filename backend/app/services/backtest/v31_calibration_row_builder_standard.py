"""Righe dataset v3.1 standard — da analisi persistite, senza rebuild PIT."""

from __future__ import annotations

from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.round_analysis_v21_trace_helpers import (
    SPLIT_MACRO_ALIASES,
    macro_index,
    macro_status,
)
from app.services.backtest.v31_calibration_feature_mappers import (
    _macro_side_from_explanation,
    map_comparisons,
    season_phase,
)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _standard_player_layer_side(expl_side: dict[str, Any] | None) -> dict[str, Any]:
    idx = _round4_macro(macro_index(expl_side, "player_layer"))
    st = macro_status(expl_side, "player_layer")
    return {
        "player_layer_index_existing": idx,
        "starting_xi_available": st in ("available", "partial_low_sample"),
        "starters_count": None,
        "avg_starter_sot_per90": None,
        "top_absent_players": [],
    }


def _standard_lineup_side(expl_side: dict[str, Any] | None) -> dict[str, Any]:
    idx = _round4_macro(macro_index(expl_side, "lineups"))
    st = macro_status(expl_side, "lineups")
    return {
        "lineup_available": st in ("available", "partial_low_sample"),
        "lineup_macro_existing": idx,
        "formation": None,
        "formation_family": None,
        "starters_count": None,
        "continuity_pct": None,
    }


def _standard_unavailable_side(expl_side: dict[str, Any] | None) -> dict[str, Any]:
    idx = _round4_macro(macro_index(expl_side, "injuries_unavailable"))
    return {
        "unavailable_macro_existing": idx,
        "important_absences_count": None,
        "unavailable_count": None,
        "top_absent_players": [],
    }


def _standard_team_side(expl_side: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "avg_sot_for": _round4_macro(macro_index(expl_side, "offensive_production")),
        "avg_sot_against": _round4_macro(macro_index(expl_side, "opponent_defensive_resistance")),
        "avg_xg_for": _round4_macro(macro_index(expl_side, "chance_quality")),
        "last5_avg_sot_for": _round4_macro(macro_index(expl_side, "recent_form")),
        "home_away_split_sot_for": _round4_macro(
            macro_index(expl_side, "home_away_split", aliases=SPLIT_MACRO_ALIASES),
        ),
        "avg_total_shots_for": _round4_macro(macro_index(expl_side, "pace_control")),
        "avg_total_shots_against": _round4_macro(
            macro_index(expl_side, "opponent_defensive_resistance"),
        ),
        "sample_count": None,
    }


def _round4_macro(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 4)


def _standard_data_quality(explanation_v21: dict[str, Any] | None) -> dict[str, Any]:
    home = (explanation_v21 or {}).get("home") if isinstance(explanation_v21, dict) else None
    away = (explanation_v21 or {}).get("away") if isinstance(explanation_v21, dict) else None
    home_d = home if isinstance(home, dict) else {}
    away_d = away if isinstance(away, dict) else {}

    def _st(side: dict[str, Any], key: str) -> str:
        s = macro_status(side, key, aliases=SPLIT_MACRO_ALIASES if key == "home_away_split" else ())
        return str(s or "missing")

    return {
        "team_stats_status": (
            "ok"
            if macro_index(home_d, "offensive_production") is not None
            and macro_index(away_d, "offensive_production") is not None
            else "partial"
        ),
        "player_layer_status": _st(home_d, "player_layer"),
        "lineup_status": _st(home_d, "lineups"),
        "unavailable_status": _st(home_d, "injuries_unavailable"),
        "split_status": _st(home_d, "home_away_split"),
        "fallback_count": 0,
        "warning_count": 0,
        "warnings": [],
        "missing_fields": [],
        "actuals_used_as_input": False,
        "leakage_guard": True,
        "source": "persisted_v21_trace",
    }


def build_standard_row(
    orm_row: Any,
    *,
    competition_id: int,
    season_year: int,
    round_number: int,
    max_round: int,
) -> dict[str, Any]:
    expl_all = dict(orm_row.explanation_json or {})
    explanation_v21 = expl_all.get(V21) if isinstance(expl_all.get(V21), dict) else None
    home_expl = (explanation_v21 or {}).get("home") if isinstance(explanation_v21, dict) else None
    away_expl = (explanation_v21 or {}).get("away") if isinstance(explanation_v21, dict) else None
    home_d = home_expl if isinstance(home_expl, dict) else {}
    away_d = away_expl if isinstance(away_expl, dict) else {}

    rn = int(round_number)
    features = {
        "team_raw_features": {
            "home": _standard_team_side(home_d),
            "away": _standard_team_side(away_d),
        },
        "player_layer": {
            "home": _standard_player_layer_side(home_d),
            "away": _standard_player_layer_side(away_d),
        },
        "lineups": {
            "home": _standard_lineup_side(home_d),
            "away": _standard_lineup_side(away_d),
        },
        "unavailable": {
            "home": _standard_unavailable_side(home_d),
            "away": _standard_unavailable_side(away_d),
        },
        "existing_macro_features": {
            "home": _macro_side_from_explanation(home_d),
            "away": _macro_side_from_explanation(away_d),
            "source": "explanation_v21_macros",
        },
        "league_context": {
            "round_number": rn,
            "season_phase": season_phase(rn, max_round),
            "season_label": season_label_from_year(int(season_year)),
        },
        "data_quality": _standard_data_quality(explanation_v21),
    }

    return {
        "metadata": {
            "fixture_id": int(orm_row.fixture_id),
            "round_number": rn,
            "home_team_name": str(orm_row.home_team_name),
            "away_team_name": str(orm_row.away_team_name),
            "competition_id": int(competition_id),
            "season_year": int(season_year),
            "mode": "historical_official_xi",
            "detail": "standard",
        },
        "target": {
            "actual_home_sot": orm_row.actual_home_sot,
            "actual_away_sot": orm_row.actual_away_sot,
            "actual_total_sot": orm_row.actual_total_sot,
            "final_score": None,
            "fixture_status": str(orm_row.status),
        },
        "features": features,
        "comparisons": map_comparisons(dict(orm_row.models_json or {})),
    }
