"""Test value gate segnali monitorati Cecchino."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.cecchino.cecchino_signal_value_gate import signal_has_value_from_kpi_context


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
def test_signal_has_value_from_kpi_context(kpi_ctx, passed, reason):
    out_passed, out_reason, meta = signal_has_value_from_kpi_context(kpi_ctx)
    assert out_passed is passed
    assert out_reason == reason
    if passed:
        assert meta["quota_book"] == Decimal(str(kpi_ctx["quota_book"]))
        assert meta["quota_cecchino"] == Decimal(str(kpi_ctx["quota_cecchino"]))
        assert meta["value_delta"] == meta["quota_book"] - meta["quota_cecchino"]
        assert meta["value_edge_pct"] == pytest.approx(
            ((meta["quota_book"] / meta["quota_cecchino"]) - Decimal("1")) * Decimal("100"),
        )


def test_value_edge_pct_computed():
    _, _, meta = signal_has_value_from_kpi_context({"quota_book": 3.40, "quota_cecchino": 3.20})
    assert meta["value_edge_pct"] == pytest.approx(Decimal("6.25"))
