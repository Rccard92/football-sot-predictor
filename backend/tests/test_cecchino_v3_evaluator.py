"""Test del valutatore di mercato V3 (Passo 3), su dati sintetici."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import numpy as np

from app.services.cecchino_v3.constants import (
    EVALUATOR_MAX_PLAYS_PER_DAY,
    JUDGE_SEASONS,
    WARMUP_SEASON,
)
from app.services.cecchino_v3.evaluator import (
    MarketRow,
    Play,
    book_probabilities,
    combine_walk_forward,
    design,
    fit_logistic,
    playability_exam,
    select_plays,
)

SEASONS = (WARMUP_SEASON, *JUDGE_SEASONS)


def _row(mid, key, *, season=JUDGE_SEASONS[0], day=0, odds=2.0, p_v3=0.5, p_book=0.5, won=True, phase="mid", eligible=True):
    return MarketRow(
        lab_match_id=mid,
        season_label=season,
        competition="Serie A",
        tier="top",
        match_date=date(2022, 9, 1) + timedelta(days=day),
        phase=phase,
        eligible=eligible,
        home_team=f"H{mid}",
        away_team=f"A{mid}",
        market_key=key,
        p_v3=p_v3,
        p_book=p_book,
        odds=odds,
        won=won,
    )


def test_book_probabilities_remove_margin_and_build_double_chance():
    odds = {"home": 2.0, "draw": 3.4, "away": 4.0, "over_25": 1.9, "under_25": 1.95, "dc_1x": None}
    book = book_probabilities(odds)
    assert abs(sum(book[k][1] for k in ("HOME", "DRAW", "AWAY")) - 1.0) < 1e-12
    assert abs(book["OVER_2_5"][1] + book["UNDER_2_5"][1] - 1.0) < 1e-12
    assert book["HOME"][0] == 2.0
    assert abs(book["ONE_X"][1] - (book["HOME"][1] + book["DRAW"][1])) < 1e-12
    assert abs(book["ONE_X"][0] - 1.0 / (1 / 2.0 + 1 / 3.4)) < 1e-12  # quota ricavata dall'1X2
    assert "HOME_PT" not in book and "OVER_1_5" not in book


def _synthetic(n_matches: int, informative: bool, seed: int) -> list[MarketRow]:
    """Mercato binario: il book vede parte della verita', la V3 un'altra parte."""
    rng = np.random.default_rng(seed)
    rows = []
    mid = 1
    for s_idx, season in enumerate(SEASONS):
        for k in range(n_matches):
            common = rng.normal(0, 0.8)
            private = rng.normal(0, 0.5)
            true_logit = common + (private if informative else 0.0)
            p_true = 1 / (1 + np.exp(-true_logit))
            p_book = 1 / (1 + np.exp(-(common + rng.normal(0, 0.1))))
            p_v3 = 1 / (1 + np.exp(-(common + private + rng.normal(0, 0.3))))
            won = bool(rng.random() < p_true)
            rows.append(
                _row(mid, "OVER_2_5", season=season, day=s_idx * 400 + k % 300, odds=round(0.95 / p_book, 3),
                     p_v3=float(p_v3), p_book=float(p_book), won=won)
            )
            mid += 1
    return rows


def test_logistic_detects_information_beyond_the_book():
    rows = _synthetic(3000, informative=True, seed=1)
    x = design(np.array([r.p_book for r in rows]), np.array([r.p_v3 for r in rows]))
    y = np.array([float(r.won) for r in rows])
    fit = fit_logistic(x, y, np.array([r.lab_match_id for r in rows])).summary()
    assert fit["c_low"] > 0.3

    noise = _synthetic(3000, informative=False, seed=2)
    x = design(np.array([r.p_book for r in noise]), np.array([r.p_v3 for r in noise]))
    y = np.array([float(r.won) for r in noise])
    fit = fit_logistic(x, y, np.array([r.lab_match_id for r in noise])).summary()
    assert fit["c_low"] < 0 < fit["c_high"] or abs(fit["c"]) < 0.1


def test_combination_is_walk_forward_without_leak():
    rows = _synthetic(700, informative=True, seed=3)
    base = combine_walk_forward(rows)
    first = [r for r in rows if r.season_label == WARMUP_SEASON]
    assert all((r.lab_match_id, r.market_key) not in base.probability for r in first)
    assert {m["season"] for m in base.models} == set(JUDGE_SEASONS)

    target = JUDGE_SEASONS[1]
    changed = [replace(r, won=not r.won) if r.season_label >= target else r for r in rows]
    after = combine_walk_forward(changed)
    for r in rows:
        if r.season_label <= target and r.season_label != WARMUP_SEASON:
            key = (r.lab_match_id, r.market_key)
            assert base.probability[key] == after.probability[key]
    later = [r for r in rows if r.season_label > target]
    assert any(base.probability[(r.lab_match_id, r.market_key)] != after.probability[(r.lab_match_id, r.market_key)] for r in later)


def test_select_plays_rules():
    rows = [
        # partita 1: due candidati, vince quello con valore piu' alto (AWAY)
        _row(1, "HOME", odds=2.0, p_v3=0.55),
        _row(1, "AWAY", odds=3.0, p_v3=0.40),
        # quota fuori intervallo
        _row(2, "HOME", odds=6.0, p_v3=0.5),
        # valore sotto soglia
        _row(3, "HOME", odds=2.0, p_v3=0.51),
        # partita non idonea
        _row(4, "HOME", odds=2.0, p_v3=0.7, eligible=False),
        # fase finale esclusa per la famiglia
        _row(5, "OVER_2_5", odds=2.0, p_v3=0.7, phase="final"),
        # mercato fuori dall'universo
        _row(6, "HOME_PT", odds=2.0, p_v3=0.7),
    ]
    prob = {(r.lab_match_id, r.market_key): r.p_v3 for r in rows}
    rules = {(JUDGE_SEASONS[0], "FT_OVER_UNDER"): {"excluded": True}}
    plays = select_plays("T", rows, prob, {}, ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5"), rules, JUDGE_SEASONS)
    assert [(p.row.lab_match_id, p.row.market_key) for p in plays] == [(1, "AWAY")]
    assert abs(plays[0].edge - 0.2) < 1e-12 and plays[0].p_eval is None

    many = [_row(i, "HOME", odds=2.0, p_v3=0.6 + i / 1000) for i in range(1, 40)]
    prob = {(r.lab_match_id, r.market_key): r.p_v3 for r in many}
    plays = select_plays("T", many, prob, {}, ("HOME",), {}, JUDGE_SEASONS)
    assert len(plays) == EVALUATOR_MAX_PLAYS_PER_DAY
    assert min(p.row.lab_match_id for p in plays) == 40 - EVALUATOR_MAX_PLAYS_PER_DAY


def test_playability_exam():
    def plays(season, wins, losses, odds=2.2):
        out = []
        for i in range(wins + losses):
            r = _row(i, "HOME", season=season, odds=odds, won=i < wins)
            out.append(Play("T", r, 0.5, 0.5, 0.1))
        return out

    good = [p for s in JUDGE_SEASONS for p in plays(s, 60, 60)]
    exam = playability_exam(good, JUDGE_SEASONS)
    assert exam["G1"] and exam["G3"] and exam["total"]["roi"] > 0
    assert exam["G2"] == (exam["total"]["roi_low"] > 0)
    bad = plays(JUDGE_SEASONS[0], 50, 70) + plays(JUDGE_SEASONS[1], 60, 60) + plays(JUDGE_SEASONS[2], 60, 60)
    assert not playability_exam(bad, JUDGE_SEASONS)["G1"]

