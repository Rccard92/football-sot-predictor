"""Rapporti del Bet Builder (13/10/2026): fasce di quota, scalini dell'indice, mesi, mappa del valore."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.services.cecchino.cecchino_bet_builder_results import (
    OUTCOME_LOST,
    OUTCOME_WON,
    build_results_report,
    quota_band,
    roi_stats,
)


def test_quota_bands_follow_giovanni_edges():
    assert quota_band(1.40) == "sotto 1,41"
    assert quota_band(1.41) == "1,41-1,60"
    assert quota_band(1.60) == "1,41-1,60"
    assert quota_band(1.61) == "1,61-1,80"
    assert quota_band(2.00) == "1,81-2,00"
    assert quota_band(2.20) == "2,01-2,20"
    assert quota_band(2.21) == "da 2,21"


def test_roi_stats_and_interval():
    s = roi_stats([(True, 2.0), (False, 2.0), (True, 2.0), (False, 2.0)])
    assert s["plays"] == 4 and s["won"] == 2
    assert s["win_pct"] == 50.0 and s["break_even_pct"] == 50.0
    assert s["roi_pct"] == 0.0
    assert s["roi_low_pct"] < 0 < s["roi_high_pct"]
    assert roi_stats([])["roi_pct"] is None


def _entry(month: str, market: str, won: bool, quota: float, v36: float | None) -> dict:
    return {
        "match_status": "finished",
        "fixture": {"scan_date": f"{month}-10"},
        "ranked": [
            {
                "market": {"market_key": market, "label": market},
                "origin": "price",
                "prediction_outcome": OUTCOME_WON if won else OUTCOME_LOST,
                "price_value": {"quota_book": quota},
                "purchasability_v36": {"score": v36},
            }
        ],
    }


def test_report_steps_months_and_market_map():
    entries = [
        _entry("2026-09", "DRAW", True, 3.2, 40),
        _entry("2026-09", "DRAW", False, 3.0, 65),
        _entry("2026-10", "DRAW", False, 3.4, 75),
        _entry("2026-10", "HOME", True, 1.3, 80),
    ]
    rep = build_results_report(entries, match_status=None, market_key="DRAW", origin=None, min_purchasability=None)
    assert rep["summary"]["plays"] == 3
    assert [b["plays"] for b in rep["quota_bands"]] == [0, 0, 0, 0, 0, 3]
    steps = {s["step"]: s for s in rep["index_steps"]}
    assert steps["senza indice"]["plays"] == 3
    assert steps["indice da 60"]["plays"] == 2 and steps["indice da 70"]["plays"] == 1
    assert steps["senza indice"]["roi_vs_baseline_pct"] == 0.0
    assert [m["month"] for m in rep["monthly"]] == ["2026-09", "2026-10"]
    # la mappa ignora il filtro mercato: c'e' anche l'1
    assert {c["market_key"] for c in rep["market_bands"]} == {"DRAW", "HOME"}
    assert all(c["value"] is False for c in rep["market_bands"])  # campioni troppo piccoli per dire "valore"
