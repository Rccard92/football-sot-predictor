"""Test registro previsioni live: estrazione mercati e quote (funzioni pure)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.cecchino_live.registry import _final_score, v2_markets
from app.services.cecchino_live.v25_live import strict_quotes_from_kpi


def _row(**kw):
    base = dict(
        kpi_panel_json={"rows": [{"market_key": "HOME", "prob_cecchino": 0.41, "quota_cecchino": 2.44, "quota_book": 2.1, "rating": 55}]},
        fixture_status="FT", score_fulltime_home=2, score_fulltime_away=1, goals_home=2, goals_away=1,
        score_halftime_home=1, score_halftime_away=0, scan_date=date(2026, 9, 14),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_v2_markets_from_today_kpi():
    markets = v2_markets(_row())
    assert markets["HOME"]["probability"] == 0.41
    assert markets["HOME"]["quota_book"] == 2.1


def test_strict_quotes_mark_derived_and_skip_unknown_markets():
    kpi = {"rows": [
        {"market_key": "ONE_X", "quota_book": 1.3, "derived_quote": True},
        {"market_key": "OVER_2_5", "quota_book": 1.9},
        {"market_key": "BTTS_YES", "quota_book": 1.8},
    ]}
    quotes = strict_quotes_from_kpi(kpi)
    assert quotes["ONE_X"]["is_derived"] is True
    assert quotes["OVER_2_5"] == {"value": 1.9, "is_derived": False}
    assert "BTTS_YES" not in quotes


def test_final_score_only_when_finished():
    assert _final_score(_row()).ft_home_goals == 2
    assert _final_score(_row(fixture_status="2H")) is None
    assert _final_score(_row(score_fulltime_home=None, goals_home=None)) is None


def test_patterns_only_active_when_all_conditions_verifiable_and_true():
    from app.services.cecchino_live.pattern_signals import evaluate_patterns

    patterns = [
        {"id": 1, "target_type": "market", "target_key": "DRAW", "threshold": None, "direction": 1, "market_label": "X",
         "conditions": [{"column": "balance_f36_class", "value": "balance"}, {"column": "pre_signal_active", "value": "true"}],
         "conditions_text": "", "total_n": 100, "win_rate_pct": 30.0, "roi_pct": 8.0, "avg_quota": 3.5, "avg_deviation_pct": None},
        {"id": 2, "target_type": "market", "target_key": "DRAW", "threshold": None, "direction": 1, "market_label": "X",
         "conditions": [{"column": "home_shots_delta_class", "value": "low"}],
         "conditions_text": "", "total_n": 100, "win_rate_pct": 30.0, "roi_pct": 5.0, "avg_quota": 3.5, "avg_deviation_pct": None},
        {"id": 3, "target_type": "market", "target_key": "HOME", "threshold": None, "direction": 1, "market_label": "1",
         "conditions": [{"column": "purchasability_class", "value": "Media"}],
         "conditions_text": "", "total_n": 100, "win_rate_pct": 50.0, "roi_pct": 3.0, "avg_quota": 2.0, "avg_deviation_pct": None},
    ]
    features = {"balance_f36_class": "balance", "home_shots_delta_class": None}
    markets = {"DRAW": {"signal_active": True, "quota_book": 3.4}, "HOME": {"buyability_class": "Bassa"}}
    out = evaluate_patterns(patterns, features=features, markets=markets)
    assert [a["id"] for a in out["active"]] == [1]
    assert out["unverifiable_count"] == 1
    assert out["active"][0]["quota_book"] == 3.4
