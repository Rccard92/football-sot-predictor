"""Indice di Acquistabilita' V3 orchestratore: nessuna quota tra le feature, righe dal vivo."""

from __future__ import annotations

from app.services.cecchino_v3 import purchasability_index as v3


def _result(eligible=True):
    return {
        "eligible": eligible,
        "lambda_home": 1.5, "lambda_away": 1.1, "ht_share": 0.45, "home_evidence": 20.0, "away_evidence": 18.0,
        "probabilities": {"HOME": 0.47, "DRAW": 0.27, "AWAY": 0.26, "OVER_2_5": 0.55},
        "specialists": {
            "forza": {"home": 1.4, "away": 1.0},
            "sot": {"home": 1.5, "away": 1.1, "volume_home": 4.8, "volume_away": 3.9},
            "shots": {"home": 1.6, "away": 1.2, "volume_home": 13.0, "volume_away": 10.0},
            "form": {"goals_home": 0.1, "goals_away": -0.1, "shots_home": 0.2, "shots_away": 0.0},
            "calendar": {"rest_days_home": 6, "rest_days_away": 4, "final_phase": False},
        },
        "indices": {
            "equilibrio": {"value": 70.0, "gap_pp": 21.0, "percentile": 40.0},
            "pareggio": {"prob": 0.27, "delta_pp": 1.0, "league_draw_rate": 0.26, "percentile": 55.0},
            "intensita_goal": {"total": 2.6, "ratio": 1.02, "league_goals_avg": 2.55, "percentile": 60.0},
            "forma": {"home": {"gioco": 0.1, "risultati": 0.0}, "away": {"gioco": -0.2, "risultati": 0.1}},
        },
    }


def test_features_never_use_book_odds_or_level():
    banned = ("book", "quota", "odds", "purchas", "edge", "vantaggio", "livello", "tier", "fair")
    assert not [f for f in v3.FEATURES if any(b in f for b in banned)]


def test_row_vector_complete_and_optional_missing():
    r = _result()
    match = v3.match_features(
        lambda_home=r["lambda_home"], lambda_away=r["lambda_away"], ht_share=r["ht_share"],
        evidence_home=r["home_evidence"], evidence_away=r["away_evidence"], specialists=r["specialists"], indices=r["indices"],
    )
    vec = v3.row_vector(match, 0.5)
    assert vec is not None and len(vec) == len(v3.FEATURES) and vec[0] == 0.0
    no_idx = v3.match_features(
        lambda_home=1.5, lambda_away=1.1, ht_share=None, evidence_home=None, evidence_away=None, specialists=r["specialists"], indices={}
    )
    assert v3.row_vector(no_idx, 0.5) is not None
    assert v3.row_vector({**match, "forza_home": None}, 0.5) is None


def test_live_early_season_is_not_scored():
    assert v3.purchasability_index_live(_result(eligible=False), {})["status"] == "early_season"


def test_runner_engine_variant_uses_only_the_probability_column():
    import numpy as np

    from app.services.cecchino_v25.orchestrator_data import MarketData
    from app.services.cecchino_v25.orchestrator_runner import run_mode

    rng = np.random.default_rng(3)

    def season(n):
        p = rng.uniform(0.2, 0.8, n)
        x = rng.normal(0, 1, (n, len(v3.FEATURES)))
        x[:, 0] = np.log(p / (1 - p))
        y = (rng.uniform(0, 1, n) < p).astype(float)
        return {"HOME": MarketData(x=x, probability=p, won=y, quota=1 / p, match_id=np.arange(n), match_day=np.array(["2024-01-01"] * n))}

    data = {"2021/2022": season(800), "2022/2023": season(800), "2023/2024": season(800)}
    rep = run_mode("dev", data, features=v3.ENGINE_FEATURES, engine_features=v3.ENGINE_FEATURES, module_version="t", runs={}, data_features=v3.FEATURES)
    s = rep["seasons"]["2022/2023"]
    assert s["log_loss_index"] == s["log_loss_engine"] and rep["verdict"]["E2"] is None
    frozen = run_mode("freeze", data, features=v3.ENGINE_FEATURES, engine_features=v3.ENGINE_FEATURES, module_version="t", runs={}, data_features=v3.FEATURES)
    assert frozen["models"]["HOME"]["features"] == ["logit_p"]
