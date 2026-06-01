"""Test classificazione player layer da JSON v2.1 persistiti."""

from __future__ import annotations

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.services.backtest.player_layer_fixture_status import (
    classify_player_layer_fixture_bucket,
    extract_v21_player_layer_sides,
    summarize_player_layer_from_fixture_rows,
)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _fixture_row(home_status: str, away_status: str) -> dict:
    return {
        "status": "ok",
        "models_json": {
            V21: {
                "status": "ok",
                "trace_summary": {},
            },
        },
        "explanation_json": {
            V21: {
                "home": {
                    "macros": [{"key": "player_layer", "status": home_status}],
                },
                "away": {
                    "macros": [{"key": "player_layer", "status": away_status}],
                },
            },
        },
    }


def test_classify_ok_when_both_available():
    assert classify_player_layer_fixture_bucket("available", "available") == "ok"


def test_classify_partial_when_one_available():
    assert classify_player_layer_fixture_bucket("available", "fallback") == "partial"
    assert classify_player_layer_fixture_bucket("missing", "available") == "partial"


def test_classify_missing_when_neither_available():
    assert classify_player_layer_fixture_bucket("fallback", "neutral") == "missing"


def test_extract_from_explanation_macros():
    home, away = extract_v21_player_layer_sides(
        models_json={},
        explanation_json={
            V21: {
                "home": {"macros": [{"key": "player_layer", "status": "available"}]},
                "away": {"macros": [{"key": "player_layer", "status": "available"}]},
            },
        },
    )
    assert home == "available"
    assert away == "available"


def test_summarize_counts():
    rows = [
        _fixture_row("available", "available"),
        _fixture_row("available", "fallback"),
        _fixture_row("missing", "missing"),
    ]
    s = summarize_player_layer_from_fixture_rows(rows)
    assert s["fixtures_player_layer_ok"] == 1
    assert s["fixtures_player_layer_partial"] == 1
    assert s["fixtures_player_layer_missing"] == 1
    assert s["player_layer_sides_available"] == 3
    assert s["player_layer_sides_total"] == 6
