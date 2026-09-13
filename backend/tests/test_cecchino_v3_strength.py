"""Controlli del motore Forza V3 su dati simulati (nessun database)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from app.services.cecchino_v3.constants import Hyper
from app.services.cecchino_v3.data import MatchRecord, annotate_season_context
from app.services.cecchino_v3.markets import market_outcomes, market_probabilities
from app.services.cecchino_v3.orchestrator import Opinions, combine, fit_weights
from app.services.cecchino_v3.strength_model import (
    ParamLayout,
    WindowData,
    fit_strength,
    team_divisions,
)
from app.services.cecchino_v3.walkforward import run_game_group, run_group


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
                    home_shots=int(rng.poisson(13)),
                    away_shots=int(rng.poisson(10)),
                    home_sot=int(rng.poisson(4.5)),
                    away_sot=None if day == 3 else int(rng.poisson(3.5)),
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


def test_game_specialist_never_uses_same_day_or_future_stats():
    matches = _records()
    hyper = Hyper(xi=0.002, sigma=0.3)
    base = run_game_group(matches, hyper, "sot")
    cut_day = matches[len(matches) // 2].day
    changed = [
        MatchRecord(**{**m.__dict__, "home_sot": 30 if m.day >= cut_day else m.home_sot})
        for m in matches
    ]
    after = run_game_group(changed, hyper, "sot")
    for m in matches:
        if m.day <= cut_day:
            assert base[m.lab_match_id] == after[m.lab_match_id]
    last = base[matches[-1].lab_match_id]
    # ~4 tiri in porta attesi, tradotti in gol con la conversione della divisione
    assert 2.5 < last.stat_home < 7.0
    assert 0.1 < last.conversion < 0.6
    assert abs(last.lambda_home - last.stat_home * last.conversion) < 1e-9


def test_orchestrator_recovers_combination_weights():
    rng = np.random.default_rng(11)
    samples = []
    for _ in range(6000):
        f_h, s_h, t_h = rng.uniform(0.6, 2.4, 3)
        f_a, s_a, t_a = rng.uniform(0.5, 2.0, 3)
        true_h = np.exp(0.05 + 0.5 * np.log(f_h) + 0.4 * np.log(s_h))
        true_a = np.exp(0.05 + 0.5 * np.log(f_a) + 0.4 * np.log(s_a))
        ops = Opinions(
            home={"forza": f_h, "sot": s_h, "shots": t_h},
            away={"forza": f_a, "sot": s_a, "shots": t_a},
        )
        samples.append((ops, int(rng.poisson(true_h)), int(rng.poisson(true_a))))
    w = fit_weights(samples)
    assert abs(w["forza"] - 0.5) < 0.1
    assert abs(w["sot"] - 0.4) < 0.1
    assert abs(w["shots"]) < 0.1
    home, away = combine(samples[0][0], w)
    assert home > 0 and away > 0


def test_orchestrator_default_is_forza_only():
    ops = Opinions(home={"forza": 1.7, "sot": 0.9, "shots": 1.1}, away={"forza": 1.1, "sot": 1.5, "shots": 1.2})
    home, away = combine(ops, {"intercept": 0.0, "forza": 1.0, "sot": 0.0, "shots": 0.0})
    assert abs(home - 1.7) < 1e-9 and abs(away - 1.1) < 1e-9


# --- Fase 3: forma e regole d'esame ---------------------------------------------


def _form_match(mid, day, home, away, gh, ga, season="2022/2023", shots=(12, 10)):
    match_day = date(2022, 8, 1) + timedelta(days=day)
    return MatchRecord(
        lab_match_id=mid,
        competition="Serie A",
        group="italy",
        season_label=season,
        match_date=match_day,
        kickoff_at=None,
        day=(match_day - date(2000, 1, 1)).days,
        home_team=home,
        away_team=away,
        ft_home=gh,
        ft_away=ga,
        ht_home=0,
        ht_away=0,
        home_shots=shots[0],
        away_shots=shots[1],
        home_sot=4,
        away_sot=3,
    )


def test_form_is_zero_when_results_match_expectations():
    from app.services.cecchino_v3.form import Expectation, compute_form

    matches = [_form_match(i, i, "A", "B", 1, 1) for i in range(1, 7)]
    exp = {m.lab_match_id: Expectation(1.0, 1.0, 12.0, 10.0) for m in matches}
    form = compute_form(matches, exp)
    last = form[6]
    assert last.matches_home == 5 and last.matches_away == 5
    assert abs(last.goals_home) < 1e-12 and abs(last.shots_home) < 1e-12


def test_form_rewards_outperformance_and_uses_only_last_five_of_same_season():
    from app.services.cecchino_v3.constants import FORM_PSEUDO_COUNT
    from app.services.cecchino_v3.form import Expectation, compute_form

    # stagione precedente: A segna tantissimo (non deve contare)
    old = [_form_match(100 + i, i, "A", "C", 6, 0, season="2021/2022") for i in range(5)]
    # stagione in corso: 6 partite, la prima con 5 gol (esce dalle ultime 5), poi 2 gol ciascuna
    current = [_form_match(1, 400, "A", "B", 5, 0)] + [
        _form_match(1 + i, 400 + i, "A", "B", 2, 1) for i in range(1, 6)
    ]
    target = _form_match(50, 410, "A", "B", 0, 0)
    matches = old + current + [target]
    exp = {m.lab_match_id: Expectation(1.0, 1.0, 12.0, 10.0) for m in matches}
    form = compute_form(matches, exp)[50]
    pg = FORM_PSEUDO_COUNT["goals"]
    expected_attack = math.log((10 + pg) / (5 + pg))  # ultime 5: 2 gol a partita contro 1 atteso
    expected_defence_b = math.log((10 + pg) / (5 + pg))  # B ha subito 2 a partita contro 1 attesa
    assert abs(form.goals_home - (expected_attack + expected_defence_b)) < 1e-12
    assert form.matches_home == 5


def test_form_ignores_same_day_and_future_results():
    from app.services.cecchino_v3.form import Expectation, compute_form

    base = [_form_match(i, i // 2, "A" if i % 2 else "C", "B" if i % 2 else "D", 1, 1) for i in range(1, 21)]
    exp = {m.lab_match_id: Expectation(1.2, 1.0, 12.0, 10.0) for m in base}
    before = compute_form(base, exp)
    cut = base[10].day
    changed = [MatchRecord(**{**m.__dict__, "ft_home": 7 if m.day >= cut else m.ft_home}) for m in base]
    after = compute_form(changed, exp)
    for m in base:
        if m.day <= cut:
            assert before[m.lab_match_id] == after[m.lab_match_id]


def test_orchestrator_learns_adjustment_weight():
    rng = np.random.default_rng(5)
    samples = []
    for _ in range(8000):
        f_h, f_a = rng.uniform(0.7, 2.2, 2)
        adj_h, adj_a = rng.normal(0, 0.3, 2)
        true_h = np.exp(np.log(f_h) + 0.3 * adj_h)
        true_a = np.exp(np.log(f_a) + 0.3 * adj_a)
        ops = Opinions(
            home={"forza": f_h, "sot": f_h, "shots": f_h},
            away={"forza": f_a, "sot": f_a, "shots": f_a},
            adjust_home={"form_goals": adj_h, "form_shots": 0.0},
            adjust_away={"form_goals": adj_a, "form_shots": 0.0},
        )
        samples.append((ops, int(rng.poisson(true_h)), int(rng.poisson(true_a))))
    w = fit_weights(samples, ("form_goals", "form_shots"))
    assert abs(w["form_goals"] - 0.3) < 0.08
    assert abs(w["form_shots"]) < 1e-6  # nessuna variazione -> resta al valore a priori
    home, _ = combine(samples[0][0], w)
    assert home > 0


def test_exam_tolerance_rules():
    from app.services.cecchino_v3.constants import EXAM_FAMILIES, JUDGE_SEASONS
    from app.services.cecchino_v3.evaluation import _exam

    def rows(changes):
        out = []
        for family in EXAM_FAMILIES:
            for season, change in zip(JUDGE_SEASONS, changes):
                out.append({"family": family, "season_label": season, "brier_v3": 0.2 * (1 + change / 100), "brier_prev": 0.2})
        return out

    calibration = {"FT_1X2": {"v3_pct": 1.0}, "FT_OVER_UNDER": {"v3_pct": 1.0}}
    # una stagione peggiore dello 0,05% (entro tolleranza), media in calo: passa
    assert _exam(rows([-0.5, 0.05, -0.3]), calibration, reference="prev", tolerance_pct=0.1)["passed"]
    # una stagione peggiore dello 0,2%: non passa
    assert not _exam(rows([-0.5, 0.2, -0.3]), calibration, reference="prev", tolerance_pct=0.1)["passed"]
    # tutte entro tolleranza ma media in aumento: non passa
    assert not _exam(rows([0.05, 0.05, -0.02]), calibration, reference="prev", tolerance_pct=0.1)["passed"]
    # senza tolleranza un pareggio esatto non passa (regola della Fase 2)
    assert not _exam(rows([0.0, -0.5, -0.5]), calibration, reference="prev")["passed"]
