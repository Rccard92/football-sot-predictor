"""Indice di Acquistabilita' V2.5 orchestratore: nessuna quota tra le feature, stima, punteggio."""

from __future__ import annotations

import numpy as np

from app.services.cecchino_v25 import orchestrator as o


def _modules():
    final = {"prob_1": 0.5, "prob_x": 0.28, "prob_2": 0.22}
    lambdas = {"ft_home": 1.6, "ft_away": 1.0, "ht_home": 0.7, "ht_away": 0.45, "reliability": 0.6}
    balance = {"pillars": {k: {"index": 50.0} for k in ("f36", "dominance", "draw_credibility", "gap_coherence")}}
    gi = {
        "pillars": {k: {"score": 60.0} for k in ("offensive_production", "defensive_solidity", "match_tempo", "offensive_stability")},
        "final_class": {"score": 55.0},
    }
    return final, lambdas, balance, gi


def test_features_never_use_book_odds():
    banned = ("book", "quota", "purchas", "buyab", "edge", "vantaggio", "rating", "fair")
    assert not [f for f in o.FEATURES if any(b in f for b in banned)]


def test_row_features_and_missing_goal_intensity():
    final, lambdas, balance, gi = _modules()
    match = o.match_features_from_modules(final=final, lambdas=lambdas, balance=balance, goal_intensity=gi)
    row = o.row_features(match, 0.5, True)
    assert row["logit_p"] == 0.0 and row["signal_active"] == 1.0 and row["gi_missing"] == 0.0
    assert row["bal_f36"] == 0.5 and row["gi_final"] == 0.55
    no_gi = o.match_features_from_modules(final=final, lambdas=lambdas, balance=balance, goal_intensity={})
    assert o.row_features(no_gi, 0.5, False)["gi_missing"] == 1.0
    no_final = o.match_features_from_modules(final={}, lambdas=lambdas, balance=balance, goal_intensity=gi)
    assert o.row_features(no_final, 0.5, False) is None


def test_fit_learns_from_results_and_roundtrip():
    rng = np.random.default_rng(1)
    n = 4000
    p = rng.uniform(0.2, 0.8, n)
    tempo = rng.uniform(0, 1, n)
    true = 1 / (1 + np.exp(-(np.log(p / (1 - p)) + 1.5 * (tempo - 0.5))))
    y = (rng.uniform(0, 1, n) < true).astype(float)
    x = rng.normal(0.3, 0.05, (n, len(o.FEATURES)))
    x[:, o.FEATURES.index("logit_p")] = np.log(p / (1 - p))
    x[:, o.FEATURES.index("gi_match_tempo")] = tempo
    x[:5, o.FEATURES.index("gi_final")] = np.nan
    model = o.fit_market_matrix("OVER_2_5", x, y)
    assert model.coef[1 + o.FEATURES.index("gi_match_tempo")] > 0.2
    again = o.MarketModel.from_dict(model.to_dict())
    assert np.allclose(again.predict_raw(x[:50]), model.predict_raw(x[:50]), atol=1e-5)


def test_score_is_module_strength_and_quota_only_decides_if_playable():
    d = o.decision(0.40, 0.27, 2.1)
    assert d["score"] == 82.5 and d["is_prediction"] and d["playable"]
    # stessa forza con quota diversa: il punteggio non cambia
    assert o.decision(0.40, 0.27, 6.0)["score"] == d["score"]
    assert o.decision(0.40, 0.27, 1.40)["playable"] is False
    assert o.decision(0.30, 0.27, 3.0)["is_prediction"] is False
    assert o.decision(0.40, 0.27, None)["playable"] is False


def test_exam_report_and_verdict():
    rng = np.random.default_rng(2)
    n = 3000
    p = rng.uniform(0.3, 0.7, n)
    y = (rng.uniform(0, 1, n) < p).astype(float)
    q = np.where(rng.uniform(0, 1, n) < 0.9, 1.0 / p * 1.02, np.nan)
    day = np.array([f"2024-01-{i % 28 + 1:02d}" for i in range(n)])
    base = np.full(n, 0.5)
    rep = o.season_report(p, np.full(n, 0.5), base, y, q, day)
    assert rep["log_loss_index"] < rep["log_loss_engine"]
    assert rep["predictions"]["lift_pt"] > 0
    assert set(rep["bands"]) == {label for label, _, _ in o.SCORE_BANDS}
    verdict = o.exam_verdict({"a": rep}, rep, o.ExamCriteria())
    assert set(verdict) == {"E1", "E2", "E3", "E4", "E5", "passed"}


def test_frozen_params_load_and_live_index_shape(monkeypatch):
    from types import SimpleNamespace

    from app.services.cecchino_v25 import orchestrator_data as od

    frozen = od.frozen_orchestrator()
    assert frozen["held_out"] == ["2025/2026"] and "2025/2026" not in frozen["trained_on"]
    assert set(frozen["_models"]) >= {"HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5"}
    final, lambdas, balance, gi = _modules()
    pre = {
        "cecchino": {"final": final},
        "goals": SimpleNamespace(lambda_home=1.6, lambda_away=1.0, ht_lambda_home=0.7, ht_lambda_away=0.45, reliability=0.6),
        "balance": balance,
        "gi": gi,
        "signal_index": {},
        "probabilities": {"HOME": 0.5, "DRAW": 0.28, "AWAY": 0.22, "OVER_2_5": 0.6},
    }
    idx = od.purchasability_index_live(pre, {"HOME": 1.9, "OVER_2_5": 1.7})
    assert idx["status"] == "ok" and set(idx["markets"]) == {"HOME", "DRAW", "AWAY", "OVER_2_5"}
    assert idx["markets"]["DRAW"]["quota"] is None and idx["markets"]["DRAW"]["playable"] is False
    assert all(idx["markets"][k]["is_prediction"] for k in idx["predictions"])
