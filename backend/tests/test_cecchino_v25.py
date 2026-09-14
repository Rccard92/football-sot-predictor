"""Test Cecchino V2.5: correzioni dei moduli rispetto alla V2 (funzioni pure, nessun DB)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.cecchino.cecchino_engine import WDLRecord
from app.services.cecchino_data_lab.historical_context_builder import build_lab_prematch_contexts
from app.services.cecchino_v25 import scales
from app.services.cecchino_v25.balance import build_balance_v25, goal_side_difference
from app.services.cecchino_v25.goal_intensity import build_goal_intensity_v25
from app.services.cecchino_v25.goals import compute_goal_markets_v25
from app.services.cecchino_v25.kpi import build_kpi_panel_v25, fair_probabilities
from app.services.cecchino_v25.league import LeagueCounts, build_reference, counts_from_matches
from app.services.cecchino_v25.picchetti import compute_cecchino_v25, picchetto_probabilities
from app.services.cecchino_v25.purchasability import (
    PurchasabilityCalibrator,
    build_purchasability_v25,
    score_from_ev,
)
from app.services.cecchino_v25.signals import mapped_quotas

_T0 = datetime(2021, 8, 1, 15, 0)


def _match(i: int, home: int, away: int, gh: int, ga: int, hh: int | None = None, ha: int | None = None, days: int = 0):
    raw = {"score": {"halftime": {"home": hh, "away": ha} if hh is not None else {}}}
    kickoff = _T0 + timedelta(days=days)
    return SimpleNamespace(
        id=i,
        home_team_id=home,
        away_team_id=away,
        goals_home=gh,
        goals_away=ga,
        kickoff_at=kickoff,
        match_date=kickoff.date(),
        match_time=None,
        source_row_number=i,
        raw_json=raw,
    )


def _season(n_rounds: int = 12, teams: int = 6):
    """Calendario sintetico: la squadra 1 vince sempre, le altre pareggiano 1-1."""
    matches = []
    mid = 1
    day = 0
    rng = np.random.default_rng(7)
    for _ in range(n_rounds):
        for h in range(1, teams + 1):
            for a in range(1, teams + 1):
                if h == a or rng.random() > 0.35:
                    continue
                if h == 1:
                    score = (3, 0)
                elif a == 1:
                    score = (0, 2)
                else:
                    score = (1, 1)
                matches.append(_match(mid, h, a, *score, hh=score[0] // 2, ha=score[1] // 2, days=day))
                mid += 1
                day += 1
    return matches


def _reference(matches):
    return build_reference(current=counts_from_matches(matches), previous=None, global_pool=None)


def test_league_counts_under_pt_0_5_is_counted():
    matches = [_match(1, 1, 2, 1, 0, 0, 0), _match(2, 2, 1, 2, 2, 1, 0), _match(3, 1, 2, 0, 0, 0, 0)]
    counts = counts_from_matches(matches)
    assert counts.ht_n == 3
    assert counts.ht_over[0.5] == 1  # un solo primo tempo con gol: Under 0.5 PT = 2/3, non 0
    ref = build_reference(current=counts, previous=None, global_pool=None)
    assert 0.0 < 1.0 - ref.over(0.5, ht=True) < 1.0


def test_league_reference_previous_season_weight_and_fallback():
    prev = LeagueCounts()
    for i in range(300):
        prev.add_match(_match(i, 1, 2, 2, 1, 1, 0))
    ref = build_reference(current=LeagueCounts(), previous=prev, global_pool=None)
    assert "stagione_precedente" in ref.source
    assert ref.p_home == pytest.approx(1.0)
    empty = build_reference(current=LeagueCounts(), previous=None, global_pool=None)
    assert empty.source.endswith("valori_tipici")
    assert empty.p_home + empty.p_draw + empty.p_away == pytest.approx(1.0)


def test_picchetto_never_zero_and_sums_to_one():
    ref = _reference(_season())
    probs = picchetto_probabilities(WDLRecord(3, 0, 0), WDLRecord(0, 0, 3), ref)
    assert probs is not None
    assert all(p > 0 for p in probs)
    assert sum(probs) == pytest.approx(1.0)
    # con molte partite il peso del campionato diventa trascurabile
    big = picchetto_probabilities(WDLRecord(300, 0, 0), WDLRecord(0, 0, 300), ref)
    assert big[0] > 0.98


def test_final_is_weighted_mean_of_probabilities():
    matches = _season()
    target = matches[-1]
    ctx = build_lab_prematch_contexts(competition_ordered=matches, target=target)
    out = compute_cecchino_v25(ctx, _reference(matches[:-1]))
    final = out["final"]
    assert final["prob_1"] + final["prob_x"] + final["prob_2"] == pytest.approx(1.0, abs=1e-5)
    assert final["quota_1"] == pytest.approx(1.0 / final["prob_1"], rel=1e-3)
    assert len(out["picchetti"]) == 4


def test_goal_markets_complementary_and_reliability_below_one():
    matches = _season()
    target = matches[-1]
    ctx = build_lab_prematch_contexts(competition_ordered=matches, target=target)
    goals = compute_goal_markets_v25(ctx, _reference(matches[:-1]))
    for under, over in (("UNDER_2_5", "OVER_2_5"), ("UNDER_0_5", "OVER_0_5"), ("UNDER_PT_0_5", "OVER_PT_0_5")):
        assert goals.probability(under) + goals.probability(over) == pytest.approx(1.0, abs=1e-5)
    ht = sum(goals.probability(k) for k in ("HOME_PT", "DRAW_PT", "AWAY_PT"))
    assert ht == pytest.approx(1.0, abs=1e-5)
    assert 0.0 < goals.reliability < 1.0
    assert goals.lambda_home is not None and goals.lambda_home > 0


def test_fair_probabilities_and_kpi_edge():
    strict = {
        "HOME": {"value": 2.0}, "DRAW": {"value": 3.4}, "AWAY": {"value": 4.0},
        "OVER_2_5": {"value": 1.9}, "UNDER_2_5": {"value": 1.9},
    }
    fair = fair_probabilities(strict)
    assert fair["HOME"] + fair["DRAW"] + fair["AWAY"] == pytest.approx(1.0)
    assert fair["ONE_X"] == pytest.approx(fair["HOME"] + fair["DRAW"])
    assert fair["OVER_2_5"] == pytest.approx(0.5)
    panel = build_kpi_panel_v25(probabilities={"HOME": 0.55, "OVER_2_5": 0.5}, strict_by_market=strict)
    row = next(r for r in panel["rows"] if r["market_key"] == "HOME")
    assert row["edge_pct"] == pytest.approx(10.0)  # 0,55 x 2,0 - 1
    assert row["vantaggio_prob"] == pytest.approx(0.55 - fair["HOME"], abs=1e-5)


def test_percentile_score_and_mapping(monkeypatch):
    table = {"version": "t", "scales": {"a": [0.0, 1.0, 2.0, 3.0, 4.0], "b": [10.0, 20.0, 30.0, 40.0, 50.0]}}
    monkeypatch.setattr(scales, "_load", lambda: table)
    assert scales.score("a", -1) == 0.0
    assert scales.score("a", 2.0) == pytest.approx(50.0)
    assert scales.score("a", 9) == 100.0
    assert scales.map_distribution(1.5, "a", "b") == pytest.approx(25.0)
    assert scales.five_class(99.0)[0] == "very_high"
    assert scales.five_class(0.0)[0] == "very_low"
    knots = scales.quantile_knots(list(range(101)), points=4)
    assert knots == [0.0, 25.0, 50.0, 75.0, 100.0]


def test_goal_side_difference_symmetric():
    assert goal_side_difference(1.4, 1.4) == pytest.approx(0.0, abs=1e-9)
    assert goal_side_difference(2.0, 0.8) > 0
    assert goal_side_difference(0.8, 2.0) == pytest.approx(-goal_side_difference(2.0, 0.8))


def _uniform_scales(monkeypatch):
    uniform = [i / 20 for i in range(21)]
    table = {
        "version": "test",
        "scales": {
            "bal_side_gap": uniform, "bal_conviction": uniform, "bal_draw_probability": uniform,
            "bal_engine_disagreement": uniform, "gi_attack_ratio": [0.5 + i * 0.05 for i in range(21)],
            "gi_defence_ratio": [0.5 + i * 0.05 for i in range(21)], "gi_tempo_ratio": [0.5 + i * 0.05 for i in range(21)],
            "gi_scoring_consistency": [0.5 + i * 0.05 for i in range(21)], "gi_over_2_5_probability": uniform,
        },
    }
    monkeypatch.setattr(scales, "_load", lambda: table)


def test_balance_all_four_pillars_have_a_class(monkeypatch):
    _uniform_scales(monkeypatch)
    out = build_balance_v25({"prob_1": 0.5, "prob_x": 0.28, "prob_2": 0.22}, 1.6, 0.9)
    assert set(out["pillar_classes"]) == {"f36", "dominance", "draw_credibility", "gap_coherence"}
    assert all(out["pillar_classes"].values())
    assert out["pillars"]["dominance"]["direction"] == "1"


def test_goal_intensity_pillars_and_final_class(monkeypatch):
    _uniform_scales(monkeypatch)
    matches = _season()
    target = matches[-1]
    ctx = build_lab_prematch_contexts(competition_ordered=matches, target=target)
    ref = _reference(matches[:-1])
    out = build_goal_intensity_v25(ctx, ref, compute_goal_markets_v25(ctx, ref))
    assert out["status"] == "ok"
    assert set(out["pillars"]) == {"offensive_production", "defensive_solidity", "match_tempo", "offensive_stability"}
    assert out["final_class"]["key"] in {"very_low", "low", "medium", "high", "very_high"}


def test_purchasability_warmup_uses_book_and_always_scores():
    calibrator = PurchasabilityCalibrator()
    panel = {
        "rows": [
            {"market_key": "HOME", "prob_cecchino": 0.7, "prob_book_fair": 0.5, "quota_book": 1.9},
            {"market_key": "DRAW", "prob_cecchino": 0.2, "prob_book_fair": None, "quota_book": None},
        ]
    }
    out = build_purchasability_v25(kpi_panel=panel, calibrator=calibrator)
    home = out["markets"][0]
    assert home["status"] == "score" and home["class"] is not None
    assert home["corrected_probability"] == pytest.approx(0.5)  # senza storico il Cecchino non viene creduto
    assert home["expected_value"] == pytest.approx(0.5 * 1.9 - 1)
    assert out["markets"][1]["status"] == "not_calculable"
    assert score_from_ev(-1.0) == 0.0 and score_from_ev(1.0) == 100.0


def test_purchasability_learns_when_cecchino_adds_information():
    rng = np.random.default_rng(3)
    calibrator = PurchasabilityCalibrator()
    for i in range(3000):
        true_p = rng.uniform(0.2, 0.8)
        p_book = float(np.clip(true_p + rng.normal(0, 0.08), 0.05, 0.95))
        p_cec = float(np.clip(true_p + rng.normal(0, 0.03), 0.05, 0.95))
        calibrator.add(family="FT_1X2", p_book=p_book, p_cec=p_cec, won=bool(rng.random() < true_p), lab_match_id=i)
    calibrator.refresh()
    model = calibrator.model("FT_1X2")
    assert model is not None and model["c"] > 0.3
    assert calibrator.corrected_probability("FT_1X2", 0.5, 0.7) > 0.55


def test_signal_quotas_mapped_to_v2_scale(monkeypatch):
    table = {
        "version": "t",
        "scales": {
            "sig_v25_q1": [1.0, 2.0, 3.0], "sig_v2_q1": [1.0, 3.0, 5.0],
            "sig_v25_qx": [3.0, 3.5, 4.0], "sig_v2_qx": [3.0, 4.5, 6.0],
            "sig_v25_q2": [1.0, 2.0, 3.0], "sig_v2_q2": [1.0, 3.0, 5.0],
            "sig_v25_under_2_5": [1.5, 2.0, 2.5], "sig_v2_under_2_5": [1.5, 2.0, 2.5],
        },
    }
    monkeypatch.setattr(scales, "_load", lambda: table)
    mapped = mapped_quotas({"quota_1": 2.0, "quota_x": 3.5, "quota_2": 2.5}, 2.0)
    assert mapped["q1"] == pytest.approx(3.0)
    assert mapped["qx"] == pytest.approx(4.5)
    assert mapped["q2"] == pytest.approx(4.0)


def test_double_chance_fair_uses_its_own_quotes_when_complete():
    strict = {
        "HOME": {"value": 2.0}, "DRAW": {"value": 3.4}, "AWAY": {"value": 4.0},
        "ONE_X": {"value": 1.25}, "X_TWO": {"value": 1.8}, "ONE_TWO": {"value": 1.3},
    }
    fair = fair_probabilities(strict)
    assert fair["ONE_X"] + fair["X_TWO"] + fair["ONE_TWO"] == pytest.approx(2.0)
    assert fair["X_TWO"] == pytest.approx(2 * (1 / 1.8) / (1 / 1.25 + 1 / 1.8 + 1 / 1.3))
    strict["X_TWO"] = {"value": 1.8, "is_derived": True}
    derived = fair_probabilities(strict)
    assert derived["X_TWO"] == pytest.approx(derived["DRAW"] + derived["AWAY"])


def test_purchasability_never_bets_against_cecchino():
    rng = np.random.default_rng(5)
    calibrator = PurchasabilityCalibrator()
    for i in range(2000):
        true_p = rng.uniform(0.2, 0.8)
        p_book = float(np.clip(true_p + rng.normal(0, 0.02), 0.05, 0.95))
        # Cecchino rumoroso e sistematicamente sbagliato: il modello libero darebbe peso negativo
        p_cec = float(np.clip(1.0 - true_p + rng.normal(0, 0.05), 0.05, 0.95))
        calibrator.add(family="FT_1X2", p_book=p_book, p_cec=p_cec, won=bool(rng.random() < true_p), lab_match_id=i)
    calibrator.refresh()
    assert calibrator.model("FT_1X2")["c"] == 0.0
    low = calibrator.corrected_probability("FT_1X2", 0.5, 0.1)
    high = calibrator.corrected_probability("FT_1X2", 0.5, 0.9)
    assert low == pytest.approx(high)
