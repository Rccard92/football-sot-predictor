"""Test Delta Forza / Linearità Match — Cecchino Fase 36."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_balance_analysis import build_cecchino_balance_analysis
from app.services.cecchino.cecchino_delta_force_analysis import (
    VERSION,
    build_cecchino_delta_force_analysis,
    classify_delta_forza,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME


def _kpi_panel(home_book, home_cec, draw_book, draw_cec, away_book, away_cec):
    return {
        "rows": [
            {
                "market_key": SEL_HOME,
                "segno": "1",
                "quota_book": home_book,
                "quota_cecchino": home_cec,
                "edge_pct": round((home_book / home_cec - 1) * 100, 2),
            },
            {
                "market_key": SEL_DRAW,
                "segno": "X",
                "quota_book": draw_book,
                "quota_cecchino": draw_cec,
                "edge_pct": round((draw_book / draw_cec - 1) * 100, 2),
            },
            {
                "market_key": SEL_AWAY,
                "segno": "2",
                "quota_book": away_book,
                "quota_cecchino": away_cec,
                "edge_pct": round((away_book / away_cec - 1) * 100, 2),
            },
        ]
    }


def test_delta_forza_abs_equals_abs_edge_pct():
    panel = _kpi_panel(2.40, 2.00, 3.00, 3.00, 4.00, 4.00)
    out = build_cecchino_delta_force_analysis(panel)
    home = next(r for r in out["rows"] if r["segno"] == "1")
    assert home["edge_pct"] == pytest.approx(20.0)
    assert home["delta_forza_abs"] == pytest.approx(20.0)


def test_edge_pct_positive_when_book_higher():
    panel = _kpi_panel(2.40, 2.00, 3.00, 3.00, 4.00, 4.00)
    out = build_cecchino_delta_force_analysis(panel)
    home = next(r for r in out["rows"] if r["segno"] == "1")
    assert home["edge_pct"] > 0
    assert home["direction"] == "book_higher"


def test_edge_pct_negative_when_book_lower():
    panel = _kpi_panel(1.70, 2.00, 3.00, 3.00, 4.00, 4.00)
    out = build_cecchino_delta_force_analysis(panel)
    home = next(r for r in out["rows"] if r["segno"] == "1")
    assert home["edge_pct"] == pytest.approx(-15.0)
    assert home["delta_forza_abs"] == pytest.approx(15.0)
    assert home["direction"] == "book_lower"


@pytest.mark.parametrize(
    ("delta", "class_key"),
    [
        (16.9, "linear_statistical"),
        (17.0, "non_linear"),
        (20.0, "non_linear"),
        (30.9, "non_linear"),
        (31.0, "strong_distortion"),
        (35.0, "strong_distortion"),
    ],
)
def test_classify_delta_forza_thresholds(delta, class_key):
    out = classify_delta_forza(delta)
    assert out["class_key"] == class_key


def test_match_delta_forza_abs_is_max_of_1x2():
    panel = _kpi_panel(2.10, 2.80, 3.00, 3.00, 4.20, 3.00)
    out = build_cecchino_delta_force_analysis(panel)
    assert out["status"] == "available"
    assert out["match"]["delta_forza_abs"] == pytest.approx(40.0)
    assert out["match"]["responsible_side"] == "AWAY"
    assert out["match"]["responsible_side_label"] == "2"


def test_responsible_side_tie_break_prefers_home():
    panel = _kpi_panel(2.40, 2.00, 3.60, 3.00, 4.80, 4.00)
    out = build_cecchino_delta_force_analysis(panel)
    assert out["match"]["delta_forza_abs"] == pytest.approx(20.0)
    assert out["match"]["responsible_side"] == "HOME"


def test_missing_quota_book_insufficient_data():
    panel = {
        "rows": [
            {"market_key": SEL_HOME, "segno": "1", "quota_cecchino": 2.0},
            {"market_key": SEL_DRAW, "segno": "X", "quota_book": 3.0, "quota_cecchino": 3.0},
            {"market_key": SEL_AWAY, "segno": "2", "quota_book": 4.0, "quota_cecchino": 4.0},
        ]
    }
    out = build_cecchino_delta_force_analysis(panel)
    assert out["status"] == "insufficient_data"
    assert "missing_delta_force_inputs" in out["warnings"]


def test_missing_quota_cecchino_insufficient_data():
    panel = {
        "rows": [
            {"market_key": SEL_HOME, "segno": "1", "quota_book": 2.0},
            {"market_key": SEL_DRAW, "segno": "X", "quota_book": 3.0, "quota_cecchino": 3.0},
            {"market_key": SEL_AWAY, "segno": "2", "quota_book": 4.0, "quota_cecchino": 4.0},
        ]
    }
    out = build_cecchino_delta_force_analysis(panel)
    assert out["status"] == "insufficient_data"


def test_balance_analysis_includes_delta_force_embed():
    panel = _kpi_panel(2.40, 2.00, 3.00, 3.00, 4.00, 4.00)
    delta = build_cecchino_delta_force_analysis(panel)
    balance = build_cecchino_balance_analysis(
        quota_cecchino_1=2.50,
        quota_cecchino_x=3.20,
        quota_cecchino_2=2.90,
        prob_cecchino_1=39.0,
        prob_cecchino_x=23.0,
        prob_cecchino_2=38.0,
        delta_force=delta,
    )
    assert balance["delta_force"]["match"]["delta_forza_abs"] == pytest.approx(20.0)
    assert balance["summary"]["delta_force_label"] == "Partita non statistica"


def test_balance_linear_match_flag():
    panel = _kpi_panel(2.05, 2.00, 3.05, 3.00, 4.05, 4.00)
    delta = build_cecchino_delta_force_analysis(panel)
    balance = build_cecchino_balance_analysis(
        quota_cecchino_1=2.50,
        quota_cecchino_x=3.20,
        quota_cecchino_2=2.90,
        prob_cecchino_1=31.0,
        prob_cecchino_x=42.0,
        prob_cecchino_2=27.0,
        delta_force=delta,
    )
    assert balance["summary"]["is_linear_match"] is True
    assert balance["summary"]["is_non_linear_match"] is False


def test_balance_non_linear_match_flag():
    panel = _kpi_panel(2.40, 2.00, 3.00, 3.00, 4.00, 4.00)
    delta = build_cecchino_delta_force_analysis(panel)
    balance = build_cecchino_balance_analysis(
        quota_cecchino_1=2.50,
        quota_cecchino_x=3.20,
        quota_cecchino_2=2.90,
        prob_cecchino_1=39.0,
        prob_cecchino_x=23.0,
        prob_cecchino_2=38.0,
        delta_force=delta,
    )
    assert balance["summary"]["is_non_linear_match"] is True


def test_balance_strong_distortion_flag():
    panel = _kpi_panel(2.10, 2.80, 3.00, 3.00, 4.20, 3.00)
    delta = build_cecchino_delta_force_analysis(panel)
    balance = build_cecchino_balance_analysis(
        quota_cecchino_1=2.50,
        quota_cecchino_x=3.20,
        quota_cecchino_2=2.90,
        prob_cecchino_1=39.0,
        prob_cecchino_x=23.0,
        prob_cecchino_2=38.0,
        delta_force=delta,
    )
    assert balance["summary"]["has_strong_delta_distortion"] is True


def test_version_constant():
    out = build_cecchino_delta_force_analysis(_kpi_panel(2.0, 2.0, 3.0, 3.0, 4.0, 4.0))
    assert out["version"] == VERSION
