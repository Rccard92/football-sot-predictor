"""Test consenso segnali Cecchino (policy min-two Opzione B)."""

from __future__ import annotations

from app.services.cecchino.cecchino_signal_consensus import (
    ACQ_ACQUIRED_CONSENSUS,
    ACQ_NO_RAW_SIGNAL,
    ACQ_REJECTED_INSUFFICIENT,
    ACQ_SINGLE_FORMULA_EXEMPT,
    compute_signal_group_consensus,
    inherit_draw_consensus,
)


def test_consensus_0_of_4_no_raw():
    c = compute_signal_group_consensus(
        signal_group="DRAW",
        signals={"excel_d": "NO", "excel_e": "NO", "excel_f": "NO", "excel_g": "NO"},
    )
    assert c["consensus_yes_count"] == 0
    assert c["consensus_passed"] is False
    assert c["acquisition_status"] == ACQ_NO_RAW_SIGNAL
    assert c["is_acquired"] is False


def test_consensus_1_of_4_rejected():
    c = compute_signal_group_consensus(
        signal_group="DRAW",
        signals={"excel_d": "SI", "excel_e": "NO", "excel_f": "NO", "excel_g": "NO"},
    )
    assert c["consensus_yes_count"] == 1
    assert c["consensus_required_count"] == 2
    assert c["consensus_passed"] is False
    assert c["acquisition_status"] == ACQ_REJECTED_INSUFFICIENT
    assert c["is_acquired"] is False
    assert c["consensus_yes_columns"] == ["EXCEL_D"]


def test_consensus_2_of_4_acquired():
    c = compute_signal_group_consensus(
        signal_group="DRAW",
        signals={"excel_d": "SI", "excel_e": "NO", "excel_f": "SI", "excel_g": "NO"},
    )
    assert c["consensus_yes_count"] == 2
    assert c["consensus_passed"] is True
    assert c["acquisition_status"] == ACQ_ACQUIRED_CONSENSUS
    assert c["is_acquired"] is True
    assert c["consensus_yes_columns"] == ["EXCEL_D", "EXCEL_F"]


def test_consensus_3_and_4_of_4():
    c3 = compute_signal_group_consensus(
        signal_group="OVER_OVER_PT",
        signals={"excel_d": "SI", "excel_e": "SI", "excel_f": "SI", "excel_g": "NO"},
    )
    assert c3["consensus_yes_count"] == 3
    assert c3["is_acquired"] is True
    c4 = compute_signal_group_consensus(
        signal_group="UNDER_UNDER_PT",
        signals={"excel_d": "SI", "excel_e": "SI", "excel_f": "SI", "excel_g": "SI"},
    )
    assert c4["consensus_yes_count"] == 4
    assert c4["is_acquired"] is True


def test_duplicate_columns_do_not_inflate():
    # Same source via duplicate keys should not happen; unknown keys ignored
    c = compute_signal_group_consensus(
        signal_group="DRAW",
        signals={"excel_d": "SI", "excel_d_dup": "SI", "unknown": "SI", "excel_f": "SI"},
    )
    assert c["consensus_yes_count"] == 2
    assert "EXCEL_D" in c["consensus_yes_columns"]
    assert "EXCEL_F" in c["consensus_yes_columns"]


def test_unknown_columns_ignored():
    c = compute_signal_group_consensus(
        signal_group="DRAW",
        signals={"excel_d": "SI", "foo": "SI"},
    )
    assert c["consensus_yes_count"] == 1


def test_groups_not_mixed():
    draw = compute_signal_group_consensus(
        signal_group="DRAW",
        signals={"excel_d": "SI"},
    )
    over = compute_signal_group_consensus(
        signal_group="OVER_OVER_PT",
        signals={"excel_d": "SI", "excel_e": "SI"},
    )
    assert draw["consensus_yes_count"] == 1
    assert over["consensus_yes_count"] == 2
    assert draw["is_acquired"] is False
    assert over["is_acquired"] is True


def test_home_away_single_formula_exempt():
    home = compute_signal_group_consensus(
        signal_group="HOME",
        signals={"excel_d": "SI"},
    )
    away = compute_signal_group_consensus(
        signal_group="AWAY",
        signals={"excel_d": "SI"},
    )
    assert home["acquisition_status"] == ACQ_SINGLE_FORMULA_EXEMPT
    assert home["consensus_eligible"] is False
    assert home["consensus_required_count"] == 1
    assert home["is_acquired"] is True
    assert away["acquisition_status"] == ACQ_SINGLE_FORMULA_EXEMPT
    assert away["is_acquired"] is True


def test_home_does_not_use_scala_1x():
    c = compute_signal_group_consensus(
        signal_group="HOME",
        signals={"excel_d": "NO", "scala_1x": "SI"},
    )
    assert c["consensus_yes_count"] == 0
    assert c["is_acquired"] is False


def test_away_does_not_use_scala_x2():
    c = compute_signal_group_consensus(
        signal_group="AWAY",
        signals={"excel_d": "NO", "scala_x2": "SI"},
    )
    assert c["consensus_yes_count"] == 0


def test_one_x_counts_scala():
    c = compute_signal_group_consensus(
        signal_group="ONE_X",
        signals={"excel_d": "SI", "scala_1x": "SI", "excel_e": "NO"},
    )
    assert c["consensus_yes_count"] == 2
    assert "SCALA" in c["consensus_yes_columns"]
    assert c["is_acquired"] is True


def test_x_two_counts_scala():
    c = compute_signal_group_consensus(
        signal_group="X_TWO",
        signals={"excel_g": "SI", "scala_x2": "SI"},
    )
    assert c["consensus_yes_count"] == 2
    assert c["is_acquired"] is True


def test_one_two_requires_both_d_and_e():
    one = compute_signal_group_consensus(
        signal_group="ONE_TWO",
        signals={"excel_d": "SI", "excel_e": "NO"},
    )
    assert one["is_acquired"] is False
    both = compute_signal_group_consensus(
        signal_group="ONE_TWO",
        signals={"excel_d": "SI", "excel_e": "SI"},
    )
    assert both["consensus_yes_count"] == 2
    assert both["is_acquired"] is True


def test_draw_pt_inherits_draw_does_not_inflate():
    draw = compute_signal_group_consensus(
        signal_group="DRAW",
        signals={"excel_d": "SI", "excel_f": "SI", "excel_g": "SI"},
    )
    pt = inherit_draw_consensus(draw)
    assert pt["consensus_yes_count"] == 3
    assert pt["consensus_source_group"] == "DRAW"
    assert pt["consensus_passed"] is True
    # DRAW_PT not autonomous
    auto = compute_signal_group_consensus(signal_group="DRAW_PT", signals={"excel_d": "SI"})
    assert auto["consensus_available_count"] == 0
    assert auto["consensus_passed"] is False


def test_canonical_column_order():
    c = compute_signal_group_consensus(
        signal_group="ONE_X",
        signals={
            "scala_1x": "SI",
            "excel_g": "SI",
            "excel_d": "SI",
            "excel_e": "SI",
        },
    )
    assert c["consensus_yes_columns"] == ["EXCEL_D", "EXCEL_E", "EXCEL_G", "SCALA"]
