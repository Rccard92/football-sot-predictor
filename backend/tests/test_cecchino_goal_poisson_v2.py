"""Test modello goal Poisson+empirico v2 — Fase 27."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_constants import (
    CECCHINO_1X2_WEIGHTS,
    CECCHINO_GOAL_MARKET_WEIGHTS,
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_INSUFFICIENT_DATA,
)
from app.services.cecchino.cecchino_fixture_history import (
    GoalContextSlice,
    GoalMarketContexts,
    GoalTotals,
)
from app.services.cecchino.cecchino_goal_poisson_v2 import (
    BLEND_EMPIRICAL,
    BLEND_POISSON,
    FORMULA_V2,
    _CONTEXT_WEIGHT_MAP,
    blend_and_shrink,
    context_reliability,
    empirical_probability_for_context,
    lambda_for_context,
    league_event_probabilities,
    poisson_cumulative,
    poisson_market_probability_ft,
    poisson_market_probability_ht,
    poisson_pmf,
    probability_to_odd,
    weighted_empirical_probability,
    weighted_lambda,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
)


def _totals(sample: int = 10, gf: int = 15, ga: int = 10, **hits) -> GoalTotals:
    return GoalTotals(
        sample=sample,
        goals_for=gf,
        goals_against=ga,
        total_goals=gf + ga,
        over_1_5_hits=hits.get("o15", sample),
        over_2_5_hits=hits.get("o25", sample),
        under_2_5_hits=hits.get("u25", 0),
        under_3_5_hits=hits.get("u35", 0),
        over_pt_0_5_hits=hits.get("pt05", sample),
        over_pt_1_5_hits=hits.get("pt15", 2),
        under_pt_1_5_hits=hits.get("upt15", 3),
        fixture_ids=list(range(sample)),
    )


def _ctx(name: str, label: str, sh: int = 10, sa: int = 10) -> GoalContextSlice:
    return GoalContextSlice(
        name=name,
        label=label,
        home_fixtures=[],
        away_fixtures=[],
        home_totals=_totals(sh),
        away_totals=_totals(sa, gf=12, ga=8),
        target_sample=10,
        min_sample=6,
    )


def test_poisson_pmf_known_values():
    assert poisson_pmf(0, 2.0) == pytest.approx(0.1353, abs=0.001)
    assert poisson_pmf(1, 2.0) == pytest.approx(0.2707, abs=0.001)
    assert poisson_pmf(0, 0) == 1.0


def test_over_15_probability():
    lam = 2.5
    p_under = poisson_cumulative(lam, 1)
    assert poisson_market_probability_ft(SEL_OVER_1_5, lam) == pytest.approx(1 - p_under, abs=0.0001)


def test_over_25_probability():
    lam = 2.5
    p_under = poisson_cumulative(lam, 2)
    assert poisson_market_probability_ft(SEL_OVER_2_5, lam) == pytest.approx(1 - p_under, abs=0.0001)


def test_under_25_probability():
    lam = 2.0
    assert poisson_market_probability_ft(SEL_UNDER_2_5, lam) == pytest.approx(poisson_cumulative(lam, 2), abs=0.0001)


def test_under_35_probability():
    lam = 2.0
    assert poisson_market_probability_ft(SEL_UNDER_3_5, lam) == pytest.approx(poisson_cumulative(lam, 3), abs=0.0001)


def test_over_pt_05_probability():
    lam = 1.2
    assert poisson_market_probability_ht(SEL_OVER_PT_0_5, lam) == pytest.approx(1 - poisson_pmf(0, lam), abs=0.0001)


def test_over_pt_15_probability():
    lam = 1.2
    assert poisson_market_probability_ht(SEL_OVER_PT_1_5, lam) == pytest.approx(
        1 - poisson_cumulative(lam, 1),
        abs=0.0001,
    )


def test_under_pt_15_probability():
    lam = 0.8
    assert poisson_market_probability_ht(SEL_UNDER_PT_1_5, lam) == pytest.approx(poisson_cumulative(lam, 1), abs=0.0001)


def test_lambda_for_context():
    home = _totals(10, gf=20, ga=10)
    away = _totals(10, gf=15, ga=12)
    out = lambda_for_context(home, away)
    assert out["lambda_home"] == pytest.approx((2.0 + 1.2) / 2, abs=0.0001)
    assert out["lambda_away"] == pytest.approx((1.5 + 1.0) / 2, abs=0.0001)
    assert out["lambda_total"] == pytest.approx(out["lambda_home"] + out["lambda_away"], abs=0.0001)


def test_weighted_lambda_uses_context_weights():
    contexts = [
        _ctx("totals", "Totali", 10, 10),
        _ctx("home_away", "Casa/Fuori", 5, 5),
        _ctx("last6_totals", "Ultime 6", 6, 6),
        _ctx("last5_home_away", "Ultime 5", 5, 5),
    ]
    for c in contexts[1:]:
        c.target_sample = 5
        c.min_sample = 3
    lam, _, rel, _ = weighted_lambda(contexts)
    assert lam is not None
    assert lam > 0
    assert rel > 0


def test_context_reliability():
    assert context_reliability(10, 8, 10) == 0.8
    assert context_reliability(12, 15, 10) == 1.0


def test_blend_65_35():
    base = BLEND_POISSON * 0.5 + BLEND_EMPIRICAL * 0.4
    assert blend_and_shrink(0.5, 0.4, 1.0, None) == pytest.approx(base, abs=0.0001)


def test_reliability_shrinkage_toward_league():
    shrunk = blend_and_shrink(0.6, 0.5, 0.5, 0.3)
    base = BLEND_POISSON * 0.6 + BLEND_EMPIRICAL * 0.5
    expected = 0.5 * base + 0.5 * 0.3
    assert shrunk == pytest.approx(expected, abs=0.0001)


def test_probability_to_odd():
    odd, raw, capped, warnings = probability_to_odd(0.5)
    assert odd == 2.0
    assert raw == 0.5
    assert capped == 0.5
    assert not warnings


def test_probability_zero_no_crash():
    odd, _, _, warnings = probability_to_odd(0.0)
    assert odd is None
    assert warnings


def test_over_15_and_over_25_differ_same_lambda():
    lam = 2.3
    p15 = poisson_market_probability_ft(SEL_OVER_1_5, lam)
    p25 = poisson_market_probability_ft(SEL_OVER_2_5, lam)
    assert p15 != p25
    assert p15 > p25


def test_under_25_and_under_35_differ_same_lambda():
    lam = 2.8
    u25 = poisson_market_probability_ft(SEL_UNDER_2_5, lam)
    u35 = poisson_market_probability_ft(SEL_UNDER_3_5, lam)
    assert u25 != u35
    assert u35 > u25


def test_kpi_formula_version_constant():
    assert FORMULA_V2 == "goal_market_poisson_empirical_v2"


def test_league_event_probabilities_empty():
    probs = league_event_probabilities([])
    assert probs[SEL_OVER_1_5] is None


def test_insufficient_contexts_returns_none_lambda():
    bad = GoalContextSlice(
        name="totals",
        label="Totali",
        home_fixtures=[],
        away_fixtures=[],
        home_totals=_totals(2),
        away_totals=_totals(2),
        target_sample=10,
        min_sample=6,
    )
    lam, _, _, warnings = weighted_lambda([bad])
    assert lam is None
    assert any("low_sample" in w for w in warnings)


def test_goal_market_weights_constants():
    assert CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_TOTALS] == 0.10
    assert CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_HOME_AWAY] == 0.20
    assert CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_LAST6_TOTALS] == 0.35
    assert CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_LAST5_HOME_AWAY] == 0.35
    assert sum(CECCHINO_GOAL_MARKET_WEIGHTS.values()) == pytest.approx(1.0)


def test_1x2_weights_unchanged():
    assert CECCHINO_1X2_WEIGHTS[PICCHETTO_KEY_TOTALS] == 0.25
    assert CECCHINO_1X2_WEIGHTS[PICCHETTO_KEY_HOME_AWAY] == 0.20
    assert CECCHINO_1X2_WEIGHTS[PICCHETTO_KEY_LAST6_TOTALS] == 0.35
    assert CECCHINO_1X2_WEIGHTS[PICCHETTO_KEY_LAST5_HOME_AWAY] == 0.20
    assert CECCHINO_1X2_WEIGHTS == FINAL_QUOTA_WEIGHTS


def test_context_weight_map_uses_goal_weights():
    assert _CONTEXT_WEIGHT_MAP["totals"] == 0.10
    assert _CONTEXT_WEIGHT_MAP["home_away"] == 0.20
    assert _CONTEXT_WEIGHT_MAP["last6_totals"] == 0.35
    assert _CONTEXT_WEIGHT_MAP["last5_home_away"] == 0.35


def _four_usable_contexts() -> list[GoalContextSlice]:
    contexts = [
        _ctx("totals", "Totali stagione", 10, 10),
        _ctx("home_away", "Casa/Fuori", 8, 8),
        _ctx("last6_totals", "Ultime 6 totali", 6, 6),
        _ctx("last5_home_away", "Ultime 5 casa/fuori", 5, 5),
    ]
    for c in contexts[1:]:
        c.target_sample = 5
        c.min_sample = 3
    contexts[0].home_totals = _totals(10, gf=10, ga=10)
    contexts[0].away_totals = _totals(10, gf=10, ga=10)
    contexts[1].home_totals = _totals(8, gf=24, ga=8)
    contexts[1].away_totals = _totals(8, gf=8, ga=24)
    contexts[2].home_totals = _totals(6, gf=18, ga=6)
    contexts[2].away_totals = _totals(6, gf=6, ga=18)
    contexts[3].home_totals = _totals(5, gf=20, ga=5)
    contexts[3].away_totals = _totals(5, gf=5, ga=20)
    return contexts


def test_weighted_lambda_ft_uses_goal_weights():
    contexts = _four_usable_contexts()
    lam, rows, rel, _ = weighted_lambda(contexts)
    expected = sum(
        lambda_for_context(c.home_totals, c.away_totals)["lambda_total"]
        * CECCHINO_GOAL_MARKET_WEIGHTS[c.name]
        for c in contexts
    )
    assert lam == pytest.approx(expected, abs=0.0001)
    for row in rows:
        assert row["original_weight"] == CECCHINO_GOAL_MARKET_WEIGHTS[row["name"]]
        assert row["effective_weight"] == pytest.approx(row["original_weight"])
        assert row["weight_renormalized"] is False
    expected_rel = sum(
        context_reliability(c.sample_home, c.sample_away, c.target_sample)
        * CECCHINO_GOAL_MARKET_WEIGHTS[c.name]
        for c in contexts
    )
    assert rel == pytest.approx(expected_rel, abs=0.0001)


def test_weighted_lambda_differs_from_old_1x2_weights():
    contexts = _four_usable_contexts()
    lam_new, _, _, _ = weighted_lambda(contexts)
    lam_old = sum(
        lambda_for_context(c.home_totals, c.away_totals)["lambda_total"]
        * FINAL_QUOTA_WEIGHTS[c.name]
        for c in contexts
    )
    assert lam_new != pytest.approx(lam_old, abs=0.0001)


def test_weight_renormalized_when_context_excluded():
    contexts = _four_usable_contexts()
    contexts[0].home_totals = _totals(2)
    contexts[0].away_totals = _totals(2)
    contexts[0].min_sample = 6
    lam, rows, _, _ = weighted_lambda(contexts)
    totals_row = next(r for r in rows if r["name"] == "totals")
    ha_row = next(r for r in rows if r["name"] == "home_away")
    assert totals_row["effective_weight"] == 0.0
    assert totals_row["weight_renormalized"] is True
    assert ha_row["effective_weight"] == pytest.approx(0.20 / 0.90, abs=0.0001)
    expected = sum(
        lambda_for_context(c.home_totals, c.away_totals)["lambda_total"]
        * (CECCHINO_GOAL_MARKET_WEIGHTS[c.name] / 0.90)
        for c in contexts[1:]
    )
    assert lam == pytest.approx(expected, abs=0.0001)


def test_weighted_empirical_uses_goal_weights(monkeypatch):
    contexts = _four_usable_contexts()
    fake_probs = {
        "totals": 0.10,
        "home_away": 0.20,
        "last6_totals": 0.30,
        "last5_home_away": 0.40,
    }

    def _fake_emp(ctx, market_key, **kwargs):
        return fake_probs[ctx.name]

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_goal_poisson_v2.empirical_probability_for_context",
        _fake_emp,
    )
    emp, rows, _ = weighted_empirical_probability(
        contexts,
        SEL_OVER_1_5,
        home_team_id=1,
        away_team_id=2,
        is_ht=False,
    )
    expected = sum(fake_probs[c.name] * CECCHINO_GOAL_MARKET_WEIGHTS[c.name] for c in contexts)
    assert emp == pytest.approx(expected, abs=0.0001)
    assert all(r["original_weight"] == CECCHINO_GOAL_MARKET_WEIGHTS[r["name"]] for r in rows)
