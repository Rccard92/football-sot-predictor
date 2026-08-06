"""Consenso trasversale: raw SI vs acquired su Today/Lab/extraction."""

from __future__ import annotations

from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    attach_consensus_to_matrix_rows,
    compute_signal_group_consensus,
    is_current_signal_matrix,
)
from app.services.cecchino_data_lab.historical_signal_extraction import (
    build_market_signal_index,
    iter_acquired_signal_groups,
    iter_raw_si_signal_cells,
)


def _matrix_with_draw_signals(signals: dict[str, str], *, formula_version: str | None = None) -> dict:
    fv = CURRENT_SIGNAL_FORMULA_VERSION if formula_version is None else formula_version
    rows = [
        {
            "key": "draw",
            "label": "SEGNO X",
            "signals": {
                "excel_d": signals.get("excel_d", "NO"),
                "excel_e": signals.get("excel_e", "NO"),
                "excel_f": signals.get("excel_f", "NO"),
                "excel_g": signals.get("excel_g", "NO"),
            },
        },
        {
            "key": "one",
            "label": "1",
            "signals": {"excel_d": signals.get("home_d", "NO")},
        },
        {
            "key": "twelve",
            "label": "12",
            "signals": {
                "excel_d": signals.get("twelve_d", "NO"),
                "excel_e": signals.get("twelve_e", "NO"),
            },
        },
    ]
    attach_consensus_to_matrix_rows(rows)
    return {
        "status": "available",
        "formula_version": fv,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "rows": rows,
    }


def test_case_a_single_si_not_acquired():
    matrix = _matrix_with_draw_signals({"excel_d": "SI"})
    assert is_current_signal_matrix(matrix)
    raw = iter_raw_si_signal_cells(matrix)
    assert len(raw) == 1
    acquired = iter_acquired_signal_groups(matrix)
    assert all(g["signal_group"] != "DRAW" for g in acquired)
    draw_cons = next(r["consensus"] for r in matrix["rows"] if r["key"] == "draw")
    assert draw_cons["consensus_yes_count"] == 1
    assert draw_cons["is_acquired"] is False
    idx = build_market_signal_index(matrix)
    draw = idx.get("DRAW") or {}
    assert draw.get("signal_active") is not True
    assert int(draw.get("raw_si_count") or 0) == 1
    assert int(draw.get("acquired_signal_count") or 0) == 0


def test_case_b_two_si_acquired_once():
    matrix = _matrix_with_draw_signals({"excel_d": "SI", "excel_e": "SI"})
    raw = iter_raw_si_signal_cells(matrix)
    assert len([c for c in raw if c["signal_group"] == "DRAW"]) == 2
    acquired = [g for g in iter_acquired_signal_groups(matrix) if g["signal_group"] == "DRAW"]
    assert len(acquired) == 1
    assert acquired[0]["consensus_yes_count"] == 2
    assert acquired[0]["consensus_required_count"] == 2
    assert acquired[0]["consensus_available_count"] == 4
    assert acquired[0]["is_acquired"] is True
    idx = build_market_signal_index(matrix)
    draw = idx["DRAW"]
    assert draw["signal_active"] is True
    assert draw["raw_si_count"] == 2
    assert draw["acquired_signal_count"] == 1
    # DRAW_PT inherited
    assert idx.get("DRAW_PT", {}).get("signal_active") is True
    assert idx["DRAW_PT"]["acquired_signal_count"] == 1


def test_case_c_home_single_formula_exempt():
    matrix = _matrix_with_draw_signals({"home_d": "SI"})
    acquired = [g for g in iter_acquired_signal_groups(matrix) if g["signal_group"] == "HOME"]
    assert len(acquired) == 1
    assert acquired[0]["acquisition_status"] == "acquired_single_formula_exempt"
    assert acquired[0]["is_acquired"] is True
    idx = build_market_signal_index(matrix)
    assert idx["HOME"]["signal_active"] is True
    assert idx["HOME"]["acquired_signal_count"] == 1


def test_case_d_twelve_requires_two():
    m1 = _matrix_with_draw_signals({"twelve_d": "SI", "twelve_e": "NO"})
    assert not any(g["signal_group"] == "ONE_TWO" for g in iter_acquired_signal_groups(m1))
    cons = compute_signal_group_consensus(
        signal_group="ONE_TWO",
        signals={"excel_d": "SI", "excel_e": "NO"},
    )
    assert cons["is_acquired"] is False
    assert cons["consensus_yes_count"] == 1

    m2 = _matrix_with_draw_signals({"twelve_d": "SI", "twelve_e": "SI"})
    acquired = [g for g in iter_acquired_signal_groups(m2) if g["signal_group"] == "ONE_TWO"]
    assert len(acquired) == 1
    assert acquired[0]["consensus_yes_count"] == 2
    assert acquired[0]["is_acquired"] is True


def test_non_current_matrix_yields_no_acquired():
    matrix = _matrix_with_draw_signals(
        {"excel_d": "SI", "excel_e": "SI"},
        formula_version="cecchino_signals_matrix_v2_draw_dfg",
    )
    assert is_current_signal_matrix(matrix) is False
    assert iter_acquired_signal_groups(matrix) == []
    idx = build_market_signal_index(matrix)
    assert (idx.get("DRAW") or {}).get("signal_active") is not True
