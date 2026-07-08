"""Test quota Cecchino X PT (DRAW_PT) — formula empirica HT draw."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_constants import (
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
)
from app.services.cecchino.cecchino_fixture_history import (
    CONTEXT_KEY_HOME_AWAY,
    CONTEXT_KEY_LAST5_HOME_AWAY,
    CONTEXT_KEY_LAST6_TOTALS,
    CONTEXT_KEY_TOTALS,
    GoalContextSlice,
    GoalMarketContexts,
    GoalTotals,
    aggregate_halftime_goal_totals,
)
from app.services.cecchino.cecchino_goal_poisson_v2 import (
    FORMULA_DRAW_PT_V1,
    calculate_first_half_draw_market_v1,
    shrink_empirical_only,
)
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW_PT


def _ht_totals(sample: int, *, draw_hits: int) -> GoalTotals:
    return GoalTotals(
        sample=sample,
        goals_for=sample,
        goals_against=sample,
        total_goals=sample * 2,
        over_1_5_hits=sample,
        over_2_5_hits=0,
        under_2_5_hits=sample,
        under_3_5_hits=sample,
        over_pt_0_5_hits=sample,
        over_pt_1_5_hits=0,
        under_pt_1_5_hits=sample,
        halftime_draw_hits=draw_hits,
        fixture_ids=list(range(sample)),
    )


def _ctx(name: str, label: str, *, draw_hits: int = 3) -> GoalContextSlice:
    return GoalContextSlice(
        name=name,
        label=label,
        home_fixtures=[],
        away_fixtures=[],
        home_totals=_ht_totals(10, draw_hits=draw_hits),
        away_totals=_ht_totals(10, draw_hits=draw_hits),
        target_sample=10,
        min_sample=6,
    )


def _contexts() -> GoalMarketContexts:
    return GoalMarketContexts(
        totals=_ctx(CONTEXT_KEY_TOTALS, PICCHETTO_KEY_TOTALS),
        home_away=_ctx(CONTEXT_KEY_HOME_AWAY, PICCHETTO_KEY_HOME_AWAY),
        last6_totals=_ctx(CONTEXT_KEY_LAST6_TOTALS, PICCHETTO_KEY_LAST6_TOTALS),
        last5_home_away=_ctx(CONTEXT_KEY_LAST5_HOME_AWAY, PICCHETTO_KEY_LAST5_HOME_AWAY),
        ht_totals=_ctx(CONTEXT_KEY_TOTALS, PICCHETTO_KEY_TOTALS),
        ht_home_away=_ctx(CONTEXT_KEY_HOME_AWAY, PICCHETTO_KEY_HOME_AWAY),
        ht_last6_totals=_ctx(CONTEXT_KEY_LAST6_TOTALS, PICCHETTO_KEY_LAST6_TOTALS),
        ht_last5_home_away=_ctx(CONTEXT_KEY_LAST5_HOME_AWAY, PICCHETTO_KEY_LAST5_HOME_AWAY),
        home_team_id=1,
        away_team_id=2,
    )


def test_calculate_draw_pt_produces_numeric_odd():
    out = calculate_first_half_draw_market_v1(_contexts(), {SEL_DRAW_PT: 0.42})
    assert out["market_key"] == SEL_DRAW_PT
    assert out["formula_version"] == FORMULA_DRAW_PT_V1
    assert out["final_odd"] is not None
    assert out["final_odd"] > 1.0
    assert out["status"] in (STATUS_AVAILABLE, STATUS_PARTIAL_LOW_SAMPLE)
    assert out["summary"]["empirical_probability"] is not None
    assert out["contexts"]


def test_calculate_draw_pt_zero_probability_insufficient():
    empty = GoalMarketContexts(
        totals=_ctx(CONTEXT_KEY_TOTALS, PICCHETTO_KEY_TOTALS, draw_hits=0),
        home_away=_ctx(CONTEXT_KEY_HOME_AWAY, PICCHETTO_KEY_HOME_AWAY, draw_hits=0),
        last6_totals=_ctx(CONTEXT_KEY_LAST6_TOTALS, PICCHETTO_KEY_LAST6_TOTALS, draw_hits=0),
        last5_home_away=_ctx(CONTEXT_KEY_LAST5_HOME_AWAY, PICCHETTO_KEY_LAST5_HOME_AWAY, draw_hits=0),
        ht_totals=GoalContextSlice(
            name=CONTEXT_KEY_TOTALS,
            label=PICCHETTO_KEY_TOTALS,
            home_fixtures=[],
            away_fixtures=[],
            home_totals=_ht_totals(2, draw_hits=0),
            away_totals=_ht_totals(2, draw_hits=0),
            target_sample=10,
            min_sample=6,
        ),
        ht_home_away=GoalContextSlice(
            name=CONTEXT_KEY_HOME_AWAY,
            label=PICCHETTO_KEY_HOME_AWAY,
            home_fixtures=[],
            away_fixtures=[],
            home_totals=_ht_totals(2, draw_hits=0),
            away_totals=_ht_totals(2, draw_hits=0),
            target_sample=10,
            min_sample=6,
        ),
        ht_last6_totals=GoalContextSlice(
            name=CONTEXT_KEY_LAST6_TOTALS,
            label=PICCHETTO_KEY_LAST6_TOTALS,
            home_fixtures=[],
            away_fixtures=[],
            home_totals=_ht_totals(2, draw_hits=0),
            away_totals=_ht_totals(2, draw_hits=0),
            target_sample=10,
            min_sample=6,
        ),
        ht_last5_home_away=GoalContextSlice(
            name=CONTEXT_KEY_LAST5_HOME_AWAY,
            label=PICCHETTO_KEY_LAST5_HOME_AWAY,
            home_fixtures=[],
            away_fixtures=[],
            home_totals=_ht_totals(2, draw_hits=0),
            away_totals=_ht_totals(2, draw_hits=0),
            target_sample=10,
            min_sample=6,
        ),
        home_team_id=1,
        away_team_id=2,
    )
    out = calculate_first_half_draw_market_v1(empty, {SEL_DRAW_PT: 0.42})
    assert out["status"] == STATUS_INSUFFICIENT_DATA
    assert out["final_odd"] is None


def test_shrinkage_uses_league_probability():
    empirical = 0.30
    league = 0.45
    rel = 0.5
    blended = shrink_empirical_only(empirical, rel, league)
    assert blended == pytest.approx(0.5 * empirical + 0.5 * league)


def test_halftime_aggregate_counts_draw_hits():
    from types import SimpleNamespace

    fx = SimpleNamespace(
        id=1,
        home_team_id=10,
        away_team_id=20,
        raw_json={"score": {"halftime": {"home": 1, "away": 1}}},
    )
    totals = aggregate_halftime_goal_totals([fx], 10)
    assert totals.halftime_draw_hits == 1
