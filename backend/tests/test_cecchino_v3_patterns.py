"""Test della ricerca pattern V3 (protocollo V2) e del movimento di mercato."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import numpy as np

from app.services.cecchino_v3.constants import JUDGE_SEASONS, PATTERN_DISCOVERY_SEASON, PATTERN_MIN_SAMPLE
from app.services.cecchino_v3.evaluator import MarketRow
from app.services.cecchino_v3.patterns import (
    PATTERN_COLUMNS,
    VERDICT_CONFIRMED,
    VERDICT_INSUFFICIENT,
    VERDICT_REJECTED,
    MatchContext,
    NullModel,
    OpeningQuote,
    build_edges,
    build_matrices,
    discover,
    frozen_test,
    market_move_analysis,
    quintile_edges,
    quintile_value,
    validate,
    validation_tally,
)

SEASONS = (PATTERN_DISCOVERY_SEASON, *JUDGE_SEASONS)


def _row(mid, season, key="HOME", *, odds=2.0, p_v3=0.5, p_book=0.5, won=False, day=0, phase="mid", tier="top"):
    return MarketRow(
        lab_match_id=mid,
        season_label=season,
        competition="Serie A",
        tier=tier,
        match_date=date(2021, 8, 1) + timedelta(days=day),
        phase=phase,
        eligible=True,
        home_team=f"H{mid}",
        away_team=f"A{mid}",
        market_key=key,
        p_v3=p_v3,
        p_book=p_book,
        odds=odds,
        won=won,
    )


def test_quintiles_are_frozen_edges():
    edges = quintile_edges([float(v) for v in range(100)])
    assert len(edges) == 4
    assert quintile_value(-5.0, edges) == "Q1"
    assert quintile_value(1000.0, edges) == "Q5"
    assert quintile_value(None, edges) is None
    assert quintile_edges([1.0, 2.0]) == []


def _planted(n_per_season=400, seed=1):
    """'livello=lower' vince sempre alla quota 2 (ROI +100%), il resto perde sempre."""
    rng = np.random.default_rng(seed)
    rows, contexts = [], {}
    mid = 1
    for s_idx, season in enumerate(SEASONS):
        for k in range(n_per_season):
            tier = "lower" if k % 4 == 0 else "top"
            rows.append(
                _row(mid, season, odds=2.0, p_v3=float(rng.uniform(0.2, 0.8)), p_book=0.48,
                     won=tier == "lower", day=s_idx * 400 + k % 300, tier=tier)
            )
            contexts[mid] = MatchContext("medio", "basso", "alto", 3 if k % 2 else 2, float(rng.normal()), 0)
            mid += 1
    return rows, contexts


def test_discovery_finds_planted_pattern_and_respects_rules():
    rows, contexts = _planted()
    edges = build_edges(rows, contexts)
    assert set(edges["HOME"]) == {"prob_v3", "v3_vs_book", "quota", "forma"}
    matrix = build_matrices(rows, contexts, edges)["HOME"]
    found = discover(matrix)
    labels = {p.label for p in found}
    assert "livello=lower" in labels
    assert all(p.discovery["n"] >= PATTERN_MIN_SAMPLE and p.discovery["roi"] > 0 for p in found)
    assert all(len({c for c, _ in p.combo}) == p.size for p in found)
    assert len({frozenset(p.combo) for p in found}) == len(found)
    assert all("livello=lower" in p.label for p in found)  # nessun altro gruppo e' in utile
    assert any(p.size == 3 for p in found)


def test_validation_verdicts_null_and_frozen_test():
    rows, contexts = _planted()
    edges = build_edges(rows, contexts)
    matrices = build_matrices(rows, contexts, edges)
    matrix = matrices["HOME"]
    found = discover(matrix)
    validate(matrix, found, JUDGE_SEASONS)
    lower = next(p for p in found if p.label == "livello=lower")
    for s in JUDGE_SEASONS:
        assert lower.seasons[s]["verdict"] == VERDICT_CONFIRMED
        assert 0.0 <= lower.seasons[s]["null_p"] <= 1.0
    tally = validation_tally(found, JUDGE_SEASONS)
    assert tally["persistence"]["confirmed"] == tally["persistence"]["tested"]

    frozen = frozen_test(matrices, found)
    lower_rows = [r for r in rows if r.season_label == "2024/2025" and r.tier == "lower"]
    assert frozen["bets"] == len(lower_rows)  # una giocata per partita anche con piu' pattern
    assert math.isclose(frozen["roi_pct"], 100.0)
    assert frozen["pooled_pattern_bets"] >= frozen["bets"]


def test_null_model_matches_margin():
    rng = np.random.default_rng(3)
    won = rng.random(4000) < 0.5
    fair = np.where(won, 1.0, -1.0)  # quota 2 equa
    null = NullModel(fair)
    assert 0.35 < null.p_roi_positive(400) < 0.6
    margin = np.where(won, 0.8, -1.0)  # quota 1,8: margine alto
    assert NullModel(margin).p_roi_positive(2000) < 0.05
    assert null.p_roi_positive(0) is None and null.p_roi_positive(10**6) is None


def test_small_validation_sample_is_insufficient():
    rows, contexts = [], {}
    mid = 1
    for s_idx, season in enumerate(SEASONS):
        count = 200 if season == PATTERN_DISCOVERY_SEASON else 30
        for k in range(count):
            tier = "lower" if k % 3 == 0 else "top"  # in verifica: 10 partite 'lower' (< 20)
            rows.append(_row(mid, season, won=tier == "lower", day=s_idx * 400 + k, tier=tier))
            contexts[mid] = MatchContext(None, None, None, None, None, None)
            mid += 1
    matrix = build_matrices(rows, contexts, build_edges(rows, contexts))["HOME"]
    lower = [p for p in discover(matrix) if p.label == "livello=lower"]
    validate(matrix, lower, JUDGE_SEASONS)
    assert lower and all(lower[0].seasons[s]["verdict"] == VERDICT_INSUFFICIENT for s in JUDGE_SEASONS)
    assert lower[0].seasons[JUDGE_SEASONS[0]]["null_p"] is None
    assert VERDICT_REJECTED != VERDICT_CONFIRMED and PATTERN_COLUMNS[0] == "prob_v3"


def test_run_patterns_end_to_end_is_serializable():
    from app.services.cecchino_v3.pattern_service import _pattern_record, run_patterns

    rows, contexts = _planted(n_per_season=300, seed=4)
    opening = {(r.lab_match_id, r.market_key): OpeningQuote(odds=2.1, p_book=0.47) for r in rows}
    summary, patterns, _ = run_patterns(rows, contexts, opening)
    json.dumps(summary)
    json.dumps([{k: v for k, v in _pattern_record(1, p).items() if k != "discovery_roi"} for p in patterns])
    assert summary["patterns"]["discovered"] == len(patterns) > 0
    assert summary["exam"]["P3"] and summary["frozen"]["patterns"] > 0
    assert {t["family"] for t in summary["market_move"]["table"]} == {"FT_1X2", "OU_2_5"}


def test_market_move_detects_moves_toward_v3():
    rng = np.random.default_rng(9)
    rows, opening = [], {}
    mid = 1
    for s_idx, season in enumerate(JUDGE_SEASONS):
        for k in range(800):
            p_open = float(rng.uniform(0.25, 0.6))
            p_v3 = float(np.clip(p_open + rng.normal(0, 0.05), 0.05, 0.95))
            p_close = float(np.clip(p_open + 0.4 * (p_v3 - p_open) + rng.normal(0, 0.01), 0.05, 0.95))
            for key in ("HOME", "OVER_2_5"):
                rows.append(_row(mid, season, key, odds=0.95 / p_close, p_v3=p_v3, p_book=p_close, day=s_idx * 400 + k % 300))
                opening[(mid, key)] = OpeningQuote(odds=0.95 / p_open, p_book=p_open)
            mid += 1
    out = market_move_analysis(rows, opening)
    json.dumps(out)
    assert out["passed"]
    assert all(0.25 < t["beta"] < 0.55 for t in out["table"] if t["family"] == "FT_1X2")
