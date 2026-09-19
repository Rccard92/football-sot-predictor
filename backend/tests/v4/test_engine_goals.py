"""Motore gol V4: forma del payload, coerenza delle probabilita', handicap,
calibrazione nel rodaggio, incertezza, live senza fughe. Storico sintetico
piccolo (una piramide a due divisioni, tre stagioni) per test rapidi."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

import numpy as np
import pytest

from app.services.cecchino_v3.constants import DEFAULT_HYPER, MARKET_KEYS, group_of
from app.services.cecchino_v3.data import MatchRecord, annotate_season_context
from app.services.cecchino_v3.markets import market_probabilities

from app.services.cecchino_v4.constants import AH_LINES, CLASSIC_MARKETS, MARKET_FAMILY
from app.services.cecchino_v4.engine_goals import additions, distributions
from app.services.cecchino_v4.engine_goals.baseline_v3 import run_v3_phase4_full
from app.services.cecchino_v4.engine_goals.config import (
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    LEVELS,
    V4GoalsConfig,
    adopted_config,
)
from app.services.cecchino_v4.engine_goals.engine import predict_history_full
from app.services.cecchino_v4.engine_goals.live import TargetMatch, fit_live_artifacts, predict_targets
from app.services.cecchino_v4.history.football_data import History

_EPOCH = date(2000, 1, 1)
SEASONS = ("2021/2022", "2022/2023", "2023/2024")
DIV_A, DIV_B = "Serie A", "Serie B"  # piramide "italy" della V3


def _make_history(seed: int = 7, teams_per_division: int = 6) -> History:
    """Doppio girone per divisione e stagione, gol Poisson da forze fisse; una
    squadra promossa/retrocessa ogni stagione. ~ 3 x 2 x 30 = 180 partite."""
    rng = random.Random(seed)
    teams_a = [f"A{i}" for i in range(teams_per_division)]
    teams_b = [f"B{i}" for i in range(teams_per_division)]
    strength = {t: rng.gauss(0.0, 0.25) for t in teams_a + teams_b}
    matches: list[MatchRecord] = []
    mid = 1
    for s_idx, season in enumerate(SEASONS):
        if s_idx > 0:  # scambio tra le divisioni
            teams_a[-1], teams_b[0] = teams_b[0], teams_a[-1]
        start = date(2021 + s_idx, 8, 15)
        for comp, teams, level in ((DIV_A, teams_a, 0.3), (DIV_B, teams_b, 0.1)):
            pairs = [(h, a) for h in teams for a in teams if h != a]
            rng.shuffle(pairs)
            per_round = len(teams) // 2
            for k, (h, a) in enumerate(pairs):
                d = start + timedelta(days=7 * (k // per_round))
                lam_h = math.exp(level + 0.2 + strength[h] - strength[a])
                lam_a = math.exp(level + strength[a] - strength[h])
                fh = np.random.default_rng(mid).poisson(lam_h)
                fa = np.random.default_rng(mid + 100000).poisson(lam_a)
                matches.append(
                    MatchRecord(
                        lab_match_id=mid,
                        competition=comp,
                        group=group_of(comp),
                        season_label=season,
                        match_date=d,
                        kickoff_at=None,
                        day=(d - _EPOCH).days,
                        home_team=h,
                        away_team=a,
                        ft_home=int(fh),
                        ft_away=int(fa),
                        ht_home=int(fh // 2),
                        ht_away=int(fa // 2),
                        home_shots=int(8 + 4 * lam_h + rng.randint(0, 4)),
                        away_shots=int(8 + 4 * lam_a + rng.randint(0, 4)),
                        home_sot=int(2 + 2 * lam_h + rng.randint(0, 2)),
                        away_sot=int(2 + 2 * lam_a + rng.randint(0, 2)),
                    )
                )
                mid += 1
    matches.sort(key=lambda m: (m.day, m.lab_match_id))
    annotate_season_context(matches)
    return History(matches=matches, extras={})


FULL = V4GoalsConfig(
    team_home_advantage=True,
    division_rho=True,
    division_dispersion=True,
    uncertainty=True,
    isotonic_calibration=True,
)


@pytest.fixture(scope="module")
def history() -> History:
    return _make_history()


@pytest.fixture(scope="module")
def baseline(history):
    return run_v3_phase4_full(history.matches, cache_key=None, grid=(DEFAULT_HYPER,), workers=1)


@pytest.fixture(scope="module")
def full_run(history, baseline):
    return predict_history_full(history, FULL, baseline=baseline, workers=1)


# --- payload -----------------------------------------------------------------------------------------


def test_payload_shape_matches_api(full_run):
    payload = next(iter(full_run.payloads.values()))
    for key in ("engine_version", "lambda_home", "lambda_away", "rho", "ht_share", "dispersion", "uncertainty", "markets", "ratings", "specialists", "calibration"):
        assert key in payload
    assert payload["engine_version"] == "cecchino_v4_goals_v1"
    assert set(payload["dispersion"]) == {"home", "away"}
    assert set(payload["uncertainty"]) >= {"score", "level", "home_evidence", "away_evidence", "disagreement", "new_team_home", "new_team_away"}
    assert payload["uncertainty"]["level"] in LEVELS
    for k in CLASSIC_MARKETS:
        assert set(payload["markets"][k]) == {"p", "lo", "hi"}
        assert 0.0 <= payload["markets"][k]["lo"] <= payload["markets"][k]["p"] <= payload["markets"][k]["hi"] <= 1.0
    for line in AH_LINES:
        assert distributions.ah_line_key("AH_HOME", line) in payload["markets"]
        assert distributions.ah_line_key("AH_AWAY", line) in payload["markets"]
    assert "AH_HOME:-0.5" in payload["markets"] and "AH_HOME:+0.25" in payload["markets"] and "AH_HOME:0.0" in payload["markets"]
    for side in ("home", "away"):
        assert set(payload["ratings"][side]) == {"attack", "defence", "attack_rank", "defence_rank", "teams_in_division", "home_advantage"}
        assert 1 <= payload["ratings"][side]["attack_rank"] <= payload["ratings"][side]["teams_in_division"]
    assert {"forza", "sot", "shots", "weights", "form", "calendar"} <= set(payload["specialists"])
    assert set(payload["calibration"]) == {"applied", "season"}


def test_every_match_gets_a_prediction(history, full_run):
    assert set(full_run.payloads) == {m.lab_match_id for m in history.matches}


def test_probabilities_sum_to_one_per_family(full_run):
    tol = 5e-6  # il payload arrotonda a 6 decimali
    for payload in full_run.payloads.values():
        p = {k: v["p"] for k, v in payload["markets"].items()}
        assert abs(p["HOME"] + p["DRAW"] + p["AWAY"] - 1.0) < tol
        assert abs(p["HOME_PT"] + p["DRAW_PT"] + p["AWAY_PT"] - 1.0) < tol
        for suffix in ("0_5", "1_5", "2_5", "3_5"):
            assert abs(p[f"OVER_{suffix}"] + p[f"UNDER_{suffix}"] - 1.0) < tol
        assert abs(p["ONE_X"] - (p["HOME"] + p["DRAW"])) < tol
        assert abs(p["X_TWO"] - (p["DRAW"] + p["AWAY"])) < tol
        assert abs(p["ONE_TWO"] - (p["HOME"] + p["AWAY"])) < tol
    # senza arrotondamento la coerenza e' esatta
    for row in full_run.rows.values():
        assert abs(row.probs["HOME"] + row.probs["DRAW"] + row.probs["AWAY"] - 1.0) < 1e-9
        assert abs(row.probs["OVER_2_5"] + row.probs["UNDER_2_5"] - 1.0) < 1e-9


def test_baseline_config_reproduces_v3_phase4(history, baseline):
    run = predict_history_full(history, V4GoalsConfig(), baseline=baseline, workers=1)
    for mid, row in run.rows.items():
        v3 = baseline.finals[mid]
        ref = market_probabilities(v3.lambda_home, v3.lambda_away, v3.rho, v3.ht_share)
        for k in MARKET_KEYS:
            assert abs(row.probs[k] - ref[k]) < 1e-9
        assert run.payloads[mid]["uncertainty"]["level"] == LEVEL_MEDIUM
        assert run.payloads[mid]["calibration"] == {"applied": False, "season": None}


# --- handicap asiatico -----------------------------------------------------------------------------------


def test_ah_sign_convention_and_quarter_lines():
    probs = distributions.all_markets(1.7, 1.1, -0.05, 0.45)
    assert probs["AH_HOME:-0.5"] == pytest.approx(probs["HOME"])
    assert probs["AH_HOME:+0.5"] == pytest.approx(probs["ONE_X"])
    assert probs["AH_AWAY:-0.5"] == pytest.approx(probs["AWAY"])
    assert probs["AH_AWAY:+0.5"] == pytest.approx(probs["X_TWO"])
    assert probs["AH_HOME:0.0"] == pytest.approx(probs["HOME"] / (probs["HOME"] + probs["AWAY"]))
    # piu' handicap contro la casa = meno probabilita'
    home_lines = [probs[distributions.ah_line_key("AH_HOME", line)] for line in AH_LINES]
    assert home_lines == sorted(home_lines)
    # linea a quarto tra le due adiacenti
    assert probs["AH_HOME:-1.0"] < probs["AH_HOME:-0.75"] < probs["AH_HOME:-0.5"]
    # casa -1.0 e ospite +1.0 sono la stessa puntata da lati opposti (con rimborso sul pareggio a un gol)
    ft = distributions.score_matrix_v4(1.7, 1.1, -0.05)
    win_h = float(ft[np.tril_indices(11, -2)].sum())
    push = float(np.trace(ft, offset=-1))
    assert probs["AH_HOME:-1.0"] == pytest.approx(win_h / (1.0 - push))


def test_score_matrix_v4_matches_v3_without_dispersion_and_is_wider_with():
    from app.services.cecchino_v3.markets import score_matrix

    assert np.allclose(distributions.score_matrix_v4(1.5, 1.2, -0.08), score_matrix(1.5, 1.2, -0.08))
    nb = distributions.negative_binomial_vector(1.5, 0.1)
    po = distributions.negative_binomial_vector(1.5, 0.0)
    assert nb.sum() == pytest.approx(1.0, abs=1e-3)
    assert float((nb * np.arange(11)).sum()) == pytest.approx(1.5, abs=1e-2)
    assert float((nb * np.arange(11) ** 2).sum()) > float((po * np.arange(11) ** 2).sum())


# --- calibrazione, dispersione ------------------------------------------------------------------------------


def test_calibration_identity_in_warmup_and_applied_later(full_run):
    for mid, row in full_run.rows.items():
        cal = full_run.payloads[mid]["calibration"]
        if row.season == SEASONS[0]:
            assert cal == {"applied": False, "season": None}
    info = full_run.season_info
    assert info[SEASONS[0]]["calibration_applied"] is False
    assert info[SEASONS[0]]["previous_season"] is None
    # nelle stagioni successive la stagione di stima e' quella precedente (se ci sono abbastanza righe)
    for s_idx in (1, 2):
        assert info[SEASONS[s_idx]]["previous_season"] == SEASONS[s_idx - 1]


def test_isotonic_requires_min_rows_and_is_monotone():
    assert additions.fit_isotonic([0.1, 0.9], [0, 1]) is None
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 500)
    y = (rng.uniform(0, 1, 500) < p**2).astype(float)
    model = additions.fit_isotonic(p, y)
    assert model is not None
    grid = np.linspace(0, 1, 11)
    pred = model.predict(grid)
    assert np.all(np.diff(pred) >= -1e-12)
    out = additions.apply_calibration({k: v for k, v in distributions.all_markets(1.6, 1.1, -0.05, 0.45).items()}, {"HOME": model})
    assert abs(out["HOME"] + out["DRAW"] + out["AWAY"] - 1.0) < 1e-9
    assert abs(out["ONE_X"] - out["HOME"] - out["DRAW"]) < 1e-9


def test_dispersion_method_of_moments():
    rng = np.random.default_rng(1)
    lam = rng.uniform(0.8, 2.0, 5000)
    poisson = rng.poisson(lam)
    alpha_poisson = additions.dispersion_alpha(lam, poisson.astype(float))
    assert alpha_poisson is None or alpha_poisson < 0.03  # ~0 a meno del rumore di campionamento
    assert additions.dispersion_alpha(lam, lam.copy()) is None  # varianza nulla -> alpha < 0 -> Poisson
    r = 1.0 / 0.3
    nb = rng.negative_binomial(r, r / (r + lam))
    alpha = additions.dispersion_alpha(lam, nb.astype(float))
    assert alpha is not None and 0.15 < alpha < 0.45
    assert additions.dispersion_alpha(lam[:50], nb[:50].astype(float)) is None  # poche righe


# --- incertezza -----------------------------------------------------------------------------------------------


def test_uncertainty_levels_by_cutpoints_and_new_team():
    cuts = (0.2, 0.45)
    assert additions.uncertainty_level(0.1, cuts) == LEVEL_LOW
    assert additions.uncertainty_level(0.2, cuts) == LEVEL_MEDIUM
    assert additions.uncertainty_level(0.44, cuts) == LEVEL_MEDIUM
    assert additions.uncertainty_level(0.45, cuts) == LEVEL_HIGH
    assert additions.uncertainty_level(0.0, cuts, new_team=True) == LEVEL_HIGH
    assert additions.uncertainty_cuts(None) == (0.20, 0.45)
    lo, hi = additions.uncertainty_cuts(list(np.linspace(0, 1, 101)))
    assert lo == pytest.approx(0.30) and hi == pytest.approx(0.70)


def test_uncertainty_score_components():
    ops = {"forza": (1.5, 1.0), "sot": (1.5, 1.0), "shots": (1.5, 1.0)}
    known = additions.uncertainty_score(40.0, 40.0, ops)
    assert known.score == 0.0 and not known.new_team_home
    unknown = additions.uncertainty_score(0.0, 40.0, ops)
    assert unknown.new_team_home and unknown.score == pytest.approx(0.65)
    disagree = additions.uncertainty_score(40.0, 40.0, {"forza": (1.0, 1.0), "sot": (1.0, 1.0), "shots": (math.e, 1.0)})
    assert disagree.disagreement == pytest.approx(1.0)
    assert disagree.score == pytest.approx(0.35)


def test_uncertainty_levels_and_intervals_in_history_run(full_run):
    levels = {r.level for r in full_run.rows.values() if r.season != SEASONS[0]}
    assert levels <= set(LEVELS)
    payload = next(iter(full_run.payloads.values()))
    wide = [k for k, v in payload["markets"].items() if v["hi"] - v["lo"] > 0]
    assert wide, "gli intervalli devono avere ampiezza positiva su qualche mercato"


# --- vantaggio casa -----------------------------------------------------------------------------------------------


def test_team_home_advantage_is_walk_forward_and_bounded():
    d0 = date(2022, 1, 1)
    recs = []
    for i in range(12):
        d = d0 + timedelta(days=7 * i)
        recs.append(
            MatchRecord(
                lab_match_id=i + 1, competition=DIV_A, group="italy", season_label="2021/2022", match_date=d,
                kickoff_at=None, day=(d - _EPOCH).days, home_team="X", away_team="Y", ft_home=5, ft_away=0, ht_home=None, ht_away=None,
            )
        )
    expected = {r.lab_match_id: (1.3, 1.3) for r in recs}
    out = additions.team_home_advantage(recs, expected)
    assert out[1].kappa == 0.0 and out[1].hdev_home == 0.0  # prima partita: nessun passato
    assert out[2].kappa > 0.0  # X vince sempre in casa oltre le attese
    assert all(abs(o.kappa) <= 0.25 for o in out.values())
    assert out[12].kappa == pytest.approx(0.25)  # limite raggiunto


# --- live ------------------------------------------------------------------------------------------------------------


def test_predict_targets_never_uses_target_rows(history):
    matches = history.matches
    last_day = max(m.day for m in matches)
    targets = [m for m in matches if m.day == last_day]
    before = [m for m in matches if m.day < last_day]
    tm = [
        TargetMatch(key=str(m.lab_match_id), competition=m.competition, season_label=m.season_label, match_date=m.match_date, home_team=m.home_team, away_team=m.away_team)
        for m in targets
    ]
    art = fit_live_artifacts(before, FULL, before_season=SEASONS[-1], workers=1)
    assert art.fitted_on == SEASONS[-2] and art.season == SEASONS[-1]
    # con o senza le righe bersaglio nello storico (con esiti fasulli) il risultato e' identico
    fake = [MatchRecord(**{**m.__dict__, "ft_home": 9, "ft_away": 0}) for m in targets]
    res_clean = predict_targets(before, tm, FULL, artifacts=art)
    res_dirty = predict_targets(before + fake, tm, FULL, artifacts=art)
    assert res_clean.keys() == res_dirty.keys() == {t.key for t in tm}
    for k in res_clean:
        assert res_clean[k]["lambda_home"] == res_dirty[k]["lambda_home"]
        assert res_clean[k]["markets"]["HOME"]["p"] == res_dirty[k]["markets"]["HOME"]["p"]
    payload = res_clean[tm[0].key]
    assert abs(payload["markets"]["HOME"]["p"] + payload["markets"]["DRAW"]["p"] + payload["markets"]["AWAY"]["p"] - 1.0) < 1e-6
    assert payload["uncertainty"]["level"] in LEVELS


def test_predict_targets_unknown_team_is_new_and_high_uncertainty(history):
    matches = history.matches
    last = matches[-1]
    art = fit_live_artifacts(matches, FULL, before_season=SEASONS[-1], workers=1)
    t = TargetMatch(key="new", competition=DIV_A, season_label=SEASONS[-1], match_date=last.match_date + timedelta(days=7), home_team="Squadra Mai Vista", away_team=last.home_team)
    res = predict_targets(matches, [t], FULL, artifacts=art)
    u = res["new"]["uncertainty"]
    assert u["new_team_home"] is True and u["new_team_away"] is False
    assert u["home_evidence"] == 0.0 and u["level"] == LEVEL_HIGH
    assert res["new"]["ratings"]["home"]["attack"] == 0.0  # livello della divisione
    assert 0.0 < res["new"]["lambda_home"] < 5.0


def test_adopted_config_is_a_valid_config():
    cfg = adopted_config()
    assert isinstance(cfg, V4GoalsConfig)
    assert cfg.live_hyper.xi > 0 and cfg.live_hyper.sigma > 0


def test_market_family_covers_classic_markets():
    assert set(MARKET_FAMILY) == set(CLASSIC_MARKETS) == set(MARKET_KEYS)
