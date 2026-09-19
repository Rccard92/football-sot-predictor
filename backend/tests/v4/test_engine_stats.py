"""Test del motore statistiche V4 su uno storico sintetico (Serie A + Serie B, due stagioni)."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from app.services.cecchino_v3.constants import Hyper, group_of
from app.services.cecchino_v3.data import MatchRecord, annotate_season_context

from app.services.cecchino_v4.constants import STAT_LINES, STAT_SIDES, STATS
from app.services.cecchino_v4.engine_stats import ADOPTED_CONFIG, Target, predict_history, predict_targets
from app.services.cecchino_v4.engine_stats import distribution as dist
from app.services.cecchino_v4.engine_stats.engine import fit_history
from app.services.cecchino_v4.history.football_data import History, MatchExtras

_EPOCH = date(2000, 1, 1)


def _round_robin(teams: list[str]) -> list[tuple[str, str]]:
    n = len(teams)
    rounds = []
    rot = teams[:]
    for _ in range(n - 1):
        pairs = [(rot[i], rot[n - 1 - i]) for i in range(n // 2)]
        rounds.append(pairs)
        rot = [rot[0]] + [rot[-1]] + rot[1:-1]
    second = [[(b, a) for a, b in r] for r in rounds]
    return [p for r in rounds + second for p in r]


def synthetic_history(seed: int = 7) -> History:
    rng = np.random.default_rng(seed)
    comps = {"Serie A": [f"A{i}" for i in range(6)], "Serie B": [f"B{i}" for i in range(6)]}
    strength = {t: rng.normal(0, 0.25) for ts in comps.values() for t in ts}
    matches: list[MatchRecord] = []
    extras: dict[int, MatchExtras] = {}
    mid = 1
    for s_idx, season in enumerate(("2021/2022", "2022/2023")):
        start = date(2021 + s_idx, 8, 20)
        for comp, teams in comps.items():
            level = 1.0 if comp == "Serie A" else 0.85
            fixtures = _round_robin(teams)
            per_round = len(teams) // 2
            for k, (h, a) in enumerate(fixtures):
                d = start + timedelta(days=7 * (k // per_round))
                lam_h = 4.5 * level * math.exp(0.15 + strength[h] - strength[a])
                lam_a = 4.5 * level * math.exp(strength[a] - strength[h])
                sot_h, sot_a = rng.poisson(lam_h), rng.poisson(lam_a)
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
                        ft_home=int(rng.poisson(1.4)),
                        ft_away=int(rng.poisson(1.1)),
                        ht_home=0,
                        ht_away=0,
                        home_shots=int(sot_h + rng.poisson(8)),
                        away_shots=int(sot_a + rng.poisson(7)),
                        home_sot=int(sot_h),
                        away_sot=int(sot_a),
                        home_fouls=int(rng.poisson(12)),
                        away_fouls=int(rng.poisson(12)),
                        home_yellow=int(rng.poisson(2)),
                        away_yellow=int(rng.poisson(2.3)),
                        home_red=int(rng.random() < 0.05),
                        away_red=int(rng.random() < 0.06),
                    )
                )
                extras[mid] = MatchExtras(code="I1" if comp == "Serie A" else "I2", home_corners=int(rng.poisson(5.5)), away_corners=int(rng.poisson(4.5)))
                mid += 1
    matches.sort(key=lambda m: (m.day, m.competition, m.home_team))
    annotate_season_context(matches)
    return History(matches=matches, extras=extras)


@pytest.fixture(scope="module")
def history() -> History:
    return synthetic_history()


@pytest.fixture(scope="module")
def config(tmp_path_factory):
    return replace(
        ADOPTED_CONFIG,
        cache_dir=tmp_path_factory.mktemp("v4_stats_cache"),
        workers=1,
        hyper_grid=(Hyper(xi=0.002, sigma=0.2), Hyper(xi=0.004, sigma=0.1)),
    )


@pytest.fixture(scope="module")
def payloads(history, config):
    return predict_history(history, config, exam={"sot": "superato"})


def test_payload_shape(history, payloads, config):
    assert len(payloads) == len(history.matches)
    p = payloads[history.matches[-1].lab_match_id]
    assert p["engine_version"] == config.version
    assert set(p["stats"]) == set(STATS)
    assert p["stats"]["sot"]["exam"] == "superato"
    assert p["stats"]["corners"]["exam"] == "in_attesa"
    for stat, block in p["stats"].items():
        for side in STAT_SIDES:
            s = block[side]
            for k in ("mean", "dispersion", "division_mean", "rank_for", "rank_against", "teams_in_division", "lines"):
                assert k in s
            assert set(s["lines"]) == {f"{x:g}" for x in STAT_LINES[stat]}
            for cell in s["lines"].values():
                assert 0.0 <= cell["lo"] <= cell["over"] <= cell["hi"] <= 1.0
        assert block["home"]["teams_in_division"] == 6
        assert 1 <= block["home"]["rank_for"] <= 6
        assert 1 <= block["away"]["rank_against"] <= 6
        assert block["total"]["rank_for"] is None


def test_over_plus_under_is_one():
    lines = np.array([0.5, 3.5, 7.5])
    for alpha in (0.0, 0.15):
        over = dist.prob_over(lines, 4.2, alpha)
        under = dist.prob_under(lines, 4.2, alpha)
        assert np.allclose(over + under, 1.0)


def test_lines_monotone(payloads):
    for p in list(payloads.values())[:50]:
        for stat, block in p["stats"].items():
            for side in STAT_SIDES:
                cells = block[side]["lines"]
                probs = [cells[f"{x:g}"]["over"] for x in STAT_LINES[stat]]
                assert all(a >= b for a, b in zip(probs, probs[1:]))


def test_total_is_sum_of_sides(payloads):
    for p in payloads.values():
        for block in p["stats"].values():
            assert block["total"]["mean"] == pytest.approx(block["home"]["mean"] + block["away"]["mean"], abs=2e-3)
            assert block["total"]["division_mean"] == pytest.approx(
                block["home"]["division_mean"] + block["away"]["division_mean"], abs=2e-3
            )


def test_dispersion_non_negative_and_total_moment_matching(history, config, payloads):
    preds = fit_history(history, config)
    for sp in preds.values():
        assert np.all(sp.alpha_h >= 0) and np.all(sp.alpha_a >= 0)
        assert np.all(sp.alpha_t >= 0)
        var_t = dist.variance(sp.mean_t, sp.alpha_t)
        var_sum = dist.variance(sp.run.mean_h, sp.alpha_h) + dist.variance(sp.run.mean_a, sp.alpha_a)
        assert np.allclose(var_t, var_sum, rtol=1e-6, atol=1e-6)
    for p in payloads.values():
        for block in p["stats"].values():
            for side in STAT_SIDES:
                d = block[side]["dispersion"]
                assert d is None or d > 0


def test_predict_targets_excludes_targets_and_future(history, config):
    cut = date(2023, 1, 15)
    targets = [
        Target("t1", "Serie A", "2022/2023", cut, "A0", "A1"),
        Target("t2", "Serie B", "2022/2023", cut, "B2", "Nuova FC"),
    ]
    full = predict_targets(history, targets, config)
    before = History(
        matches=[m for m in history.matches if m.match_date < cut],
        extras=history.extras,
    )
    truncated = predict_targets(before, targets, config)
    assert set(full) == {"t1", "t2"}
    for key in full:
        for stat in STATS:
            for side in STAT_SIDES:
                assert full[key]["stats"][stat][side]["mean"] == pytest.approx(truncated[key]["stats"][stat][side]["mean"], abs=1e-6)
    # squadra mai vista: evidenza zero e intervallo piu' largo di una squadra nota
    unknown = full["t2"]["stats"]["sot"]["away"]
    known = full["t1"]["stats"]["sot"]["away"]
    assert unknown["evidence"] == 0.0
    assert known["evidence"] > 0
    line = "4.5"
    assert (unknown["lines"][line]["hi"] - unknown["lines"][line]["lo"]) > (known["lines"][line]["hi"] - known["lines"][line]["lo"])
    # aggiungere un bersaglio nello stesso giorno non cambia gli altri
    only_t1 = predict_targets(history, targets[:1], config)
    assert only_t1["t1"]["stats"]["shots"]["home"]["mean"] == pytest.approx(full["t1"]["stats"]["shots"]["home"]["mean"], abs=1e-6)


def test_crps_matches_closed_form_for_degenerate_case():
    # media molto piccola: quasi tutta la massa in 0; CRPS(y=0) ≈ 0 e CRPS(y=3) ≈ 3
    c0 = dist.crps(np.array([0.0]), np.array([1e-6]), np.array([0.0]))[0]
    c3 = dist.crps(np.array([3.0]), np.array([1e-6]), np.array([0.0]))[0]
    assert c0 == pytest.approx(0.0, abs=1e-4)
    assert c3 == pytest.approx(3.0, abs=1e-4)
