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
    assert one == {"excel_d": "NO", "scala_1x": "SI"}

    one_x = _signals_by_key(result, "one_x")
    assert one_x == {"excel_d": "NO", "excel_e": "SI", "excel_f": "NO", "excel_g": "NO"}

    two = _signals_by_key(result, "two")
    assert two == {"excel_d": "NO", "scala_x2": "NO"}

    x_two = _signals_by_key(result, "x_two")
    assert x_two == {"excel_d": "NO", "excel_e": "NO", "excel_f": "NO", "excel_g": "NO"}

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
