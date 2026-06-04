"""Regressione quote doppia chance Cecchino nel pannello KPI."""

from __future__ import annotations

from app.services.cecchino.cecchino_kpi_panel import build_cecchino_kpi_panel


def _panel(prob_1: float, prob_x: float, prob_2: float):
    return build_cecchino_kpi_panel(
        statistical={"status": "not_available"},
        final_odds={
            "status": "available",
            "quota_1": 2.5,
            "quota_x": 3.0,
            "quota_2": 3.5,
            "prob_1": prob_1,
            "prob_x": prob_x,
            "prob_2": prob_2,
        },
        bookmaker_payload={"status": "not_available", "bookmakers": [], "bookmaker_average": {}},
    )


def test_dc_cecchino_uses_decimal_probs_not_pct_scale():
    p1, px, p2 = 0.40, 0.30, 0.30
    panel = _panel(p1, px, p2)
    rows = {r["label"]: r["cecchino"] for r in panel["rows"]}
    expected_1x = round(1.0 / (p1 + px), 2)
    expected_x2 = round(1.0 / (px + p2), 2)
    expected_12 = round(1.0 / (p1 + p2), 2)
    assert rows["1X"] == expected_1x
    assert rows["X2"] == expected_x2
    assert rows["12"] == expected_12
    assert rows["1X"] != round(100.0 / (p1 + px), 2)


def test_dc_1x_matches_excel_style():
    panel = _panel(0.416, 0.291, 0.293)
    rows = {r["label"]: r["cecchino"] for r in panel["rows"]}
    assert rows["1X"] == round(1.0 / (0.416 + 0.291), 2)
