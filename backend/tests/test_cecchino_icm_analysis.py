"""Test Indice di Convergenza Match (ICM) — Cecchino Fase 41."""

from __future__ import annotations

import importlib
import inspect

import pytest

from app.services.cecchino.cecchino_balance_analysis import build_cecchino_balance_analysis
from app.services.cecchino.cecchino_icm_analysis import (
    VERSION,
    _ambiguity_penalty,
    _classify_icm,
    build_cecchino_icm_analysis,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)


def _balance(**kwargs) -> dict:
    defaults = {
        "quota_cecchino_1": 2.50,
        "quota_cecchino_x": 3.20,
        "quota_cecchino_2": 2.90,
        "prob_cecchino_1": 31.0,
        "prob_cecchino_x": 42.0,
        "prob_cecchino_2": 27.0,
    }
    defaults.update(kwargs)
    return build_cecchino_balance_analysis(**defaults)


def _kpi_rows(*rows: dict) -> dict:
    return {"rows": list(rows)}


def _under_kpi() -> dict:
    return _kpi_rows(
        {"market_key": SEL_HOME, "rating": 40, "vantaggio_prob": -0.02},
        {"market_key": SEL_DRAW, "rating": 50, "vantaggio_prob": 0.01},
        {"market_key": SEL_AWAY, "rating": 35, "vantaggio_prob": -0.01},
        {"market_key": SEL_UNDER_2_5, "rating": 70, "vantaggio_prob": 0.04},
        {"market_key": SEL_UNDER_3_5, "rating": 65, "vantaggio_prob": 0.03},
        {"market_key": SEL_OVER_2_5, "rating": 30, "vantaggio_prob": -0.05},
        {"market_key": SEL_OVER_1_5, "rating": 35, "vantaggio_prob": -0.02},
    )


def _draw_kpi() -> dict:
    return _kpi_rows(
        {"market_key": SEL_HOME, "rating": 35, "vantaggio_prob": -0.02},
        {"market_key": SEL_DRAW, "rating": 65, "vantaggio_prob": 0.03},
        {"market_key": SEL_AWAY, "rating": 30, "vantaggio_prob": -0.01},
        {"market_key": SEL_ONE_X, "rating": 45, "vantaggio_prob": 0.01},
        {"market_key": SEL_X_TWO, "rating": 40, "vantaggio_prob": 0.0},
    )


def _home_imbalance_kpi() -> dict:
    return _kpi_rows(
        {"market_key": SEL_HOME, "rating": 70, "vantaggio_prob": 0.05},
        {"market_key": SEL_DRAW, "rating": 30, "vantaggio_prob": -0.04},
        {"market_key": SEL_AWAY, "rating": 25, "vantaggio_prob": -0.03},
        {"market_key": SEL_ONE_X, "rating": 55, "vantaggio_prob": 0.02},
    )


def _away_imbalance_kpi() -> dict:
    return _kpi_rows(
        {"market_key": SEL_HOME, "rating": 25, "vantaggio_prob": -0.03},
        {"market_key": SEL_DRAW, "rating": 30, "vantaggio_prob": -0.02},
        {"market_key": SEL_AWAY, "rating": 72, "vantaggio_prob": 0.06},
        {"market_key": SEL_X_TWO, "rating": 58, "vantaggio_prob": 0.02},
    )


def _over_imbalance_kpi() -> dict:
    return _kpi_rows(
        {"market_key": SEL_HOME, "rating": 45, "vantaggio_prob": 0.01},
        {"market_key": SEL_DRAW, "rating": 25, "vantaggio_prob": -0.03},
        {"market_key": SEL_AWAY, "rating": 40, "vantaggio_prob": 0.0},
        {"market_key": SEL_OVER_2_5, "rating": 68, "vantaggio_prob": 0.04},
        {"market_key": SEL_OVER_1_5, "rating": 62, "vantaggio_prob": 0.03},
        {"market_key": SEL_UNDER_2_5, "rating": 28, "vantaggio_prob": -0.04},
        {"market_key": SEL_UNDER_3_5, "rating": 30, "vantaggio_prob": -0.03},
    )


@pytest.mark.parametrize(
    ("score", "class_key"),
    [
        (15, "contradictory"),
        (35, "weak_convergence"),
        (55, "moderate_convergence"),
        (75, "strong_convergence"),
        (92, "total_convergence"),
    ],
)
def test_classify_icm_bands(score: int, class_key: str):
    out = _classify_icm(score)
    assert out["class_key"] == class_key


@pytest.mark.parametrize(
    ("gap", "penalty"),
    [(20, 0), (15, 5), (7, 10), (3, 20)],
)
def test_ambiguity_penalty(gap: float, penalty: int):
    assert _ambiguity_penalty(gap) == penalty


def test_balance_under_narrative():
    balance = _balance(
        quota_cecchino_1=2.50,
        quota_cecchino_2=2.90,
        prob_cecchino_1=31.0,
        prob_cecchino_x=42.0,
        prob_cecchino_2=27.0,
    )
    out = build_cecchino_icm_analysis(balance_analysis=balance, kpi_panel=_under_kpi())
    assert out["status"] == "available"
    assert out["dominant_narrative"]["key"] == "balance_under"
    assert out["score"] is not None
    assert 0 <= out["score"] <= 100


def test_balance_draw_narrative():
    balance = _balance(
        quota_cecchino_1=2.55,
        quota_cecchino_2=2.85,
        quota_cecchino_x=3.10,
        prob_cecchino_1=30.0,
        prob_cecchino_x=45.0,
        prob_cecchino_2=25.0,
    )
    out = build_cecchino_icm_analysis(balance_analysis=balance, kpi_panel=_draw_kpi())
    assert out["dominant_narrative"]["key"] == "balance_draw"


def test_imbalance_home_narrative():
    balance = _balance(
        quota_cecchino_1=2.20,
        quota_cecchino_2=4.50,
        quota_cecchino_x=3.80,
        prob_cecchino_1=48.0,
        prob_cecchino_x=18.0,
        prob_cecchino_2=34.0,
    )
    out = build_cecchino_icm_analysis(balance_analysis=balance, kpi_panel=_home_imbalance_kpi())
    assert out["dominant_narrative"]["key"] == "imbalance_home"


def test_imbalance_away_narrative():
    balance = _balance(
        quota_cecchino_1=4.50,
        quota_cecchino_2=2.20,
        quota_cecchino_x=3.80,
        prob_cecchino_1=28.0,
        prob_cecchino_x=16.0,
        prob_cecchino_2=52.0,
    )
    out = build_cecchino_icm_analysis(balance_analysis=balance, kpi_panel=_away_imbalance_kpi())
    assert out["dominant_narrative"]["key"] == "imbalance_away"


def test_imbalance_over_narrative():
    balance = _balance(
        quota_cecchino_1=2.10,
        quota_cecchino_2=5.00,
        quota_cecchino_x=3.90,
        prob_cecchino_1=46.0,
        prob_cecchino_x=14.0,
        prob_cecchino_2=40.0,
    )
    out = build_cecchino_icm_analysis(balance_analysis=balance, kpi_panel=_over_imbalance_kpi())
    assert out["dominant_narrative"]["key"] == "imbalance_over"


def test_contradictory_markets_forced_on_low_gap():
    balance = _balance(
        quota_cecchino_1=2.55,
        quota_cecchino_2=2.85,
        quota_cecchino_x=3.15,
        prob_cecchino_1=33.0,
        prob_cecchino_x=34.0,
        prob_cecchino_2=33.0,
    )
    kpi = _kpi_rows(
        {"market_key": SEL_HOME, "rating": 55, "vantaggio_prob": 0.01},
        {"market_key": SEL_DRAW, "rating": 54, "vantaggio_prob": 0.01},
        {"market_key": SEL_AWAY, "rating": 53, "vantaggio_prob": 0.01},
        {"market_key": SEL_UNDER_2_5, "rating": 52, "vantaggio_prob": 0.01},
        {"market_key": SEL_OVER_2_5, "rating": 51, "vantaggio_prob": 0.01},
    )
    out = build_cecchino_icm_analysis(balance_analysis=balance, kpi_panel=kpi)
    assert out["dominant_narrative"]["key"] == "contradictory_markets"
    assert out["class_key"] in ("contradictory", "weak_convergence")


def test_driver_statuses_present():
    balance = _balance()
    out = build_cecchino_icm_analysis(balance_analysis=balance, kpi_panel=_under_kpi())
    assert len(out["drivers"]) == 5
    symbols = {d["symbol"] for d in out["drivers"]}
    assert symbols.issubset({"✓", "~", "✗"})


def test_insufficient_data_without_balance():
    out = build_cecchino_icm_analysis(balance_analysis=None, kpi_panel=_under_kpi())
    assert out["status"] == "insufficient_data"
    assert out["score"] is None
    assert "missing_icm_inputs" in out["warnings"]


def test_icm_does_not_import_delta_force_module():
    mod = importlib.import_module("app.services.cecchino.cecchino_icm_analysis")
    source = inspect.getsource(mod)
    assert "cecchino_delta_force_analysis" not in source


def test_version_constant():
    out = build_cecchino_icm_analysis(balance_analysis=_balance(), kpi_panel=_under_kpi())
    assert out["version"] == VERSION
    assert out["composition"] is not None
    assert len(out["composition"]) == 5


def test_detail_payload_includes_icm_analysis():
    from datetime import date
    from unittest.mock import MagicMock, patch

    from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
    from app.services.cecchino.cecchino_today_service import get_today_fixture_detail

    row = MagicMock()
    row.id = 99
    row.provider_fixture_id = 1001
    row.local_fixture_id = 50
    row.competition_id = 5
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    row.scan_date = date(2026, 6, 9)
    row.country_name = "IT"
    row.league_name = "Serie A"
    row.home_team_name = "Home"
    row.away_team_name = "Away"
    row.kickoff = None
    row.fixture_status = "NS"
    row.odds_snapshot_json = {}
    row.stats_snapshot_json = {}
    row.warnings_json = []
    row.cecchino_output_json = {
        "final": {
            "status": "available",
            "quota_1": 2.50,
            "quota_x": 3.20,
            "quota_2": 2.90,
            "prob_1": 31.0,
            "prob_x": 42.0,
            "prob_2": 27.0,
        },
        "signals_matrix": {"status": "available", "rows": []},
    }

    db = MagicMock()
    db.get.return_value = row
    with (
        patch(
            "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
            return_value=_under_kpi(),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations",
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.build_expected_goal_engine_diagnostics_for_today_row",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
            return_value={"status": "unavailable", "error": "bundle_missing"},
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail",
            return_value={},
        ),
    ):
        detail = get_today_fixture_detail(db, 99)

    assert detail is not None
    assert "icm_analysis" in detail
    assert detail["icm_analysis"]["status"] == "available"
    assert "delta_force_analysis" not in detail
    assert "balance_v5" in detail
    assert "balance_v5_preview" not in detail
