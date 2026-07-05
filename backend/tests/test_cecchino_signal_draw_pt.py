"""Test activation derivata X PT (DRAW_PT) — Cecchino Monitoraggio Segnali."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
    CecchinoSignalActivation,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
    PROVIDER_API_FOOTBALL,
)
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_DRAW_PT, SEL_HOME
from app.services.cecchino.cecchino_signal_aggregation import build_signals_summary
from app.services.cecchino.cecchino_signal_display_order import SIGNAL_GROUP_DISPLAY_ORDER
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_market_selection,
    evaluate_signal_activation,
)
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_signal_target_mapping import (
    DRAW_PT_PARENT_DEACTIVATED_REASON,
    map_draw_pt_derived_target,
    map_cecchino_signal_to_target,
)


def _kpi_panel(market_key: str, *, book: float = 3.40, cecchino: float = 3.20) -> dict:
    return {
        "rows": [
            {
                "market_key": market_key,
                "quota_book": book,
                "quota_cecchino": cecchino,
            }
        ]
    }


def _draw_si_fixture_row(*, book: float = 3.40, cecchino: float = 3.20, **kwargs) -> CecchinoTodayFixture:
    row = CecchinoTodayFixture(
        scan_date=date(2026, 6, 8),
        provider_source=PROVIDER_API_FOOTBALL,
        provider_fixture_id=12345,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        home_team_name="Home FC",
        away_team_name="Away FC",
        league_name="Serie A",
        country_name="Italy",
    )
    row.id = 99
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [{"key": "draw", "label": "SEGNO X", "signals": {"excel_d": "SI"}}],
        },
    }
    row.kpi_panel_json = _kpi_panel(SEL_DRAW, book=book, cecchino=cecchino)
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_sel_draw_pt_constant():
    assert SEL_DRAW_PT == "DRAW_PT"


def test_map_draw_unchanged_ft():
    out = map_cecchino_signal_to_target("DRAW", "EXCEL_D")
    assert out["target_market_key"] == SEL_DRAW
    assert out["target_period"] == "FT"


def test_map_draw_pt_derived_target():
    out = map_draw_pt_derived_target()
    assert out["target_market_key"] == SEL_DRAW_PT
    assert out["target_market_label"] == "X PT"
    assert out["target_period"] == "HT"


def test_sync_draw_value_pass_creates_draw_and_draw_pt():
    db = MagicMock()
    row = _draw_si_fixture_row()
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 2
    assert counts["draw_pt_created"] == 1
    assert db.add.call_count == 2
    groups = {call.args[0].signal_group for call in db.add.call_args_list}
    assert groups == {"DRAW", "DRAW_PT"}
    pt = next(call.args[0] for call in db.add.call_args_list if call.args[0].signal_group == "DRAW_PT")
    assert pt.quota_book is None
    assert pt.quota_cecchino is None
    assert pt.target_market_key == SEL_DRAW_PT
    assert pt.target_period == "HT"


def test_sync_draw_value_fail_creates_neither():
    db = MagicMock()
    row = _draw_si_fixture_row(book=2.90, cecchino=3.20)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 0
    assert counts["draw_pt_created"] == 0
    assert not db.add.called


def test_sync_draw_value_fail_deactivates_draw_and_draw_pt():
    db = MagicMock()
    row = _draw_si_fixture_row(book=2.90, cecchino=3.20)
    draw = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="DRAW",
        signal_label="SEGNO X",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=True,
    )
    draw_pt = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="DRAW_PT",
        signal_label="X PT",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=True,
    )
    db.get.return_value = row
    db.scalars.return_value.all.return_value = [draw, draw_pt]

    sync_cecchino_signal_activations(db, 99)

    assert draw.is_current is False
    assert draw_pt.is_current is False
    assert draw_pt.evaluation_reason == DRAW_PT_PARENT_DEACTIVATED_REASON


def test_draw_pt_won_when_ht_draw():
    result = evaluate_market_selection(
        SEL_DRAW_PT,
        {"halftime": {"home": 1, "away": 1}, "fulltime": {"home": None, "away": None}},
    )
    assert result["evaluation_status"] == EVAL_WON


def test_draw_pt_lost_when_ht_not_draw():
    result = evaluate_market_selection(
        SEL_DRAW_PT,
        {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": None, "away": None}},
    )
    assert result["evaluation_status"] == EVAL_LOST


def test_draw_pt_result_missing_without_ht():
    result = evaluate_market_selection(
        SEL_DRAW_PT,
        {"halftime": {"home": None, "away": None}, "fulltime": {"home": 1, "away": 1}},
    )
    assert result["evaluation_status"] == EVAL_RESULT_MISSING


def test_draw_pt_evaluate_signal_activation_no_ft_required():
    activation = {"target_market_key": SEL_DRAW_PT, "target_period": "HT"}
    match = {"halftime": {"home": 0, "away": 0}, "fulltime": {"home": None, "away": None}}
    out = evaluate_signal_activation(activation, match)
    assert out["evaluation_status"] == EVAL_WON
    assert out["ft_home_goals"] is None


def test_home_unchanged_not_transformed_to_one_x():
    db = MagicMock()
    row = _draw_si_fixture_row()
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [{"key": "one", "label": "1", "signals": {"excel_d": "SI"}}],
        },
    }
    row.kpi_panel_json = _kpi_panel(SEL_HOME)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    sync_cecchino_signal_activations(db, 99)

    added = db.add.call_args[0][0]
    assert added.signal_group == "HOME"
    assert added.signal_group != "ONE_X"


def test_summary_signal_order():
    db = MagicMock()
    rows = [
        CecchinoSignalActivation(
            today_fixture_id=i,
            provider_fixture_id=i,
            scan_date=date(2026, 6, 8),
            signal_group=sg,
            signal_label=sg,
            source_column="EXCEL_D",
            signal_value=True,
            evaluation_status=EVAL_WON,
            is_current=True,
        )
        for i, sg in enumerate(["OVER_OVER_PT", "HOME", "DRAW_PT", "DRAW"], start=1)
    ]
    db.scalars.return_value.all.return_value = rows
    db.scalar.return_value = 4

    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )

    order = [row["signal_group"] for row in summary["by_signal"]]
    assert order.index("HOME") < order.index("DRAW")
    assert order.index("DRAW") < order.index("DRAW_PT")
    assert order.index("DRAW_PT") < order.index("OVER_OVER_PT")


def test_display_order_constant():
    assert SIGNAL_GROUP_DISPLAY_ORDER == (
        "HOME",
        "DRAW",
        "AWAY",
        "ONE_X",
        "X_TWO",
        "ONE_TWO",
        "DRAW_PT",
        "UNDER_UNDER_PT",
        "OVER_OVER_PT",
    )
