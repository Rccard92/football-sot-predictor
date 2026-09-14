"""Test Master Pattern: verdetti, totali, orientamento Over/Under, ricerca V3 senza quota."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import numpy as np

from app.services.master_patterns.constants import (
    ALL_SEASONS,
    DISCOVERY_SEASON,
    MIN_SAMPLE,
    VERDICT_ATTENUATED,
    VERDICT_CONFIRMED,
    VERDICT_INSUFFICIENT,
    VERDICT_REJECTED,
    VERIFY_SEASONS,
)
from app.services.master_patterns.orientation import orient_season, synthetic_market_label
from app.services.master_patterns.scoring import (
    chance_probability,
    is_tested_all,
    is_winner,
    market_verdict,
    synthetic_verdict,
    tally,
    totals,
)


def test_verdicts():
    assert market_verdict(MIN_SAMPLE - 1, 10.0) == VERDICT_INSUFFICIENT
    assert market_verdict(MIN_SAMPLE, 0.1) == VERDICT_CONFIRMED
    assert market_verdict(MIN_SAMPLE, 0.0) == VERDICT_REJECTED
    assert synthetic_verdict(30, 6.0, 1) == VERDICT_CONFIRMED
    assert synthetic_verdict(30, 3.0, 1) == VERDICT_ATTENUATED
    assert synthetic_verdict(30, -6.0, -1) == VERDICT_CONFIRMED
    assert synthetic_verdict(30, 6.0, -1) == VERDICT_REJECTED
    assert synthetic_verdict(10, 20.0, 1) == VERDICT_INSUFFICIENT


def _seasons(verdicts, null_p=0.5):
    out = {DISCOVERY_SEASON: {"n": 40, "wins": 25, "profit_units": 5.0, "n_priced": 40, "avg_quota": 2.0, "verdict": "discovery"}}
    for s, v in zip(VERIFY_SEASONS, verdicts):
        out[s] = {"n": 30, "wins": 16, "profit_units": 2.0, "n_priced": 30, "avg_quota": 2.2, "verdict": v, "null_p": null_p}
    return out


def test_winner_chance_and_tally():
    win = _seasons([VERDICT_CONFIRMED] * 4, null_p=0.3)
    lose = _seasons([VERDICT_CONFIRMED, VERDICT_REJECTED, VERDICT_CONFIRMED, VERDICT_CONFIRMED])
    untested = _seasons([VERDICT_CONFIRMED, VERDICT_INSUFFICIENT, VERDICT_CONFIRMED, VERDICT_CONFIRMED])
    assert is_winner(win) and not is_winner(lose) and not is_winner(untested)
    assert is_tested_all(lose) and not is_tested_all(untested)
    assert math.isclose(chance_probability(win), 0.3**4)
    t = tally([{"seasons": win}, {"seasons": lose}, {"seasons": untested}])
    assert t["tested_all_seasons"] == 2 and t["winners"] == 1
    assert math.isclose(t["expected_by_chance"], round(0.3**4 + 0.5**4, 1))


def test_totals_market_and_synthetic():
    t = totals(_seasons([VERDICT_CONFIRMED] * 4), "market")
    assert t["n"] == 40 + 4 * 30 and t["wins"] == 25 + 4 * 16
    assert math.isclose(t["profit_units"], 5.0 + 4 * 2.0)
    assert math.isclose(t["roi_pct"], round(13.0 / 160 * 100, 2))
    assert math.isclose(t["avg_quota"], round((2.0 * 40 + 2.2 * 120) / 160, 3))
    seasons = {s: {"n": 30, "wins": 20, "deviation_pct": 6.0 + i} for i, s in enumerate(ALL_SEASONS)}
    ts = totals(seasons, "synthetic")
    assert math.isclose(ts["avg_deviation_pct"], 8.0) and "roi_pct" not in ts


def test_orientation_under_side():
    stats = {"n": 40, "wins": 10, "losses": 30, "win_rate_pct": 25.0, "baseline_win_rate_pct": 45.0, "deviation_pct": -20.0}
    under = orient_season(stats, -1)
    assert under["wins"] == 30 and under["losses"] == 10
    assert under["win_rate_pct"] == 75.0 and under["baseline_win_rate_pct"] == 55.0 and under["deviation_pct"] == 20.0
    assert orient_season(stats, 1) == stats
    assert synthetic_market_label("Corner totali", 9.5, -1) == "Corner totali Under 9.5"
    assert synthetic_market_label("Corner totali", 9.5, 1) == "Corner totali Over 9.5"


def _synthetic_rows(n_per_season=300, seed=3):
    from app.services.cecchino_v3.patterns import MatchContext
    from app.services.cecchino_v3.synthetic_patterns import SyntheticRow

    rng = np.random.default_rng(seed)
    rows, contexts = [], {}
    mid = 1
    for s_idx, season in enumerate(ALL_SEASONS):
        for k in range(n_per_season):
            final = k % 5 == 0  # ultime giornate: molti corner
            corners = float(rng.integers(12, 16) if final else rng.integers(5, 10))
            rows.append(
                SyntheticRow(
                    lab_match_id=mid,
                    season_label=season,
                    competition="Serie A",
                    tier="top",
                    match_date=date(2021, 8, 1) + timedelta(days=s_idx * 400 + k % 300),
                    phase="final" if final else "mid",
                    eligible=True,
                    home_team="A",
                    away_team="B",
                    actuals={"total_corners": corners, "total_shots": float(rng.integers(15, 30))},
                    volumes={"shots_home": 12.0, "shots_away": float(rng.uniform(8, 14)), "sot_home": 4.0, "sot_away": 3.0},
                )
            )
            contexts[mid] = MatchContext("medio", "basso", "alto", 3, float(rng.normal()), 0)
            mid += 1
    return rows, contexts


def test_synthetic_discovery_and_validation_find_planted_pattern():
    from app.services.cecchino_v3.synthetic_patterns import (
        build_stat_matrix,
        discover_synthetic,
        expected_volume,
        synthetic_edges,
        validate_synthetic,
    )

    rows, contexts = _synthetic_rows()
    edges = synthetic_edges(rows, contexts, ["total_corners", "total_shots"])
    assert edges["total_corners"]["volume_atteso"] == []  # nessuna stima dei corner dagli agenti
    assert len(edges["total_shots"]["volume_atteso"]) == 4
    assert expected_volume(rows[0], "total_shots") == 12.0 + rows[0].volumes["shots_away"]

    matrix = build_stat_matrix(rows, contexts, "total_corners", edges)
    found = discover_synthetic(matrix, 9.5)
    planted = [p for p in found if p.conditions == [{"column": "fase", "value": "finale"}]]
    assert planted and planted[0].direction == 1
    disc = planted[0].seasons[DISCOVERY_SEASON]
    assert disc["n"] == 60 and math.isclose(disc["win_rate_pct"], 100.0)
    regular = [p for p in found if p.conditions == [{"column": "fase", "value": "stagione"}]]
    assert regular and regular[0].direction == -1  # sotto la media: si gioca Under

    validate_synthetic(matrix, found, VERIFY_SEASONS, 5.0)
    for s in VERIFY_SEASONS:
        assert planted[0].seasons[s]["verdict"] == VERDICT_CONFIRMED
        assert 0.0 <= planted[0].seasons[s]["null_p"] <= 1.0
    assert is_winner(planted[0].seasons)
    json.dumps([p.seasons for p in found])
    combo = matrix.combo_from_conditions(planted[0].conditions)
    assert combo == planted[0].combo
