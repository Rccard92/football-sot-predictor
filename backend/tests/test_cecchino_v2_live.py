"""V2 in live per i Pattern Master V2: quote Today nelle colonne RUN V2, classi dei moduli."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.cecchino_live.v2_live import quote_match_proxy, v2_modules


def test_quote_match_proxy_fills_run_v2_columns_with_real_quotes_only():
    target = SimpleNamespace(id=5, kickoff_at=datetime(2026, 9, 15, 18, tzinfo=timezone.utc), home_team_id=1, away_team_id=2, referee="X")
    kpi = {"rows": [
        {"market_key": "HOME", "quota_book": 2.1},
        {"market_key": "OVER_2_5", "quota_book": 1.9},
        {"market_key": "ONE_X", "quota_book": 1.3, "derived_quote": True},
        {"market_key": "DRAW_PT", "quota_book": 2.2},
    ]}
    m = quote_match_proxy(target, kpi)
    assert m.bet365_home == 2.1 and m.bet365_closing_home == 2.1
    assert m.bet365_over_25 == 1.9 and m.bet365_closing_over_25 == 1.9
    assert m.bet365_ht_draw == 2.2
    assert not hasattr(m, "bet365_dc_1x")  # quota derivata: mai usata come reale


def test_v2_modules_extracts_pattern_columns():
    pre = {
        "gi": {"pillars": {"offensive_production": {"class_key": "high"}, "match_tempo": {"class_key": "low"}}, "final_class": {"key": "medium"}},
        "balance": {"pillar_classes": {"f36": "imbalance", "dominance": None}},
        "signal_index": {"HOME": {"signal_active": True}, "DRAW": {"signal_active": False}},
        "eligibility": {"status": "eligible_core"},
        "history_matches": 40,
        "gi_training": {"run_id": 8, "rows": 4400},
    }
    mods = v2_modules(pre)
    assert mods["goal_intensity_classes"] == {"offensive_production": "high", "match_tempo": "low"}
    assert mods["goal_intensity_final"] == "medium"
    assert mods["goal_intensity_pillars"]["offensive_production"]["class_key"] == "high"
    assert mods["goal_intensity_final_detail"] == {"key": "medium"}
    assert mods["balance_classes"]["f36"] == "imbalance"
    assert mods["signal_markets"] == ["HOME"]
