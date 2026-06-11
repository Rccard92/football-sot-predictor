"""Test formule segnali Cecchino — Fase 45 (D48, D54, E51, G57, D60, E60, Dominanza)."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_balance_analysis import compute_dominance_pp
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


def _signals(result: dict, key: str) -> dict[str, str]:
    for row in result["rows"]:
        if row["key"] == key:
            return row["signals"]
    raise KeyError(key)


def _matrix(
    *,
    q1: float,
    qx: float,
    q2: float,
    prob_1: float | None = None,
    prob_x: float | None = None,
    prob_2: float | None = None,
) -> dict:
    return build_signals_matrix(
        q1=q1,
        qx=qx,
        q2=q2,
        sample_home_away_split=16,
        prob_1=prob_1,
        prob_x=prob_x,
        prob_2=prob_2,
    )


def _probs_for_dominance_pp(target_pp: float) -> tuple[float, float, float]:
    """Probabilità decimali con dominanza esatta target_pp (max - seconda)."""
    best = 50.0
    second = best - target_pp
    third = 100.0 - best - second
    return (best / 100.0, second / 100.0, third / 100.0)


# --- D48 ---


@pytest.mark.parametrize(
    ("f36", "dominance_pp", "expected"),
    [
        (2.1, 10.1, "SI"),
        (1.9, 10.1, "NO"),
        (2.1, 9.9, "NO"),
    ],
)
def test_d48_one_excel_d(f36: float, dominance_pp: float, expected: str):
    q1 = 2.0
    q2 = q1 + f36
    qx = (q1 + q2) / 2.0
    p1, px, p2 = _probs_for_dominance_pp(dominance_pp)
    result = _matrix(q1=q1, qx=qx, q2=q2, prob_1=p1, prob_x=px, prob_2=p2)
    assert result["inputs"]["diff_1_2"] == pytest.approx(f36, rel=1e-9)
    assert _signals(result, "one_x")["scala_1x"] == "SI"
    assert _signals(result, "one")["excel_d"] == expected


# --- D54 ---


@pytest.mark.parametrize(
    ("f36", "dominance_pp", "expected"),
    [
        (-2.4, 10.1, "SI"),
        (-2.2, 10.1, "NO"),
        (-2.4, 9.9, "NO"),
    ],
)
def test_d54_two_excel_d(f36: float, dominance_pp: float, expected: str):
    q2 = 2.0
    q1 = q2 - f36
    qx = (q1 + q2) / 2.0
    p1, px, p2 = _probs_for_dominance_pp(dominance_pp)
    result = _matrix(q1=q1, qx=qx, q2=q2, prob_1=p1, prob_x=px, prob_2=p2)
    assert result["inputs"]["diff_1_2"] == pytest.approx(f36, rel=1e-9)
    assert _signals(result, "x_two")["scala_x2"] == "SI"
    assert _signals(result, "two")["excel_d"] == expected


# --- E51 ---


def test_e51_one_x_excel_e_positive():
    result = _matrix(q1=2.00, qx=2.50, q2=3.10)
    assert _signals(result, "one_x")["excel_e"] == "SI"


# --- G57 ---


def test_g57_x_two_excel_g_negative():
    result = _matrix(q1=4.00, qx=4.40, q2=4.90)
    assert _signals(result, "x_two")["excel_g"] == "NO"


def test_g57_x_two_excel_g_positive():
    result = _matrix(q1=5.0, qx=4.0, q2=3.0)
    assert _signals(result, "x_two")["excel_g"] == "SI"


# --- D60 ---


def test_d60_twelve_excel_d_case_a():
    result = _matrix(q1=2.30, qx=4.8, q2=0.70)
    assert result["inputs"]["diff_1_2"] == pytest.approx(-1.6, rel=1e-9)
    assert _signals(result, "twelve")["excel_d"] == "SI"


def test_d60_twelve_excel_d_case_b():
    result = _matrix(q1=0.70, qx=4.8, q2=2.30)
    assert result["inputs"]["diff_1_2"] == pytest.approx(1.6, rel=1e-9)
    assert _signals(result, "twelve")["excel_d"] == "SI"


def test_d60_twelve_excel_d_negative():
    result = _matrix(q1=2.30, qx=4.7, q2=2.30)
    assert _signals(result, "twelve")["excel_d"] == "NO"


# --- E60 ---


@pytest.mark.parametrize(
    ("dominance_pp", "f36", "expected"),
    [
        (10.0, 1.5, "SI"),
        (9.9, 1.5, "NO"),
        (10.0, 1.4, "NO"),
    ],
)
def test_e60_twelve_excel_e(dominance_pp: float, f36: float, expected: str):
    q1 = 2.0
    q2 = q1 + f36
    qx = 4.8
    p1, px, p2 = _probs_for_dominance_pp(dominance_pp)
    result = _matrix(q1=q1, qx=qx, q2=q2, prob_1=p1, prob_x=px, prob_2=p2)
    assert _signals(result, "twelve")["excel_e"] == expected


# --- Dominanza scala ---


def test_dominance_pp_decimal_and_percent_same_scale():
    assert compute_dominance_pp(0.42, 0.35, 0.23) == pytest.approx(7.0, abs=0.01)
    assert compute_dominance_pp(42, 35, 23) == pytest.approx(7.0, abs=0.01)


def test_dominance_pp_threshold_gt_10_vs_gte_10():
    q1, qx, q2 = 2.0, 3.0, 4.1
    p_gt = _probs_for_dominance_pp(10.1)
    p_eq = _probs_for_dominance_pp(10.0)
    p_lt = _probs_for_dominance_pp(9.9)

    assert (
        _signals(
            _matrix(q1=q1, qx=qx, q2=q2, prob_1=p_gt[0], prob_x=p_gt[1], prob_2=p_gt[2]),
            "one",
        )["excel_d"]
        == "SI"
    )
    assert (
        _signals(
            _matrix(q1=q1, qx=qx, q2=q2, prob_1=p_eq[0], prob_x=p_eq[1], prob_2=p_eq[2]),
            "one",
        )["excel_d"]
        == "NO"
    )
    assert (
        _signals(
            _matrix(q1=q1, qx=qx, q2=q2, prob_1=p_lt[0], prob_x=p_lt[1], prob_2=p_lt[2]),
            "one",
        )["excel_d"]
        == "NO"
    )

    assert (
        _signals(
            _matrix(q1=q1, qx=4.8, q2=3.5, prob_1=p_eq[0], prob_x=p_eq[1], prob_2=p_eq[2]),
            "twelve",
        )["excel_e"]
        == "SI"
    )
    assert (
        _signals(
            _matrix(q1=q1, qx=4.8, q2=3.5, prob_1=p_lt[0], prob_x=p_lt[1], prob_2=p_lt[2]),
            "twelve",
        )["excel_e"]
        == "NO"
    )


def test_dominance_missing_probs_blocks_d48_d54_e60():
    result = _matrix(q1=1.2, qx=4.0, q2=8.0)
    assert result["inputs"]["dominance_pp"] is None
    assert _signals(result, "one")["excel_d"] == "NO"
    assert _signals(result, "two")["excel_d"] == "NO"

    result12 = _matrix(q1=2.0, qx=4.8, q2=3.5)
    assert _signals(result12, "twelve")["excel_e"] == "NO"
