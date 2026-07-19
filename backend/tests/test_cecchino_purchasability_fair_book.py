"""Test Fair Book panel adapter — Acquistabilità Fase 2."""

from __future__ import annotations

from app.services.cecchino.cecchino_purchasability_fair_book import (
    SOURCE_1X2,
    SOURCE_DC_DERIVED,
    SOURCE_TWO_WAY,
    normalize_exclusive_market,
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)


def _row(market_key: str, quota: float, **extra) -> dict:
    return {
        "market_key": market_key,
        "quota_book": quota,
        "book_source": "betfair",
        **extra,
    }


def test_1x2_fair_sums_to_one():
    rows = [
        _row(SEL_HOME, 2.0),
        _row(SEL_DRAW, 3.5),
        _row(SEL_AWAY, 4.0),
    ]
    fair = resolve_fair_book_for_panel_rows(rows, today_fixture_id=1, snapshot_at="2026-03-01T12:00:00+00:00")
    assert fair[SEL_HOME]["fair_book_probability_verified"] is True
    assert fair[SEL_HOME]["fair_book_probability_source"] == SOURCE_1X2
    total = sum(fair[s]["fair_book_probability"] for s in (SEL_HOME, SEL_DRAW, SEL_AWAY))
    assert abs(total - 1.0) < 1e-9


def test_ou_25_normalized():
    rows = [_row(SEL_OVER_2_5, 1.9), _row(SEL_UNDER_2_5, 2.1)]
    fair = resolve_fair_book_for_panel_rows(rows, today_fixture_id=1, snapshot_at="t")
    assert fair[SEL_OVER_2_5]["fair_book_probability_source"] == SOURCE_TWO_WAY
    assert fair[SEL_OVER_2_5]["fair_book_probability_verified"] is True
    s = fair[SEL_OVER_2_5]["fair_book_probability"] + fair[SEL_UNDER_2_5]["fair_book_probability"]
    assert abs(s - 1.0) < 1e-9


def test_ou_pt_15_normalized():
    rows = [_row(SEL_OVER_PT_1_5, 2.0), _row(SEL_UNDER_PT_1_5, 1.9)]
    fair = resolve_fair_book_for_panel_rows(rows, today_fixture_id=1, snapshot_at="t")
    assert fair[SEL_OVER_PT_1_5]["fair_book_probability_verified"] is True


def test_dc_derived_from_1x2_not_three_way_exclusive():
    rows = [
        _row(SEL_HOME, 2.0),
        _row(SEL_DRAW, 3.5),
        _row(SEL_AWAY, 4.0),
        _row(SEL_ONE_X, 1.4),
        _row(SEL_X_TWO, 1.6),
        _row(SEL_ONE_TWO, 1.3),
    ]
    fair = resolve_fair_book_for_panel_rows(rows, today_fixture_id=1, snapshot_at="t")
    assert fair[SEL_ONE_X]["fair_book_probability_source"] == SOURCE_DC_DERIVED
    assert fair[SEL_ONE_X]["fair_book_probability_verified"] is True
    # DC non normalizzata come tre esiti esclusivi
    dc_sum = (
        fair[SEL_ONE_X]["fair_book_probability"]
        + fair[SEL_X_TWO]["fair_book_probability"]
        + fair[SEL_ONE_TWO]["fair_book_probability"]
    )
    assert abs(dc_sum - 2.0) < 1e-6  # (H+D)+(D+A)+(H+A) = 2*(H+D+A)=2


def test_incomplete_over_15_not_verified():
    rows = [_row(SEL_OVER_1_5, 1.3)]
    fair = resolve_fair_book_for_panel_rows(rows, today_fixture_id=1, snapshot_at="t")
    assert fair[SEL_OVER_1_5]["fair_book_probability_verified"] is False
    assert fair[SEL_OVER_1_5]["raw_implied_probability"] is not None


def test_normalize_exclusive_incomplete():
    norm, over, status = normalize_exclusive_market({SEL_HOME: 2.0}, frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY}))
    assert norm is None
    assert status == "incomplete_market"
