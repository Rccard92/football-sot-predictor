"""Test parità matrice segnali SI/NO — valori esempio Excel."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE, STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


def _signals_by_key(result: dict, key: str) -> dict[str, str]:
    for row in result["rows"]:
        if row["key"] == key:
            return row["signals"]
    raise KeyError(key)


def test_excel_example_parity():
    q1 = 2.4066666666666667
    qx = 2.5133333333333332
    q2 = 5.7666666666666675
    result = build_signals_matrix(q1=q1, qx=qx, q2=q2, sample_home_away_split=16)

    assert result["status"] == STATUS_AVAILABLE
    assert result["inputs"]["avg_q"] == pytest.approx(3.5622222222222226, rel=1e-9)
    assert result["inputs"]["diff_1_2"] == pytest.approx(3.3600000000000008, rel=1e-9)

    under = _signals_by_key(result, "under_under_pt")
    assert under == {"excel_d": "NO", "excel_e": "NO", "excel_f": "NO", "excel_g": "NO"}

    draw = _signals_by_key(result, "draw")
    assert draw == {"excel_d": "NO", "excel_e": "NO", "excel_f": "NO", "excel_g": "NO"}

    over = _signals_by_key(result, "over_over_pt")
    assert over == {"excel_d": "NO", "excel_e": "NO", "excel_f": "NO", "excel_g": "NO"}

    one = _signals_by_key(result, "one")
    assert one == {"excel_d": "NO"}

    one_x = _signals_by_key(result, "one_x")
    assert one_x == {
        "excel_d": "NO",
        "excel_e": "NO",
        "excel_f": "NO",
        "excel_g": "NO",
        "scala_1x": "SI",
    }

    two = _signals_by_key(result, "two")
    assert two == {"excel_d": "NO"}

    x_two = _signals_by_key(result, "x_two")
    assert x_two == {
        "excel_d": "NO",
        "excel_e": "NO",
        "excel_f": "NO",
        "excel_g": "NO",
        "scala_x2": "NO",
    }

    twelve = _signals_by_key(result, "twelve")
    assert twelve == {"excel_d": "NO", "excel_e": "NO"}

    rel = result["reliability"]
    assert rel["sample"] == 16
    assert rel["index"] == pytest.approx(0.8, rel=1e-9)
    assert rel["status"] == "OK"
    assert rel["level"] == "ALTA"


def test_missing_quotas_insufficient_data():
    result = build_signals_matrix(q1=None, qx=2.5, q2=5.0, sample_home_away_split=10)
    assert result["status"] == STATUS_INSUFFICIENT_DATA
    assert result["rows"] == []
    assert "signals_matrix:missing_final_quotas" in result["warnings"]


def test_low_sample_reliability():
    result = build_signals_matrix(q1=2.4, qx=2.5, q2=5.7, sample_home_away_split=5)
    rel = result["reliability"]
    assert rel["sample"] == 5
    assert rel["index"] == pytest.approx(0.25, rel=1e-9)
    assert rel["status"] == "NO BET"
    assert rel["level"] == "BASSA"


@pytest.mark.parametrize(
    ("q1", "q2", "under_odd", "expected"),
    [
        (2.00, 2.30, 1.80, "NO"),  # q1 < q2
        (2.30, 2.00, 1.80, "SI"),
        (2.00, 2.00, 2.00, "SI"),
        (2.30, 2.00, 2.10, "NO"),  # under_odd > 2
        (2.30, 2.00, None, "NO"),  # under_odd assente
        (3.00, 2.00, 1.80, "NO"),  # F36 fuori range
    ],
)
def test_under_excel_d_d39_formula(q1: float, q2: float, under_odd: float | None, expected: str):
    result = build_signals_matrix(
        q1=q1,
        qx=3.2,
        q2=q2,
        sample_home_away_split=16,
        under_2_5_cecchino_odd=under_odd,
    )
    assert result["status"] == STATUS_AVAILABLE
    under = _signals_by_key(result, "under_under_pt")
    assert under["excel_d"] == expected
    assert result["inputs"]["diff_1_2"] == pytest.approx(q2 - q1, rel=1e-9)
    assert result["inputs"]["under_2_5_cecchino_odd"] == under_odd


@pytest.mark.parametrize(
    ("q1", "q2", "expected"),
    [
        (2.00, 2.30, "NO"),  # range OK ma q1 < q2
        (2.30, 2.00, "SI"),  # range OK e q1 >= q2 (diff=-0.3)
        (2.00, 2.00, "SI"),  # parità quote
        (3.00, 2.00, "NO"),  # F36 = -1.0 fuori ±0.80
        (2.00, 2.7999, "NO"),  # q1 < q2 anche se |F36|<0.80
    ],
)
def test_draw_excel_d_d42_formula(q1: float, q2: float, expected: str):
    result = build_signals_matrix(q1=q1, qx=3.2, q2=q2, sample_home_away_split=16)
    assert result["status"] == STATUS_AVAILABLE
    draw = _signals_by_key(result, "draw")
    assert draw["excel_d"] == expected
    assert result["inputs"]["diff_1_2"] == pytest.approx(q2 - q1, rel=1e-9)
    assert result["formula_version"] == "cecchino_signals_matrix_v2_draw_dfg"


@pytest.mark.parametrize(
    ("q1", "q2", "expected"),
    [
        (2.7999, 2.0, "SI"),  # F36 = -0.7999, stretti OK
        (2.8001, 2.0, "NO"),  # F36 ≈ -0.8001 → non >
        (2.0, 2.7999, "NO"),  # q1 < q2
        (2.0, 2.8001, "NO"),  # F36 ≈ 0.8001 → non <
    ],
)
def test_draw_excel_d_d42_v2_boundaries(q1: float, q2: float, expected: str):
    result = build_signals_matrix(q1=q1, qx=3.2, q2=q2, sample_home_away_split=16)
    draw = _signals_by_key(result, "draw")
    assert draw["excel_d"] == expected


@pytest.mark.parametrize(
    ("q1", "qx", "q2", "expected"),
    [
        (2.00, 2.30, 2.40, "NO"),  # q1 < q2
        (2.40, 2.90, 2.00, "SI"),  # qx <= 2.90, F36 in ±1.70
        (2.00, 2.30, 2.00, "SI"),
        (2.40, 2.9001, 2.00, "NO"),  # qx > 2.90
        (4.00, 2.30, 2.00, "NO"),  # F36 = -2.0 < -1.70
        (2.6999, 2.90, 1.00, "SI"),  # F36 ≈ -1.6999 inclusivo
        (3.6999, 2.90, 2.00, "SI"),  # F36 ≈ -1.6999
        (2.71, 2.90, 1.00, "NO"),  # F36 = -1.71
        (2.00, 2.90, 3.71, "NO"),  # F36 = 1.71 and q1 < q2
        (2.00, 2.90, 3.70, "NO"),  # F36=1.70 but q1 < q2
    ],
)
def test_draw_excel_f_f42_formula(q1: float, qx: float, q2: float, expected: str):
    result = build_signals_matrix(q1=q1, qx=qx, q2=q2, sample_home_away_split=16)
    assert result["status"] == STATUS_AVAILABLE
    draw = _signals_by_key(result, "draw")
    assert draw["excel_f"] == expected
    assert result["inputs"]["diff_1_2"] == pytest.approx(q2 - q1, rel=1e-9)


@pytest.mark.parametrize(
    ("q1", "qx", "q2", "expected"),
    [
        (2.00, 3.00, 2.30, "NO"),  # q1 < q2
        (2.30, 3.00, 2.00, "SI"),
        (2.30, 3.30, 2.00, "NO"),  # qx >= 3.3
        (3.80, 3.00, 2.00, "NO"),  # diff = -1.8, fuori range E
        (2.00, 3.00, 3.60, "NO"),  # diff = 1.6, fuori range E
    ],
)
def test_draw_excel_e_e42_formula(q1: float, qx: float, q2: float, expected: str):
    result = build_signals_matrix(q1=q1, qx=qx, q2=q2, sample_home_away_split=16)
    assert result["status"] == STATUS_AVAILABLE
    draw = _signals_by_key(result, "draw")
    assert draw["excel_e"] == expected
    assert result["inputs"]["diff_1_2"] == pytest.approx(q2 - q1, rel=1e-9)


@pytest.mark.parametrize(
    ("q1", "qx", "q2", "expected"),
    [
        (2.00, 2.90, 2.30, "NO"),  # q1 < q2
        (2.30, 3.50, 2.00, "SI"),  # qx <= 3.50, F36 in ±1.20
        (2.30, 3.5001, 2.00, "NO"),  # qx > 3.50
        (3.50, 2.90, 2.00, "NO"),  # F36 = -1.50 < -1.20
        (3.1999, 3.50, 2.00, "SI"),  # F36 ≈ -1.1999 inclusivo
        (2.21, 3.50, 1.00, "NO"),  # F36 = -1.21
        (2.1999, 3.50, 1.00, "SI"),  # F36 ≈ -1.1999
    ],
)
def test_draw_excel_g_g42_formula(q1: float, qx: float, q2: float, expected: str):
    result = build_signals_matrix(q1=q1, qx=qx, q2=q2, sample_home_away_split=16)
    assert result["status"] == STATUS_AVAILABLE
    draw = _signals_by_key(result, "draw")
    assert draw["excel_g"] == expected
    assert result["inputs"]["diff_1_2"] == pytest.approx(q2 - q1, rel=1e-9)


@pytest.mark.parametrize(
    ("q1", "qx", "q2", "under_odd", "expected"),
    [
        (2.00, 2.80, 2.30, 1.80, "NO"),  # q1 < q2
        (2.30, 2.80, 2.00, 1.80, "SI"),
        (2.30, 2.80, 2.00, 2.10, "NO"),  # under_odd > 2
        (2.30, 2.80, 2.00, None, "NO"),  # under_odd assente
        (2.30, 3.10, 2.00, 1.80, "NO"),  # qx > 3
    ],
)
def test_under_excel_f_f39_formula(
    q1: float, qx: float, q2: float, under_odd: float | None, expected: str
):
    result = build_signals_matrix(
        q1=q1,
        qx=qx,
        q2=q2,
        sample_home_away_split=16,
        under_2_5_cecchino_odd=under_odd,
    )
    assert result["status"] == STATUS_AVAILABLE
    under = _signals_by_key(result, "under_under_pt")
    assert under["excel_f"] == expected
    assert result["inputs"]["diff_1_2"] == pytest.approx(q2 - q1, rel=1e-9)
    assert result["inputs"]["under_2_5_cecchino_odd"] == under_odd


@pytest.mark.parametrize(
    ("q1", "qx", "q2", "under_odd", "expected"),
    [
        (2.00, 3.50, 2.30, 1.80, "NO"),  # q1 < q2
        (2.30, 3.50, 2.00, 1.80, "SI"),
        (2.30, 3.50, 2.00, 2.10, "NO"),  # under_odd > 2
        (2.30, 3.50, 2.00, None, "NO"),  # under_odd assente
        (2.30, 4.00, 2.00, 1.80, "NO"),  # qx >= 4
    ],
)
def test_under_excel_g_g39_formula(
    q1: float, qx: float, q2: float, under_odd: float | None, expected: str
):
    result = build_signals_matrix(
        q1=q1,
        qx=qx,
        q2=q2,
        sample_home_away_split=16,
        under_2_5_cecchino_odd=under_odd,
    )
    assert result["status"] == STATUS_AVAILABLE
    under = _signals_by_key(result, "under_under_pt")
    assert under["excel_g"] == expected
    assert result["inputs"]["diff_1_2"] == pytest.approx(q2 - q1, rel=1e-9)
    assert result["inputs"]["under_2_5_cecchino_odd"] == under_odd
