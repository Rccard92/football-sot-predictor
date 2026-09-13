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


# --- Fase 4: calendario ---------------------------------------------------------


def test_rest_score_limits_and_reference():
    from app.services.cecchino_v3.calendar_features import rest_score

    assert abs(rest_score(7)) < 1e-12
    assert rest_score(1) == rest_score(2) < rest_score(3)
    assert rest_score(10) == rest_score(40) == rest_score(None) > rest_score(9)


def test_calendar_rest_days_and_final_phase():
    from app.services.cecchino_v3.calendar_features import compute_calendar, rest_score

    matches = [
        _form_match(1, 0, "A", "B", 1, 0),
        _form_match(2, 3, "C", "A", 0, 0),  # A riposa 3 giorni, C debutta
        _form_match(3, 10, "A", "C", 2, 2),  # A 7 giorni, C 7 giorni
    ]
    annotate_season_context(matches)
    cal = compute_calendar(matches)
    assert cal[1].rest_days_home is None and cal[1].rest_days_away is None
    assert cal[2].rest_days_home is None and cal[2].rest_days_away == 3
    assert cal[3].rest_days_home == 7 and cal[3].rest_days_away == 7
    # lato casa della partita 2: attacca C (senza precedenti), difende A (3 giorni)
    assert cal[2].adjust_home["rest_attack"] == rest_score(None)
    assert cal[2].adjust_home["rest_defence"] == rest_score(3)
    assert cal[2].adjust_away["rest_attack"] == rest_score(3)
    assert cal[3].adjust_home["final_phase"] == (1.0 if matches[2].phase == "final" else 0.0)


def test_build_adjustments_merges_form_and_calendar():
    from app.services.cecchino_v3.calendar_features import compute_calendar
    from app.services.cecchino_v3.constants import CALENDAR_ADJUSTMENTS, FORM_ADJUSTMENTS
    from app.services.cecchino_v3.form import Expectation, compute_form
    from app.services.cecchino_v3.service import build_adjustments

    matches = [_form_match(i, i * 3, "A" if i % 2 else "B", "B" if i % 2 else "A", 1, 1) for i in range(1, 9)]
    annotate_season_context(matches)
    form = compute_form(matches, {m.lab_match_id: Expectation(1.0, 1.0, 12.0, 10.0) for m in matches})
    cal = compute_calendar(matches)
    adj = build_adjustments(form, cal)
    assert adj is not None and adj.keys == FORM_ADJUSTMENTS + CALENDAR_ADJUSTMENTS
    assert set(adj.home[5]) == set(FORM_ADJUSTMENTS + CALENDAR_ADJUSTMENTS)
    only_form = build_adjustments(form)
    assert only_form is not None and only_form.keys == FORM_ADJUSTMENTS
    assert build_adjustments(None) is None


# --- Fase 5: disciplina ---------------------------------------------------------


def _discipline_match(mid, day, home, away, fouls=(11, 11), cards=((2, 0), (2, 0)), referee=None, goals=(1, 1)):
    m = _form_match(mid, day, home, away, goals[0], goals[1])
    return MatchRecord(
        **{
            **m.__dict__,
            "home_fouls": fouls[0],
            "away_fouls": fouls[1],
            "home_yellow": cards[0][0],
            "home_red": cards[0][1],
            "away_yellow": cards[1][0],
            "away_red": cards[1][1],
            "referee": referee,
        }
    )


def test_discipline_indices_follow_team_versus_division_average():
    from app.services.cecchino_v3.constants import DISCIPLINE_PSEUDO_MATCHES
    from app.services.cecchino_v3.discipline import compute_discipline
    from app.services.cecchino_v3.form import Expectation

    matches = [
        _discipline_match(1, 0, "A", "B", fouls=(20, 10)),
        _discipline_match(2, 1, "C", "D", fouls=(10, 20)),
        _discipline_match(3, 5, "A", "D", fouls=(15, 15)),
    ]
    exp = {m.lab_match_id: Expectation(1.0, 1.0, 12.0, 10.0) for m in matches}
    feats = compute_discipline(matches, exp)
    # prima partita: nessun dato, tutto nella media a priori
    assert feats[1].adjust_home["fouls_attack"] == 0.0
    # terza partita: media divisione con 4 osservazioni reali (media 15) + prior
    from app.services.cecchino_v3.constants import DISCIPLINE_PRIOR_FOULS

    k = DISCIPLINE_PSEUDO_MATCHES
    avg = (60 + k * DISCIPLINE_PRIOR_FOULS) / (4 + k)
    expected_a = math.log((20 + k * avg) / ((1 + k) * avg))
    expected_d = math.log((20 + k * avg) / ((1 + k) * avg))
    assert abs(feats[3].adjust_home["fouls_attack"] - expected_a) < 1e-12
    assert abs(feats[3].adjust_home["fouls_defence"] - expected_d) < 1e-12
    assert feats[3].adjust_away["fouls_attack"] == feats[3].adjust_home["fouls_defence"]


def test_referee_index_uses_only_past_matches_of_that_referee():
    from app.services.cecchino_v3.constants import REFEREE_PSEUDO_GOALS
    from app.services.cecchino_v3.discipline import compute_discipline
    from app.services.cecchino_v3.form import Expectation

    matches = [
        _discipline_match(1, 0, "A", "B", referee="R1", goals=(3, 3)),
        _discipline_match(2, 1, "C", "D", referee="R2", goals=(0, 0)),
        _discipline_match(3, 4, "A", "C", referee="R1", goals=(0, 0)),
        _discipline_match(4, 4, "B", "D", referee=None),
    ]
    exp = {m.lab_match_id: Expectation(1.5, 1.0, 12.0, 10.0) for m in matches}
    feats = compute_discipline(matches, exp)
    assert feats[1].adjust_home["referee_goals"] == 0.0
    expected = math.log((6 + REFEREE_PSEUDO_GOALS) / (2.5 + REFEREE_PSEUDO_GOALS))
    assert abs(feats[3].adjust_home["referee_goals"] - expected) < 1e-12
    assert feats[3].adjust_away["referee_goals"] == feats[3].adjust_home["referee_goals"]
    assert feats[4].adjust_home["referee_goals"] == 0.0
    # cambiare i risultati dal giorno della partita 3 in poi non cambia nulla dei giorni fino a quello
    cut = matches[2].day
    changed = [MatchRecord(**{**m.__dict__, "ft_home": 9, "home_fouls": 40}) if m.day >= cut else m for m in matches]
    after = compute_discipline(changed, exp)
    for m in matches:
        assert feats[m.lab_match_id] == after[m.lab_match_id]


def test_build_adjustments_with_discipline():
    from app.services.cecchino_v3.calendar_features import compute_calendar
    from app.services.cecchino_v3.constants import CALENDAR_ADJUSTMENTS, DISCIPLINE_ADJUSTMENTS, FORM_ADJUSTMENTS
    from app.services.cecchino_v3.discipline import compute_discipline
    from app.services.cecchino_v3.form import Expectation, compute_form
    from app.services.cecchino_v3.service import build_adjustments

    matches = [_discipline_match(i, i * 3, "A" if i % 2 else "B", "B" if i % 2 else "A") for i in range(1, 7)]
    annotate_season_context(matches)
    exp = {m.lab_match_id: Expectation(1.0, 1.0, 12.0, 10.0) for m in matches}
    adj = build_adjustments(compute_form(matches, exp), compute_calendar(matches), compute_discipline(matches, exp))
    assert adj is not None
    assert adj.keys == FORM_ADJUSTMENTS + CALENDAR_ADJUSTMENTS + DISCIPLINE_ADJUSTMENTS
    assert set(adj.away[4]) == set(adj.keys)


# --- Rifinitura: promosse/retrocesse, calibrazione, esame rigoroso ------------


def _pyramid_match(mid, season, day, competition, home, away, gh=1, ga=1):
    m = _form_match(mid, day, home, away, gh, ga, season=season)
    return MatchRecord(**{**m.__dict__, "competition": competition, "group": "england"})


def test_mover_flags_detect_promotion_and_relegation():
    from app.services.cecchino_v3.walkforward import mover_flags

    div_index = {"Premier League": 0, "Championship": 1}
    matches = [
        _pyramid_match(1, "2021/2022", 0, "Premier League", "Big", "Down"),
        _pyramid_match(2, "2021/2022", 1, "Championship", "Up", "Stay"),
        _pyramid_match(3, "2022/2023", 400, "Premier League", "Up", "Big"),
        _pyramid_match(4, "2022/2023", 401, "Championship", "Down", "New"),
    ]
    home, away = mover_flags(matches, div_index)
    assert home[0].tolist() == [0.0, 0.0] and away[0].tolist() == [0.0, 0.0]  # prima stagione
    assert home[2].tolist() == [1.0, 0.0]  # Up promossa in Premier
    assert away[2].tolist() == [0.0, 0.0]  # Big resta in Premier
    assert home[3].tolist() == [0.0, 1.0]  # Down retrocessa
    assert away[3].tolist() == [0.0, 0.0]  # New non era nel dataset


def test_movers_without_moves_gives_same_expected_goals():
    from app.services.cecchino_v3.strength_model import expected_goals

    _, arr, n_teams, n_div, _ = _simulate()
    window = WindowData(
        home=arr[:, 0],
        away=arr[:, 1],
        division=arr[:, 2],
        home_goals=arr[:, 3].astype(float),
        away_goals=arr[:, 4].astype(float),
        weight=np.ones(len(arr)),
    )
    team_div = team_divisions(window, n_teams=n_teams, n_divisions=n_div, fallback=np.zeros(n_teams, dtype=int))
    newcomer = np.zeros(n_teams)
    base_layout = ParamLayout(n_divisions=n_div, n_teams=n_teams)
    beta0 = fit_strength(base_layout, window, team_division=team_div, newcomer=newcomer, sigma=0.4)
    zeros = np.zeros((len(arr), 2))
    mover_layout = ParamLayout(n_divisions=n_div, n_teams=n_teams, movers=True)
    window_m = WindowData(**{**window.__dict__, "home_move": zeros, "away_move": zeros})
    beta1 = fit_strength(mover_layout, window_m, team_division=team_div, newcomer=newcomer, sigma=0.4)

    h0, a0 = expected_goals(
        base_layout, beta0, division=arr[:, 2], home=arr[:, 0], away=arr[:, 1],
        team_division=team_div, newcomer=newcomer,
    )
    h1, a1 = expected_goals(
        mover_layout, beta1, division=arr[:, 2], home=arr[:, 0], away=arr[:, 1],
        team_division=team_div, newcomer=newcomer, home_move=zeros, away_move=zeros,
    )
    assert np.max(np.abs(h0 - h1)) < 1e-8 and np.max(np.abs(a0 - a1)) < 1e-8
    assert abs(beta1[mover_layout.promoted_att]) < 1e-12  # nessun caso: resta al valore a priori


def test_fit_estimates_promotion_penalty():
    rng = np.random.default_rng(21)
    n_teams = 20
    rows, home_flags, away_flags = [], [], []
    for _ in range(10):
        for h in range(n_teams):
            for a in range(n_teams):
                if h == a:
                    continue
                h_up, a_up = float(h < 4), float(a < 4)  # 4 squadre promosse
                lh = np.exp(0.35 - 0.3 * h_up + 0.2 * a_up)
                la = np.exp(0.10 - 0.3 * a_up + 0.2 * h_up)
                rows.append((h, a, 0, rng.poisson(lh), rng.poisson(la)))
                home_flags.append((h_up, 0.0))
                away_flags.append((a_up, 0.0))
    arr = np.array(rows)
    layout = ParamLayout(n_divisions=1, n_teams=n_teams, movers=True)
    window = WindowData(
        home=arr[:, 0],
        away=arr[:, 1],
        division=arr[:, 2],
        home_goals=arr[:, 3].astype(float),
        away_goals=arr[:, 4].astype(float),
        weight=np.ones(len(arr)),
        home_move=np.array(home_flags),
        away_move=np.array(away_flags),
    )
    beta = fit_strength(
        layout, window, team_division=np.zeros(n_teams, dtype=int), newcomer=np.zeros(n_teams), sigma=0.05
    )
    # attacco piu' debole (-0,3) e difesa piu' debole (concede +0,2 -> parametro -0,2)
    assert -0.45 < beta[layout.promoted_att] < -0.15
    assert -0.35 < beta[layout.promoted_def] < -0.05


def test_calibration_identity_and_recovery():
    from app.services.cecchino_v3.calibration import (
        IDENTITY,
        Calibration,
        CalibrationSample,
        apply_calibration,
        fit_calibration,
    )

    h_id, a_id = apply_calibration(1.7, 0.9, IDENTITY)
    assert abs(h_id - 1.7) < 1e-12 and abs(a_id - 0.9) < 1e-12

    rng = np.random.default_rng(8)
    true = Calibration(alpha=1.3, beta=0.05, gamma=-0.04)
    samples = []
    for _ in range(12000):
        lh, la = rng.uniform(0.6, 2.2), rng.uniform(0.5, 1.8)
        th, ta = apply_calibration(lh, la, true)
        samples.append(CalibrationSample(lh, la, 0.0, int(rng.poisson(th)), int(rng.poisson(ta))))
    fitted = fit_calibration(samples)
    assert abs(fitted.alpha - 1.3) < 0.08
    assert abs(fitted.beta - 0.05) < 0.04
    assert abs(fitted.gamma + 0.04) < 0.03
    # mercati ancora coerenti dopo la calibrazione
    h, a = apply_calibration(1.5, 1.0, fitted)
    p = market_probabilities(h, a, -0.05, 0.45)
    assert abs(p["HOME"] + p["DRAW"] + p["AWAY"] - 1.0) < 1e-9
    assert fit_calibration([]) == IDENTITY


def test_exam_strict_rules():
    from app.services.cecchino_v3.constants import EXAM_FAMILIES, JUDGE_SEASONS
    from app.services.cecchino_v3.evaluation import _exam

    def rows(changes_by_family):
        out = []
        for family in EXAM_FAMILIES:
            for season, change in zip(JUDGE_SEASONS, changes_by_family.get(family, [-0.1, -0.1, -0.1])):
                out.append(
                    {"family": family, "season_label": season, "brier_v3": 0.2 * (1 + change / 100), "brier_prev": 0.2}
                )
        return out

    cal = {"FT_1X2": {"v3_pct": 1.0}, "FT_OVER_UNDER": {"v3_pct": 1.0}}
    stable = {"x": dict(zip(JUDGE_SEASONS, [0.2, 0.15, 0.005]))}
    good = rows({})

    def passed(by_season, stability):
        return _exam(by_season, cal, reference="prev", tolerance_pct=0.1, strict=True, stability=stability)["passed"]

    assert passed(good, stable)
    # guadagno medio sotto lo 0,05% su 1X2: non passa
    assert not passed(rows({"FT_1X2": [-0.04, -0.03, -0.05]}), stable)
    # la soglia minima vale solo per 1X2 e Over/Under
    assert passed(rows({"HT_1X2": [-0.01, -0.02, -0.01]}), stable)
    # parametro che cambia segno: non passa
    assert not passed(good, {"x": dict(zip(JUDGE_SEASONS, [0.2, -0.15, 0.1]))})
    # regola rigorosa senza parametri da controllare: non passa
    assert not passed(good, None)


def test_calibration_preserving_total_goals():
    from app.services.cecchino_v3.calibration import (
        Calibration,
        CalibrationSample,
        apply_calibration,
        fit_calibration,
    )

    # gamma = 0: i gol totali restano identici anche allargando molto le differenze
    cal = Calibration(alpha=1.4, beta=-0.05, gamma=0.0, preserve_total=True)
    h, a = apply_calibration(1.8, 0.8, cal)
    assert abs((h + a) - 2.6) < 1e-12
    assert h / a > 1.8 / 0.8  # differenza allargata
    # la variante a livello medio fisso invece aumenta i gol totali
    h1, a1 = apply_calibration(1.8, 0.8, Calibration(alpha=1.4, beta=-0.05, gamma=0.0))
    assert h1 + a1 > 2.6
    # identita' in entrambe le varianti
    hi, ai = apply_calibration(1.8, 0.8, Calibration(preserve_total=True))
    assert abs(hi - 1.8) < 1e-12 and abs(ai - 0.8) < 1e-12
    # gamma riscala solo il totale
    hg, ag = apply_calibration(1.8, 0.8, Calibration(gamma=0.1, preserve_total=True))
    assert abs((hg + ag) - 2.6 * math.exp(0.1)) < 1e-12 and abs(hg / ag - 1.8 / 0.8) < 1e-9

    rng = np.random.default_rng(13)
    true = Calibration(alpha=1.25, beta=-0.04, gamma=0.03, preserve_total=True)
    samples = []
    for _ in range(12000):
        lh, la = rng.uniform(0.6, 2.2), rng.uniform(0.5, 1.8)
        th, ta = apply_calibration(lh, la, true)
        samples.append(CalibrationSample(lh, la, 0.0, int(rng.poisson(th)), int(rng.poisson(ta))))
    fitted = fit_calibration(samples, preserve_total=True)
    assert fitted.preserve_total
    assert abs(fitted.alpha - 1.25) < 0.08
    assert abs(fitted.beta + 0.04) < 0.04
    assert abs(fitted.gamma - 0.03) < 0.03
    assert fit_calibration([], preserve_total=True) == Calibration(preserve_total=True)


# --- Passo 2: indici a 360 gradi ------------------------------------------------


def _index_input(mid, day, home="A", away="B", gh=1, ga=1, p=(0.45, 0.27, 0.28), lam=(1.5, 1.1), season="2022/2023"):
    from app.services.cecchino_v3.indices import IndexInput

    m = _form_match(mid, day, home, away, gh, ga, season=season)
    m.eval_eligible = True
    m.phase = "mid"
    return IndexInput(
        match=m,
        prob_home=p[0],
        prob_draw=p[1],
        prob_away=p[2],
        prob_over_2_5=0.5,
        lambda_home=lam[0],
        lambda_away=lam[1],
        home_evidence=30.0,
        away_evidence=30.0,
        specialists={
            "forza": {"home": lam[0], "away": lam[1]},
            "sot": {"home": lam[0], "away": lam[1]},
            "shots": {"home": lam[0], "away": lam[1]},
        },
    )


def test_equilibrium_and_classes():
    from app.services.cecchino_v3.indices import equilibrium_value, percentile_class

    assert equilibrium_value(0.35, 0.35) == 100.0
    assert abs(equilibrium_value(0.6, 0.2) - 50.0) < 1e-12
    assert percentile_class(None) is None
    assert percentile_class(10.0) == "molto_basso"
    assert percentile_class(20.0) == "basso"
    assert percentile_class(59.9) == "medio"
    assert percentile_class(80.0) == "molto_alto"


def test_rolling_percentile_needs_history():
    from app.services.cecchino_v3.constants import INDEX_MIN_HISTORY
    from app.services.cecchino_v3.indices import RollingPercentile

    rp = RollingPercentile()
    for v in range(INDEX_MIN_HISTORY - 1):
        rp.add(float(v))
    assert rp.percentile(10.0) is None
    rp.add(float(INDEX_MIN_HISTORY - 1))
    assert rp.percentile(-1.0) == 0.0
    assert rp.percentile(1e9) == 100.0


def test_reliability_formula():
    from app.services.cecchino_v3.constants import (
        RELIABILITY_EARLY_FACTOR,
        RELIABILITY_NEW_TEAM_FACTOR,
        RELIABILITY_SUPREMACY_SCALE,
        RELIABILITY_TOTAL_SCALE,
    )
    from app.services.cecchino_v3.indices import reliability, specialist_disagreement

    full = reliability(
        home_evidence=40, away_evidence=25, disagreement_supremacy=0.0, disagreement_total=0.0,
        new_team=False, early=False,
    )
    assert full["value"] == 100.0 and full["class"] == "alta"
    half = reliability(
        home_evidence=10, away_evidence=40, disagreement_supremacy=0.0, disagreement_total=0.0,
        new_team=False, early=False,
    )
    assert half["value"] == 50.0 and half["class"] == "media"
    d_sup, d_tot = 0.2, 0.15
    expected = 100.0 / (1 + d_sup / RELIABILITY_SUPREMACY_SCALE + d_tot / RELIABILITY_TOTAL_SCALE)
    expected *= RELIABILITY_NEW_TEAM_FACTOR * RELIABILITY_EARLY_FACTOR
    got = reliability(
        home_evidence=30, away_evidence=30, disagreement_supremacy=d_sup, disagreement_total=d_tot,
        new_team=True, early=True,
    )
    assert abs(got["value"] - round(expected, 1)) < 1e-9 and got["class"] == "bassa"

    sup, tot = specialist_disagreement(
        {"forza": {"home": 2.0, "away": 1.0}, "sot": {"home": 1.0, "away": 1.0}, "shots": {"home": 1.5, "away": 1.0}}
    )
    assert abs(sup - math.log(2.0)) < 1e-12
    assert abs(tot - (math.log(3.0) - math.log(2.0))) < 1e-12
    assert specialist_disagreement({"forza": {"home": 1.0, "away": 1.0}}) == (None, None)


def test_indices_use_only_previous_days_of_same_league():
    from app.services.cecchino_v3.constants import INDEX_MIN_HISTORY
    from app.services.cecchino_v3.indices import compute_indices

    inputs = []
    mid = 1
    for day in range(INDEX_MIN_HISTORY + 20):
        inputs.append(_index_input(mid, day, gh=day % 4, ga=1, lam=(1.0 + (day % 7) / 10, 1.0)))
        mid += 1
    base = compute_indices(inputs)
    first = base[1]
    assert first["pareggio"]["league_draw_rate"] is None and first["intensita_goal"]["percentile"] is None
    target = inputs[INDEX_MIN_HISTORY + 5].match
    assert base[target.lab_match_id]["intensita_goal"]["league_goals_avg"] is not None

    from dataclasses import replace

    # risultati stravolti dal giorno della partita bersaglio in poi
    changed = [
        replace(item, match=replace(item.match, ft_home=9, ft_away=9)) if item.match.day >= target.day else item
        for item in inputs
    ]
    after = compute_indices(changed)
    for item in inputs:
        if item.match.day <= target.day:
            assert base[item.match.lab_match_id] == after[item.match.lab_match_id]


def test_coherence_checks_detect_monotonic_patterns():
    from app.services.cecchino_v3.constants import JUDGE_SEASONS
    from app.services.cecchino_v3.indices import coherence_checks

    classes = ("molto_basso", "basso", "medio", "alto", "molto_alto")
    inputs, indices = [], {}
    mid = 1
    for level, klass in enumerate(classes):
        for k in range(10):
            item = _index_input(mid, level * 10 + k, gh=level, ga=0 if k % 2 else level, season=JUDGE_SEASONS[0])
            inputs.append(item)
            indices[mid] = {
                "intensita_goal": {"class": klass},
                "pareggio": {"class": klass},
                "equilibrio": {"class": klass},
                "affidabilita": {"class": ("bassa", "media", "alta")[min(level, 2)]},
            }
            mid += 1
    checks = {c["code"]: c for c in coherence_checks(inputs, indices, JUDGE_SEASONS)}
    assert checks["C1"]["passed"]  # gol crescono con la classe
    assert [r["n"] for r in checks["C1"]["rows"]] == [10] * 5
    assert not checks["C3"]["passed"]  # favorito non decrescente in questo esempio costruito
