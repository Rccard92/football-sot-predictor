"""Controlli del motore Forza V3 su dati simulati (nessun database)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.services.cecchino_v3.constants import Hyper
from app.services.cecchino_v3.data import MatchRecord, annotate_season_context
from app.services.cecchino_v3.markets import market_outcomes, market_probabilities
from app.services.cecchino_v3.strength_model import (
    ParamLayout,
    WindowData,
    fit_strength,
    team_divisions,
)
from app.services.cecchino_v3.walkforward import run_group


def test_market_probabilities_are_coherent():
    p = market_probabilities(1.6, 1.1, -0.08, 0.45)
    assert abs(p["HOME"] + p["DRAW"] + p["AWAY"] - 1.0) < 1e-9
    assert abs(p["HOME_PT"] + p["DRAW_PT"] + p["AWAY_PT"] - 1.0) < 1e-9
    assert abs(p["ONE_X"] - (p["HOME"] + p["DRAW"])) < 1e-12
    for line in ("0_5", "1_5", "2_5", "3_5"):
        assert abs(p[f"OVER_{line}"] + p[f"UNDER_{line}"] - 1.0) < 1e-9
    assert p["OVER_0_5"] > p["OVER_1_5"] > p["OVER_2_5"] > p["OVER_3_5"]
    assert p["HOME"] > p["AWAY"]


def test_negative_rho_increases_draws():
    assert market_probabilities(1.3, 1.3, -0.1, 0.45)["DRAW"] > market_probabilities(1.3, 1.3, 0.0, 0.45)["DRAW"]


def test_market_outcomes():
    o = market_outcomes(2, 1, 0, 0)
    assert o["HOME"] and not o["DRAW"] and o["OVER_2_5"] and not o["OVER_3_5"] and o["DRAW_PT"]
    assert market_outcomes(1, 1, None, None)["HOME_PT"] is None


def _simulate(seed: int = 7):
    rng = np.random.default_rng(seed)
    n_teams, n_div = 20, 2
    att = rng.normal(0, 0.25, n_teams)
    dfn = rng.normal(0, 0.25, n_teams)
    division_of_team = np.array([0] * 10 + [1] * 10)
    level_att, level_def = np.array([0.0, -0.3]), np.array([0.0, -0.3])
    mu, home_adv = np.array([0.1, 0.05]), np.array([0.25, 0.2])
    rows = []
    for _ in range(12):  # 12 giri completi
        for h in range(n_teams):
            for a in range(n_teams):
                if h == a or division_of_team[h] != division_of_team[a]:
                    continue
                d = division_of_team[h]
                lh = np.exp(mu[d] + home_adv[d] + level_att[d] + att[h] - level_def[d] - dfn[a])
                la = np.exp(mu[d] + level_att[d] + att[a] - level_def[d] - dfn[h])
                rows.append((h, a, d, rng.poisson(lh), rng.poisson(la)))
    arr = np.array(rows)
    return att, arr, n_teams, n_div, division_of_team


def test_fit_recovers_team_strength():
    att, arr, n_teams, n_div, division_of_team = _simulate()
    layout = ParamLayout(n_divisions=n_div, n_teams=n_teams)
    window = WindowData(
        home=arr[:, 0],
        away=arr[:, 1],
        division=arr[:, 2],
        home_goals=arr[:, 3].astype(float),
        away_goals=arr[:, 4].astype(float),
        weight=np.ones(len(arr)),
    )
    team_div = team_divisions(window, n_teams=n_teams, n_divisions=n_div, fallback=np.zeros(n_teams, dtype=int))
    assert (team_div == division_of_team).all()
    beta = fit_strength(layout, window, team_division=team_div, newcomer=np.zeros(n_teams), sigma=0.4)
    est_att = beta[layout.team_att(np.arange(n_teams))]
    for d in range(n_div):
        mask = division_of_team == d
        assert np.corrcoef(est_att[mask], att[mask])[0, 1] > 0.8
    assert 0.1 < beta[layout.home[0]] < 0.4


def _records(n_days: int = 60) -> list[MatchRecord]:
    rng = np.random.default_rng(3)
    teams = [f"T{i}" for i in range(8)]
    out: list[MatchRecord] = []
    start = date(2021, 8, 1)
    mid = 1
    for day in range(n_days):
        order = rng.permutation(8)
        for k in range(4):
            h, a = teams[order[2 * k]], teams[order[2 * k + 1]]
            match_day = start + timedelta(days=day * 3)
            out.append(
                MatchRecord(
                    lab_match_id=mid,
                    competition="Serie A",
                    group="italy",
                    season_label="2021/2022",
                    match_date=match_day,
                    kickoff_at=None,
                    day=(match_day - date(2000, 1, 1)).days,
                    home_team=h,
                    away_team=a,
                    ft_home=int(rng.poisson(1.5)),
                    ft_away=int(rng.poisson(1.1)),
                    ht_home=0,
                    ht_away=0,
                )
            )
            mid += 1
    annotate_season_context(out)
    return out


def test_walkforward_never_uses_same_day_or_future_results():
    matches = _records()
    hyper = Hyper(xi=0.002, sigma=0.3)
    base = run_group(matches, hyper)
    cut_day = matches[len(matches) // 2].day
    changed = [
        MatchRecord(**{**m.__dict__, "ft_home": 9 if m.day >= cut_day else m.ft_home})
        for m in matches
    ]
    after = run_group(changed, hyper)
    for m in matches:
        if m.day <= cut_day:
            assert base[m.lab_match_id] == after[m.lab_match_id]


def test_season_context_phases():
    matches = _records(n_days=20)
    first = matches[0]
    assert first.home_played == 0 and not first.eval_eligible and first.phase == "early"
    assert any(m.phase == "final" for m in matches)
    assert any(m.phase == "mid" for m in matches)
