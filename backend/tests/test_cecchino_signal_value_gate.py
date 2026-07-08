"""Test value gate segnali monitorati Cecchino — soglie minime quota book."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.cecchino.cecchino_selection_keys import (
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_signal_value_gate import (
    DEACTIVATION_REASON_BOOK_BELOW_MIN,
    VALUE_REASON_BOOK_BELOW_MIN,
    deactivation_reason_for_value_gate,
    signal_has_value_from_kpi_context,
)


@pytest.mark.parametrize(
    ("kpi_ctx", "passed", "reason"),
    [
        ({}, False, "missing_quota_book"),
        ({"quota_cecchino": 3.20}, False, "missing_quota_book"),
        ({"quota_book": 3.40}, False, "missing_quota_cecchino"),
        ({"quota_book": 0, "quota_cecchino": 3.20}, False, "invalid_quota_book"),
        ({"quota_book": -1, "quota_cecchino": 3.20}, False, "invalid_quota_book"),
        ({"quota_book": 3.40, "quota_cecchino": 0}, False, "invalid_quota_cecchino"),
        ({"quota_book": 3.40, "quota_cecchino": -2}, False, "invalid_quota_cecchino"),
        ({"quota_book": 3.40, "quota_cecchino": 3.20}, True, "value_ok"),
        ({"quota_book": 3.20, "quota_cecchino": 3.20}, True, "value_ok"),
        ({"quota_book": 2.90, "quota_cecchino": 3.20}, False, "no_value_book_below_cecchino"),
    ],
)
def test_signal_has_value_from_kpi_context_basic(kpi_ctx, passed, reason):
    out_passed, out_reason, meta = signal_has_value_from_kpi_context(kpi_ctx)
    assert out_passed is passed
    assert out_reason == reason
    if passed:
        assert meta["quota_book"] == Decimal(str(kpi_ctx["quota_book"]))
        assert meta["quota_cecchino"] == Decimal(str(kpi_ctx["quota_cecchino"]))
        assert meta["value_delta"] == meta["quota_book"] - meta["quota_cecchino"]


def test_value_edge_pct_computed():
    _, _, meta = signal_has_value_from_kpi_context({"quota_book": 3.40, "quota_cecchino": 3.20})
    assert meta["value_edge_pct"] == pytest.approx(Decimal("6.25"))


def test_x_passes_with_min_threshold():
    passed, reason, meta = signal_has_value_from_kpi_context(
        {"quota_book": 3.10, "quota_cecchino": 2.90},
        target_market_key=SEL_DRAW,
    )
    assert passed is True
    assert reason == "value_ok"
    assert meta["min_book_odd"] == Decimal("3.00")
    assert meta["min_book_odd_delta"] == Decimal("0.10")


def test_x_fails_below_min_threshold():
    passed, reason, meta = signal_has_value_from_kpi_context(
        {"quota_book": 2.95, "quota_cecchino": 2.80},
        target_market_key=SEL_DRAW,
    )
    assert passed is False
    assert reason == VALUE_REASON_BOOK_BELOW_MIN
    assert meta["min_book_odd"] == Decimal("3.00")


def test_x_fails_below_cecchino_despite_min_threshold():
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 3.10, "quota_cecchino": 3.20},
        target_market_key=SEL_DRAW,
    )
    assert passed is False
    assert reason == "no_value_book_below_cecchino"


def test_x_pt_passes():
    passed, reason, meta = signal_has_value_from_kpi_context(
        {"quota_book": 1.95, "quota_cecchino": 1.80},
        target_market_key=SEL_DRAW_PT,
    )
    assert passed is True
    assert reason == "value_ok"
    assert meta["min_book_odd"] == Decimal("1.90")


def test_x_pt_fails_below_min_threshold():
    passed, reason, meta = signal_has_value_from_kpi_context(
        {"quota_book": 1.85, "quota_cecchino": 1.70},
        target_market_key=SEL_DRAW_PT,
    )
    assert passed is False
    assert reason == VALUE_REASON_BOOK_BELOW_MIN
    assert meta["min_book_odd"] == Decimal("1.90")


def test_one_x_passes_at_threshold():
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 1.37, "quota_cecchino": 1.30},
        target_market_key=SEL_ONE_X,
    )
    assert passed is True
    assert reason == "value_ok"


def test_x_two_fails_below_threshold():
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 1.44, "quota_cecchino": 1.30},
        target_market_key=SEL_X_TWO,
    )
    assert passed is False
    assert reason == VALUE_REASON_BOOK_BELOW_MIN


def test_one_two_passes_at_threshold():
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 1.37, "quota_cecchino": 1.30},
        target_market_key=SEL_ONE_TWO,
    )
    assert passed is True
    assert reason == "value_ok"


def test_under_25_fails_below_threshold():
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 1.95, "quota_cecchino": 1.80},
        target_market_key=SEL_UNDER_2_5,
    )
    assert passed is False
    assert reason == VALUE_REASON_BOOK_BELOW_MIN


def test_over_25_passes_at_threshold():
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 1.85, "quota_cecchino": 1.70},
        target_market_key=SEL_OVER_2_5,
    )
    assert passed is True
    assert reason == "value_ok"


def test_market_without_threshold_uses_only_cecchino_value():
    passed, reason, meta = signal_has_value_from_kpi_context(
        {"quota_book": 1.50, "quota_cecchino": 1.40},
        target_market_key=SEL_HOME,
    )
    assert passed is True
    assert reason == "value_ok"
    assert meta["min_book_odd"] is None
    assert meta["min_book_odd_delta"] is None


def test_meta_includes_min_book_odd_fields():
    _, _, meta = signal_has_value_from_kpi_context(
        {"quota_book": 3.10, "quota_cecchino": 2.90},
        target_market_key=SEL_DRAW,
    )
    assert meta["target_market_key"] == SEL_DRAW
    assert meta["min_book_odd"] == Decimal("3.00")
    assert meta["min_book_odd_delta"] == Decimal("0.10")


def test_deactivation_reason_for_min_threshold():
    assert deactivation_reason_for_value_gate(VALUE_REASON_BOOK_BELOW_MIN) == DEACTIVATION_REASON_BOOK_BELOW_MIN
    assert deactivation_reason_for_value_gate("no_value_book_below_cecchino") == "no_value_book_below_cecchino"
