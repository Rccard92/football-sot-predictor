"""Test helper Decimal canonico per formule Segnali Cecchino."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.cecchino.cecchino_signal_decimal import (
    SIGNAL_FORMULA_DECIMAL_QUANTUM,
    canonical_signal_decimal,
)


@pytest.mark.parametrize(
    "value",
    [None, True, False, "abc", "not-a-number", float("nan"), float("inf"), float("-inf")],
)
def test_canonical_rejects_invalid(value):
    assert canonical_signal_decimal(value) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2.7999, "2.80"),
        (2.8049, "2.80"),
        (2.8050, "2.81"),
        (2.904, "2.90"),
        (2.905, "2.91"),
        (3.504, "3.50"),
        (3.505, "3.51"),
        (0, "0.00"),
        (0.0, "0.00"),
        (-1.205, "-1.21"),
        (-1.2050, "-1.21"),
        (-1.2049, "-1.20"),
        ("2.8050", "2.81"),
        (Decimal("2.8050"), "2.81"),
    ],
)
def test_canonical_round_half_up(value, expected: str):
    result = canonical_signal_decimal(value)
    assert result is not None
    assert isinstance(result, Decimal)
    assert format(result, "f") == expected
    assert result == Decimal(expected)


def test_quantum_is_one_cent():
    assert SIGNAL_FORMULA_DECIMAL_QUANTUM == Decimal("0.01")
