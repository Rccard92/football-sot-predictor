"""Test aggregazione overview Round Analysis."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_mode_stats import count_play_mode, reliability_score
from app.services.backtest.round_analysis_overview_aggregator import (
    build_overview_payload,
    summarize_model_from_fixtures,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _block(agg_advice: str, agg_out: str, caut_advice: str, caut_out: str) -> dict:
    return {
        "status": "ok",
        "predicted_total_sot": 10.0,
        "aggressive_advice": agg_advice,
        "aggressive_outcome": agg_out,
        "cautious_advice": caut_advice,
        "cautious_outcome": caut_out,
    }


def test_count_play_mode_advised_vs_calculated():
    block = _block("GIOCA", "WIN", "GIOCA", "LOSS")
    agg = count_play_mode(block, "aggressive")
    assert agg["advised"]["wins"] == 1
    assert agg["advised"]["plays"] == 1
    assert agg["calculated"]["plays"] == 1

    block2 = _block("NON GIOCARE", "WIN", "GIOCA", "WIN")
    agg2 = count_play_mode(block2, "aggressive")
    assert agg2["advised"]["plays"] == 0
    assert agg2["calculated"]["wins"] == 1


def test_reliability_score_weighted():
    assert reliability_score(80.0, 70.0) == round(0.65 * 80 + 0.35 * 70, 1)


def test_summarize_model_hit_rates_advised_only():
    rows = [
        {
            "status": "ok",
            "actual_total_sot": 10,
            "models_json": {
                V11: _block("GIOCA", "WIN", "GIOCA", "WIN"),
            },
        },
        {
            "status": "ok",
            "actual_total_sot": 12,
            "models_json": {
                V11: _block("NON GIOCARE", "LOSS", "GIOCA", "LOSS"),
            },
        },
    ]
    s = summarize_model_from_fixtures(V11, rows)
    assert s["cautious"]["wins"] == 1
    assert s["cautious"]["losses"] == 1
    assert s["aggressive"]["wins"] == 1
    assert s["aggressive"]["losses"] == 0


def test_build_overview_latest_version_per_round():
    a10_v1 = SimpleNamespace(
        id=1,
        round_number=10,
        analysis_version=1,
        status="completed",
        total_fixtures=2,
        processed_fixtures=2,
        model_summary_json={},
        data_quality_summary_json={"badge": "OK"},
        config_json={"models": [V11]},
    )
    a10_v2 = SimpleNamespace(
        id=2,
        round_number=10,
        analysis_version=2,
        status="completed",
        total_fixtures=2,
        processed_fixtures=2,
        model_summary_json={
            V11: {
                "cautious_wins": 2,
                "cautious_losses": 0,
                "aggressive_wins": 1,
                "aggressive_losses": 1,
                "cautious_hit_rate": 100.0,
                "aggressive_hit_rate": 50.0,
            },
        },
        data_quality_summary_json={"badge": "OK"},
        config_json={"models": [V11]},
    )
    fixtures = {
        2: [
            SimpleNamespace(
                status="ok",
                fixture_id=100,
                home_team_name="A",
                away_team_name="B",
                actual_total_sot=10,
                models_json={V11: _block("GIOCA", "WIN", "GIOCA", "WIN")},
                explanation_json={},
            ),
        ],
    }
    payload = build_overview_payload(
        competition_id=1,
        season_year=2024,
        season_label="2024/2025",
        use_latest_version_per_round=True,
        model_keys=[V11],
        analyses=[a10_v2],
        fixtures_by_analysis_id=fixtures,
    )
    assert payload["rounds_analyzed"] == 1
    assert payload["rounds"][0]["analysis_id"] == 2
    assert payload["models"][V11]["reliability_score"] is not None
