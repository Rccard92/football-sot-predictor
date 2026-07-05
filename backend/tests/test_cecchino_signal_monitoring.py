"""Test monitoraggio segnali Cecchino — Fase 32/33."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
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
from app.services.cecchino.cecchino_signal_aggregation import (
    _bucket_counts,
    _format_signal_display_label,
    _serialize_activation_row,
    _success_rate,
    build_signals_summary,
    export_signals_csv,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_activations_for_fixture,
    evaluate_signal_activation,
    revaluate_signal_activations,
)
from app.services.cecchino.cecchino_signal_backfill import (
    backfill_signal_activations,
    build_signal_diagnostics,
)
from app.services.cecchino.cecchino_signal_sync import (
    remap_legacy_scala_activations_in_range,
    sync_cecchino_signal_activations,
)
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix
from app.services.cecchino.cecchino_signal_target_mapping import (
    LEGACY_WRONG_SCALA_REASON,
    VALID_SCALA_SIGNAL_GROUPS,
    apply_under_over_target_to_activation,
    is_invalid_legacy_scala_activation,
    is_valid_scala_activation,
    map_cecchino_signal_to_target,
    map_row_key_to_signal_group,
    remap_under_over_activations_in_range,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)


def _signals_matrix(**row_signals):
    rows = []
    for key, label, signals in [
        ("under_under_pt", "UNDER / UNDER PT", {"excel_d": "NO"}),
        ("draw", "SEGNO X", {"excel_d": row_signals.get("draw_d", "NO")}),
        ("over_over_pt", "OVER / OVER PT", {"excel_d": row_signals.get("over_d", "NO")}),
        ("one", "1", {"excel_d": row_signals.get("one_d", "NO")}),
        ("one_x", "1X", {"excel_d": row_signals.get("one_x_d", "NO")}),
        ("two", "2", {"excel_d": row_signals.get("two_d", "NO")}),
        ("x_two", "X2", {"excel_d": row_signals.get("x_two_d", "NO")}),
        ("twelve", "12", {"excel_d": row_signals.get("twelve_d", "NO")}),
    ]:
        rows.append({"key": key, "label": label, "signals": signals})
    return {
        "status": STATUS_AVAILABLE,
        "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9, "avg_q": 2.87, "diff_1_2": 0.4},
        "rows": rows,
    }


def _kpi_panel_row(
    market_key: str,
    *,
    book: float = 3.40,
    cecchino: float = 3.20,
) -> dict:
    return {
        "market_key": market_key,
        "quota_book": book,
        "quota_cecchino": cecchino,
        "edge_pct": 5.0,
        "rating": 70,
    }


def _kpi_panel(*market_keys: str, book: float = 3.40, cecchino: float = 3.20) -> dict:
    return {"rows": [_kpi_panel_row(mk, book=book, cecchino=cecchino) for mk in market_keys]}


def _fixture_row(**kwargs) -> CecchinoTodayFixture:
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
    row.cecchino_output_json = {"signals_matrix": _signals_matrix(draw_d="SI")}
    row.kpi_panel_json = {
        "rows": [
            {
                "market_key": SEL_DRAW,
                "segno": "X",
                "quota_book": 2.8,
                "quota_cecchino": 2.31,
                "edge_pct": 12.5,
                "rating": 72,
            }
        ]
    }
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_map_draw_target():
    out = map_cecchino_signal_to_target("DRAW", "EXCEL_D")
    assert out["target_market_key"] == SEL_DRAW
    assert out["evaluation_status"] == EVAL_PENDING


def test_map_home_away_targets():
    assert map_cecchino_signal_to_target("HOME", "EXCEL_D")["target_market_key"] == SEL_HOME
    assert map_cecchino_signal_to_target("AWAY", "EXCEL_D")["target_market_key"] == SEL_AWAY


def test_map_dc_targets():
    assert map_cecchino_signal_to_target("ONE_X", "EXCEL_D")["target_market_key"] == SEL_ONE_X
    assert map_cecchino_signal_to_target("X_TWO", "EXCEL_D")["target_market_key"] == SEL_X_TWO
    assert map_cecchino_signal_to_target("ONE_TWO", "EXCEL_D")["target_market_key"] == SEL_ONE_TWO


def test_under_over_maps_to_2_5_ft():
    under = map_cecchino_signal_to_target("UNDER_UNDER_PT", "EXCEL_D")
    over = map_cecchino_signal_to_target("OVER_OVER_PT", "EXCEL_E")
    assert under["target_market_key"] == SEL_UNDER_2_5
    assert under["target_market_label"] == "Under 2.5"
    assert under["target_period"] == "FT"
    assert under["evaluation_status"] == EVAL_PENDING
    assert over["target_market_key"] == SEL_OVER_2_5
    assert over["target_market_label"] == "Over 2.5"
    assert over["evaluation_status"] == EVAL_PENDING


@pytest.mark.parametrize(
    ("total_goals", "expected"),
    [
        (0, EVAL_WON),
        (1, EVAL_WON),
        (2, EVAL_WON),
        (3, EVAL_LOST),
        (4, EVAL_LOST),
        (5, EVAL_LOST),
    ],
)
def test_evaluate_under_2_5_won_lost(total_goals, expected):
    home = total_goals // 2
    away = total_goals - home
    result = evaluate_signal_activation(
        {"target_market_key": SEL_UNDER_2_5, "target_period": "FT"},
        {"fulltime": {"home": home, "away": away}, "halftime": {}},
    )
    assert result["evaluation_status"] == expected
    if expected in (EVAL_WON, EVAL_LOST):
        assert f"Totale gol FT {total_goals}" in (result["evaluation_reason"] or "")
        assert "Under 2.5" in (result["evaluation_reason"] or "")


@pytest.mark.parametrize(
    ("total_goals", "expected"),
    [
        (0, EVAL_LOST),
        (1, EVAL_LOST),
        (2, EVAL_LOST),
        (3, EVAL_WON),
        (4, EVAL_WON),
        (5, EVAL_WON),
    ],
)
def test_evaluate_over_2_5_won_lost(total_goals, expected):
    home = total_goals // 2
    away = total_goals - home
    result = evaluate_signal_activation(
        {"target_market_key": SEL_OVER_2_5, "target_period": "FT"},
        {"fulltime": {"home": home, "away": away}, "halftime": {}},
    )
    assert result["evaluation_status"] == expected
    if expected in (EVAL_WON, EVAL_LOST):
        assert f"Totale gol FT {total_goals}" in (result["evaluation_reason"] or "")
        assert "Over 2.5" in (result["evaluation_reason"] or "")


def test_apply_under_over_target_to_activation_remaps_not_evaluable():
    activation = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        signal_group="UNDER_UNDER_PT",
        signal_label="UNDER / UNDER PT",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_NOT_EVALUABLE,
        evaluation_reason="missing_target_market_mapping",
    )
    assert apply_under_over_target_to_activation(activation) is True
    assert activation.target_market_key == SEL_UNDER_2_5
    assert activation.target_period == "FT"
    assert activation.evaluation_status == EVAL_PENDING
    assert activation.evaluation_reason is None


def test_remap_under_over_activations_in_range():
    db = MagicMock()
    under = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        signal_group="UNDER_UNDER_PT",
        signal_label="UNDER / UNDER PT",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_NOT_EVALUABLE,
        is_current=True,
    )
    over = CecchinoSignalActivation(
        today_fixture_id=2,
        provider_fixture_id=2,
        scan_date=date(2026, 6, 9),
        signal_group="OVER_OVER_PT",
        signal_label="OVER / OVER PT",
        source_column="EXCEL_E",
        signal_value=True,
        target_market_key=None,
        evaluation_status=EVAL_NOT_EVALUABLE,
        is_current=True,
    )
    db.scalars.return_value.all.return_value = [under, over]
    remapped = remap_under_over_activations_in_range(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    assert remapped == 2
    assert under.target_market_key == SEL_UNDER_2_5
    assert over.target_market_key == SEL_OVER_2_5
    db.flush.assert_called_once()


def test_evaluate_activations_for_fixture_remaps_ex_not_evaluable_under():
    db = MagicMock()
    fixture = _fixture_row(
        score_fulltime_home=1,
        score_fulltime_away=0,
        match_display_status="finished",
    )
    activation = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        signal_group="UNDER_UNDER_PT",
        signal_label="UNDER / UNDER PT",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_NOT_EVALUABLE,
        evaluation_reason="missing_target_market_mapping",
        is_current=True,
    )
    db.get.return_value = fixture
    db.scalars.return_value.all.return_value = [activation]

    counts = evaluate_activations_for_fixture(db, 99)

    assert activation.target_market_key == SEL_UNDER_2_5
    assert activation.evaluation_status == EVAL_WON
    assert "Under 2.5 vinto" in (activation.evaluation_reason or "")
    assert counts["evaluated"] == 1
    assert counts["not_evaluable"] == 0


def test_success_rate_includes_under_over_after_remap():
    rows = [
        CecchinoSignalActivation(
            today_fixture_id=1,
            provider_fixture_id=1,
            scan_date=date(2026, 6, 8),
            signal_group="UNDER_UNDER_PT",
            signal_label="UNDER / UNDER PT",
            source_column="EXCEL_D",
            signal_value=True,
            evaluation_status=EVAL_WON,
            is_current=True,
        ),
        CecchinoSignalActivation(
            today_fixture_id=2,
            provider_fixture_id=2,
            scan_date=date(2026, 6, 8),
            signal_group="OVER_OVER_PT",
            signal_label="OVER / OVER PT",
            source_column="EXCEL_E",
            signal_value=True,
            evaluation_status=EVAL_LOST,
            is_current=True,
        ),
    ]
    bucket = _bucket_counts(rows)
    assert bucket["success_rate"] == 50.0
    assert bucket["not_evaluable"] == 0


def test_serialize_activation_row_under_over_ft_labels():
    under = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        signal_group="UNDER_UNDER_PT",
        signal_label="UNDER / UNDER PT",
        source_column="EXCEL_D",
        signal_value=True,
        target_market_label="Under 2.5",
        evaluation_status=EVAL_WON,
        evaluation_reason="Totale gol FT 1: Under 2.5 vinto",
        home_team_name="A",
        away_team_name="B",
        is_current=True,
    )
    under.id = 1
    over = CecchinoSignalActivation(
        today_fixture_id=2,
        provider_fixture_id=2,
        scan_date=date(2026, 6, 8),
        signal_group="OVER_OVER_PT",
        signal_label="OVER / OVER PT",
        source_column="EXCEL_E",
        signal_value=True,
        target_market_label="Over 2.5",
        evaluation_status=EVAL_LOST,
        home_team_name="C",
        away_team_name="D",
        is_current=True,
    )
    over.id = 2
    under_row = _serialize_activation_row(under)
    over_row = _serialize_activation_row(over)
    assert under_row["target_market_label"] == "Under 2.5 FT"
    assert over_row["target_market_label"] == "Over 2.5 FT"
    assert under_row["signal_label"] == "Under"
    assert over_row["signal_label"] == "Over"
    assert under_row["signal_group"] == "UNDER_UNDER_PT"
    assert over_row["signal_group"] == "OVER_OVER_PT"


def test_format_signal_display_label_under_over():
    assert _format_signal_display_label("UNDER_UNDER_PT", "UNDER / UNDER PT") == "Under"
    assert _format_signal_display_label("OVER_OVER_PT", "OVER / OVER PT") == "Over"
    assert _format_signal_display_label("DRAW", "SEGNO X") == "X"
    assert _format_signal_display_label("ONE_TWO", "12") == "1/2"
    assert _format_signal_display_label("DRAW_PT", "X PT") == "X PT"


def test_evaluate_draw_won_lost():
    activation = {"target_market_key": SEL_DRAW, "target_period": "FT"}
    won = evaluate_signal_activation(activation, {"fulltime": {"home": 1, "away": 1}, "halftime": {}})
    lost = evaluate_signal_activation(activation, {"fulltime": {"home": 2, "away": 1}, "halftime": {}})
    assert won["evaluation_status"] == EVAL_WON
    assert lost["evaluation_status"] == EVAL_LOST


def test_evaluate_home_away():
    home = evaluate_signal_activation(
        {"target_market_key": SEL_HOME, "target_period": "FT"},
        {"fulltime": {"home": 2, "away": 1}, "halftime": {}},
    )
    away = evaluate_signal_activation(
        {"target_market_key": SEL_AWAY, "target_period": "FT"},
        {"fulltime": {"home": 1, "away": 2}, "halftime": {}},
    )
    assert home["evaluation_status"] == EVAL_WON
    assert away["evaluation_status"] == EVAL_WON


def test_evaluate_one_x_x2_twelve():
    one_x = evaluate_signal_activation(
        {"target_market_key": SEL_ONE_X, "target_period": "FT"},
        {"fulltime": {"home": 1, "away": 1}, "halftime": {}},
    )
    x2 = evaluate_signal_activation(
        {"target_market_key": SEL_X_TWO, "target_period": "FT"},
        {"fulltime": {"home": 0, "away": 2}, "halftime": {}},
    )
    twelve = evaluate_signal_activation(
        {"target_market_key": SEL_ONE_TWO, "target_period": "FT"},
        {"fulltime": {"home": 2, "away": 1}, "halftime": {}},
    )
    assert one_x["evaluation_status"] == EVAL_WON
    assert x2["evaluation_status"] == EVAL_WON
    assert twelve["evaluation_status"] == EVAL_WON


def test_evaluate_result_missing_and_not_evaluable():
    pending = evaluate_signal_activation(
        {"target_market_key": SEL_DRAW, "target_period": "FT"},
        {"fulltime": {"home": None, "away": None}, "halftime": {}},
    )
    ne = evaluate_signal_activation(
        {"target_market_key": None, "evaluation_reason": "missing_target_market_mapping"},
        {"fulltime": {"home": 1, "away": 1}, "halftime": {}},
    )
    assert pending["evaluation_status"] == EVAL_RESULT_MISSING
    assert ne["evaluation_status"] == EVAL_NOT_EVALUABLE


def test_success_rate_excludes_pending_and_not_evaluable():
    assert _success_rate(8, 2) == 80.0
    rows = [
        MagicMock(evaluation_status=EVAL_WON),
        MagicMock(evaluation_status=EVAL_WON),
        MagicMock(evaluation_status=EVAL_LOST),
        MagicMock(evaluation_status=EVAL_PENDING),
        MagicMock(evaluation_status=EVAL_NOT_EVALUABLE),
    ]
    bucket = _bucket_counts(rows)
    assert bucket["success_rate"] == pytest.approx(66.7, abs=0.1)
    assert bucket["pending"] == 1
    assert bucket["not_evaluable"] == 1


def test_matrix_home_away_have_no_scala_column():
    matrix = build_signals_matrix(
        q1=2.50,
        qx=3.20,
        q2=2.90,
        sample_home_away_split=16,
    )
    rows = {row["key"]: row["signals"] for row in matrix["rows"]}
    assert "scala_1x" not in rows["one"]
    assert "scala_x2" not in rows["two"]
    assert "scala_1x" in rows["one_x"]
    assert "scala_x2" in rows["x_two"]


def test_sync_scala_on_one_x_not_home():
    db = MagicMock()
    row = _fixture_row()
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9, "avg_q": 2.87, "diff_1_2": 0.4},
            "rows": [
                {"key": "one", "label": "1", "signals": {"excel_d": "NO"}},
                {
                    "key": "one_x",
                    "label": "1X",
                    "signals": {
                        "excel_d": "NO",
                        "excel_e": "NO",
                        "excel_f": "NO",
                        "excel_g": "NO",
                        "scala_1x": "SI",
                    },
                },
            ],
        },
    }
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []
    row.kpi_panel_json = _kpi_panel(SEL_ONE_X)

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 1
    added = db.add.call_args[0][0]
    assert added.signal_group == "ONE_X"
    assert added.source_column == "SCALA"
    assert added.signal_group != "HOME"


def test_remap_legacy_scala_activations_deactivates_home_away():
    db = MagicMock()
    home_scala = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        signal_group="HOME",
        signal_label="1",
        source_column="SCALA",
        signal_value=True,
        is_current=True,
    )
    away_scala = CecchinoSignalActivation(
        today_fixture_id=2,
        provider_fixture_id=2,
        scan_date=date(2026, 6, 8),
        signal_group="AWAY",
        signal_label="2",
        source_column="SCALA",
        signal_value=True,
        is_current=True,
    )
    db.scalars.return_value.all.return_value = [home_scala, away_scala]

    count = remap_legacy_scala_activations_in_range(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )

    assert count == 2
    assert home_scala.is_current is False
    assert away_scala.is_current is False
    assert home_scala.evaluation_reason == LEGACY_WRONG_SCALA_REASON
    assert away_scala.evaluation_reason == LEGACY_WRONG_SCALA_REASON


def test_sync_skips_home_scala_from_malformed_matrix():
    db = MagicMock()
    row = _fixture_row()
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [
                {"key": "one", "label": "1", "signals": {"excel_d": "NO", "scala_1x": "SI"}},
                {"key": "two", "label": "2", "signals": {"excel_d": "NO", "scala_x2": "SI"}},
            ],
        },
    }
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 0
    assert not db.add.called


def test_sync_home_from_d48_excel_d_only():
    db = MagicMock()
    row = _fixture_row()
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [{"key": "one", "label": "1", "signals": {"excel_d": "SI"}}],
        },
    }
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []
    row.kpi_panel_json = _kpi_panel(SEL_HOME)

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 1
    added = db.add.call_args[0][0]
    assert added.signal_group == "HOME"
    assert added.source_column == "EXCEL_D"


def test_sync_away_from_d54_excel_d_only():
    db = MagicMock()
    row = _fixture_row()
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [{"key": "two", "label": "2", "signals": {"excel_d": "SI"}}],
        },
    }
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []
    row.kpi_panel_json = _kpi_panel(SEL_AWAY)

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 1
    added = db.add.call_args[0][0]
    assert added.signal_group == "AWAY"
    assert added.source_column == "EXCEL_D"


def test_sync_x_two_from_g54_scala():
    db = MagicMock()
    row = _fixture_row()
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [
                {
                    "key": "x_two",
                    "label": "X2",
                    "signals": {
                        "excel_d": "NO",
                        "excel_e": "NO",
                        "excel_f": "NO",
                        "excel_g": "NO",
                        "scala_x2": "SI",
                    },
                },
            ],
        },
    }
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []
    row.kpi_panel_json = _kpi_panel(SEL_X_TWO)

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 1
    added = db.add.call_args[0][0]
    assert added.signal_group == "X_TWO"
    assert added.source_column == "SCALA"


def test_scala_validation_accepts_only_one_x_x_two():
    assert is_valid_scala_activation("ONE_X", "SCALA")
    assert is_valid_scala_activation("X_TWO", "SCALA")
    assert not is_valid_scala_activation("HOME", "SCALA")
    assert not is_valid_scala_activation("AWAY", "SCALA")
    assert is_valid_scala_activation("HOME", "EXCEL_D")
    assert VALID_SCALA_SIGNAL_GROUPS == frozenset({"ONE_X", "X_TWO"})


def test_summary_excludes_home_away_scala_legacy():
    db = MagicMock()
    valid = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        signal_group="ONE_X",
        signal_label="1X",
        source_column="SCALA",
        signal_value=True,
        evaluation_status=EVAL_WON,
        is_current=True,
    )
    db.scalars.return_value.all.return_value = [valid]
    db.scalar.side_effect = [1, 2]

    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )

    combos = {(r["signal_group"], r["source_column"]) for r in summary["by_signal_and_column"]}
    assert ("ONE_X", "SCALA") in combos
    assert ("HOME", "SCALA") not in combos
    assert "legacy_wrong_scala_mapping_detected" in summary["warnings"]
    assert is_invalid_legacy_scala_activation("HOME", "SCALA")


def test_diagnostics_legacy_wrong_scala_mapping_count():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.side_effect = [0, 0, 2]
    db.execute.return_value.all.return_value = []

    diag = build_signal_diagnostics(db, date_from=date(2026, 6, 8), date_to=date(2026, 6, 8))

    assert diag["legacy_wrong_scala_mapping_count"] == 2
    assert any("Ricalcola mapping segnali" in w for w in diag["warnings"])


def test_matrix_d48_formula_generates_home_excel_d():
    matrix = build_signals_matrix(
        q1=1.20,
        qx=4.00,
        q2=8.00,
        sample_home_away_split=16,
        prob_1=0.55,
        prob_x=0.25,
        prob_2=0.20,
    )
    rows = {row["key"]: row["signals"] for row in matrix["rows"]}
    assert rows["one"]["excel_d"] == "SI"
    assert rows["one_x"]["scala_1x"] == "SI"


def test_matrix_d54_formula_generates_away_excel_d():
    matrix = build_signals_matrix(
        q1=10.00,
        qx=6.00,
        q2=2.00,
        sample_home_away_split=16,
        prob_1=0.15,
        prob_x=0.20,
        prob_2=0.65,
    )
    rows = {row["key"]: row["signals"] for row in matrix["rows"]}
    assert rows["two"]["excel_d"] == "SI"
    assert rows["x_two"]["scala_x2"] == "SI"


def test_backfill_force_remap_rebuilds_activations_offline():
    db = MagicMock()
    fixture = _fixture_row()
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.return_value = 0

    with patch(
        "app.services.cecchino.cecchino_signal_backfill._ensure_signals_matrix_on_row",
        return_value=True,
    ) as mock_ensure, patch(
        "app.services.cecchino.cecchino_signal_backfill.sync_cecchino_signal_activations",
        return_value={"created": 2, "updated": 0, "deactivated": 1, "skipped": 0},
    ) as mock_sync, patch(
        "app.services.cecchino.cecchino_signal_backfill.remap_legacy_scala_activations_in_range",
        return_value=3,
    ) as mock_remap, patch(
        "app.services.cecchino.cecchino_signal_backfill.remap_under_over_activations_in_range",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill.evaluate_activations_for_fixture",
        return_value={"evaluated": 2, "pending": 0, "not_evaluable": 0},
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill._activation_status_counts",
        return_value={"won": 1, "lost": 1, "pending": 0, "not_evaluable": 0, "evaluated_count": 2},
    ), patch(
        "app.services.api_football_client.ApiFootballClient",
    ) as mock_client:
        out = backfill_signal_activations(
            db,
            date_from=date(2026, 6, 8),
            date_to=date(2026, 6, 8),
            only_missing=False,
            evaluate_after=True,
            force_remap=True,
        )

    assert out["force_remap"] is True
    assert out["legacy_scala_deactivated"] == 3
    assert out["fixtures_with_signals"] == 1
    mock_ensure.assert_called_once_with(fixture, force_rebuild=True)
    mock_remap.assert_called_once()
    mock_sync.assert_called_once_with(db, 99)
    mock_client.assert_not_called()


def test_sync_saves_only_si_and_is_idempotent():
    db = MagicMock()
    row = _fixture_row()
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts1 = sync_cecchino_signal_activations(db, 99)
    assert counts1["created"] == 2
    assert db.add.called

    existing = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="DRAW",
        signal_label="SEGNO X",
        source_column="EXCEL_D",
        signal_value=True,
        target_market_key=SEL_DRAW,
        target_period="FT",
        evaluation_status=EVAL_PENDING,
    )
    existing_pt = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="DRAW_PT",
        signal_label="X PT",
        source_column="EXCEL_D",
        signal_value=True,
        target_market_key=SEL_DRAW_PT,
        target_period="HT",
        evaluation_status=EVAL_PENDING,
    )
    existing.id = 1
    existing_pt.id = 2
    db.scalars.return_value.all.return_value = [existing, existing_pt]
    db.add.reset_mock()

    counts2 = sync_cecchino_signal_activations(db, 99)
    assert counts2["updated"] == 2
    assert not db.add.called


def test_map_row_key_to_signal_group():
    assert map_row_key_to_signal_group("draw") == "DRAW"
    assert map_row_key_to_signal_group("one") == "HOME"


def test_build_signals_summary_aggregates_by_signal_and_column():
    db = MagicMock()
    rows = [
        CecchinoSignalActivation(
            today_fixture_id=1,
            provider_fixture_id=1,
            scan_date=date(2026, 6, 8),
            signal_group="DRAW",
            signal_label="SEGNO X",
            source_column="EXCEL_D",
            signal_value=True,
            evaluation_status=EVAL_WON,
            is_current=True,
        ),
        CecchinoSignalActivation(
            today_fixture_id=2,
            provider_fixture_id=2,
            scan_date=date(2026, 6, 8),
            signal_group="DRAW",
            signal_label="SEGNO X",
            source_column="EXCEL_D",
            signal_value=True,
            evaluation_status=EVAL_LOST,
            is_current=True,
        ),
    ]
    db.scalars.return_value.all.return_value = rows
    db.scalar.return_value = 2
    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    assert summary["overall"]["won"] == 1
    assert summary["overall"]["lost"] == 1
    assert summary["overall"]["success_rate"] == 50.0
    assert summary["overall"]["eligible_fixtures_count"] == 2
    assert summary["overall"]["fixtures_with_signals_count"] == 2
    assert summary["overall"]["avg_signals_per_fixture"] == 1.0
    assert len(summary["by_signal_and_column"]) == 1


def test_summary_avg_signals_per_fixture_uses_eligible_count():
    db = MagicMock()
    rows = [
        CecchinoSignalActivation(
            today_fixture_id=i,
            provider_fixture_id=i,
            scan_date=date(2026, 6, 8),
            signal_group="DRAW",
            signal_label="SEGNO X",
            source_column="EXCEL_D",
            signal_value=True,
            evaluation_status=EVAL_WON,
            is_current=True,
        )
        for i in range(1, 7)
    ]
    db.scalars.return_value.all.return_value = rows
    db.scalar.return_value = 2
    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    assert summary["overall"]["activations"] == 6
    assert summary["overall"]["fixtures_with_signals_count"] == 6
    assert summary["overall"]["eligible_fixtures_count"] == 2
    assert summary["overall"]["avg_signals_per_fixture"] == 3.0


def test_summary_avg_signals_per_fixture_null_when_no_fixtures():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = 0
    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    assert summary["overall"]["activations"] == 0
    assert summary["overall"]["eligible_fixtures_count"] == 0
    assert summary["overall"]["fixtures_with_signals_count"] == 0
    assert summary["overall"]["avg_signals_per_fixture"] is None


def test_summary_under_over_display_labels():
    db = MagicMock()
    rows = [
        CecchinoSignalActivation(
            today_fixture_id=1,
            provider_fixture_id=1,
            scan_date=date(2026, 6, 8),
            signal_group="UNDER_UNDER_PT",
            signal_label="UNDER / UNDER PT",
            source_column="EXCEL_D",
            signal_value=True,
            evaluation_status=EVAL_WON,
            is_current=True,
        ),
        CecchinoSignalActivation(
            today_fixture_id=2,
            provider_fixture_id=2,
            scan_date=date(2026, 6, 8),
            signal_group="OVER_OVER_PT",
            signal_label="OVER / OVER PT",
            source_column="EXCEL_E",
            signal_value=True,
            evaluation_status=EVAL_LOST,
            is_current=True,
        ),
    ]
    db.scalars.return_value.all.return_value = rows
    db.scalar.return_value = 2
    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    labels = {row["signal_group"]: row["signal_label"] for row in summary["by_signal"]}
    assert labels["UNDER_UNDER_PT"] == "Under"
    assert labels["OVER_OVER_PT"] == "Over"


def test_export_csv_respects_filters():
    db = MagicMock()
    row = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        signal_group="DRAW",
        signal_label="SEGNO X",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_WON,
        home_team_name="A",
        away_team_name="B",
        target_market_label="X",
        is_current=True,
    )
    row.id = 7
    db.scalar.return_value = 1
    db.scalars.return_value.all.return_value = [row]
    csv_text = export_signals_csv(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        signal_group="DRAW",
    )
    assert ",X," in csv_text or ",X,EXCEL_D" in csv_text
    assert "EXCEL_D" in csv_text


def test_revaluate_does_not_call_api():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [99]
    with patch(
        "app.services.cecchino.cecchino_signal_evaluation.remap_under_over_activations_in_range",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_signal_evaluation.evaluate_activations_for_fixture",
        return_value={"evaluated": 2, "pending": 1, "not_evaluable": 0},
    ) as mock_eval:
        out = revaluate_signal_activations(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )
    assert out["fixtures"] == 1
    assert out["evaluated"] == 2
    assert out["remapped"] == 0
    mock_eval.assert_called_once_with(db, 99)
    db.commit.assert_called_once()


def test_revaluate_remaps_historical_not_evaluable_under_over():
    db = MagicMock()
    fixture = _fixture_row(
        score_fulltime_home=2,
        score_fulltime_away=2,
        match_display_status="finished",
    )
    under = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        signal_group="UNDER_UNDER_PT",
        signal_label="UNDER / UNDER PT",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_NOT_EVALUABLE,
        is_current=True,
    )
    over = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        signal_group="OVER_OVER_PT",
        signal_label="OVER / OVER PT",
        source_column="EXCEL_E",
        signal_value=True,
        evaluation_status=EVAL_NOT_EVALUABLE,
        is_current=True,
    )

    scalars_calls = {"n": 0}

    def _scalars_side_effect(_stmt):
        result = MagicMock()
        scalars_calls["n"] += 1
        if scalars_calls["n"] == 1:
            result.all.return_value = [under, over]
        elif scalars_calls["n"] == 2:
            result.all.return_value = [99]
        else:
            result.all.return_value = [under, over]
        return result

    db.scalars.side_effect = _scalars_side_effect
    db.get.return_value = fixture

    out = revaluate_signal_activations(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )

    assert out["remapped"] == 2
    assert under.evaluation_status == EVAL_LOST
    assert over.evaluation_status == EVAL_WON
    assert out["evaluated"] == 2


def test_diagnostics_detects_fixtures_without_activations():
    db = MagicMock()
    fixture = _fixture_row()
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.side_effect = [0, 0, 0]
    db.execute.return_value.all.return_value = []

    diag = build_signal_diagnostics(db, date_from=date(2026, 6, 8), date_to=date(2026, 6, 8))
    assert diag["legacy_wrong_scala_mapping_count"] == 0
    assert diag["today_fixtures_count"] == 1
    assert diag["fixtures_with_signal_matrix_count"] >= 1
    assert diag["signal_activations_count"] == 0
    assert diag["date_filter_field_used"] == "scan_date"


def test_backfill_creates_activations_offline():
    db = MagicMock()
    fixture = _fixture_row(score_fulltime_home=2, score_fulltime_away=1, match_display_status="finished")
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.return_value = 0

    with patch(
        "app.services.cecchino.cecchino_signal_backfill.sync_cecchino_signal_activations",
        return_value={"created": 2, "updated": 0, "deactivated": 0, "skipped": 0},
    ) as mock_sync, patch(
        "app.services.cecchino.cecchino_signal_backfill.remap_under_over_activations_in_range",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill.evaluate_activations_for_fixture",
        return_value={"evaluated": 2, "pending": 0, "not_evaluable": 0},
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill._activation_status_counts",
        return_value={"won": 2, "lost": 0, "pending": 0, "not_evaluable": 0, "evaluated_count": 2},
    ):
        out = backfill_signal_activations(
            db,
            date_from=date(2026, 6, 8),
            date_to=date(2026, 6, 8),
            only_missing=True,
            evaluate_after=True,
        )

    assert out["status"] == "ok"
    assert out["fixtures_with_signals"] == 1
    assert out["signals_created"] == 2
    mock_sync.assert_called_once_with(db, 99)
    db.commit.assert_called_once()


def test_backfill_idempotent_skips_when_only_missing():
    db = MagicMock()
    fixture = _fixture_row()
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.return_value = 1

    with patch(
        "app.services.cecchino.cecchino_signal_backfill.sync_cecchino_signal_activations",
    ) as mock_sync, patch(
        "app.services.cecchino.cecchino_signal_backfill.remap_under_over_activations_in_range",
        return_value=0,
    ):
        out = backfill_signal_activations(
            db,
            date_from=date(2026, 6, 8),
            date_to=date(2026, 6, 8),
            only_missing=True,
            evaluate_after=False,
        )

    assert out["fixtures_skipped"] == 1
    assert out["signals_created"] == 0
    mock_sync.assert_not_called()


def test_backfill_does_not_call_api_football():
    db = MagicMock()
    fixture = _fixture_row()
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.return_value = 0

    with patch(
        "app.services.cecchino.cecchino_signal_backfill.sync_cecchino_signal_activations",
        return_value={"created": 1, "updated": 0, "deactivated": 0, "skipped": 0},
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill.remap_under_over_activations_in_range",
        return_value=0,
    ), patch(
        "app.services.api_football_client.ApiFootballClient",
    ) as mock_client:
        backfill_signal_activations(
            db,
            date_from=date(2026, 6, 8),
            date_to=date(2026, 6, 8),
            evaluate_after=False,
        )
    mock_client.assert_not_called()


def test_sync_under_over_creates_correct_target():
    db = MagicMock()
    row = _fixture_row()
    row.cecchino_output_json = {
        "signals_matrix": _signals_matrix(draw_d="NO", over_d="SI"),
    }
    row.kpi_panel_json = {
        "rows": [
            {
                "market_key": SEL_OVER_2_5,
                "segno": "Over 2.5",
                "quota_book": 1.9,
                "quota_cecchino": 1.75,
                "edge_pct": 8.0,
                "rating": 65,
            }
        ]
    }
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 1
    added = db.add.call_args[0][0]
    assert added.signal_group == "OVER_OVER_PT"
    assert added.target_market_key == SEL_OVER_2_5
    assert added.evaluation_status == EVAL_RESULT_MISSING


def test_revaluate_sync_missing_triggers_backfill():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    with patch(
        "app.services.cecchino.cecchino_signal_evaluation.remap_under_over_activations_in_range",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill.build_signal_diagnostics",
        return_value={
            "fixtures_with_signal_matrix_count": 3,
            "current_signal_activations_count": 0,
        },
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill.backfill_signal_activations",
        return_value={"status": "ok", "signals_created": 5},
    ) as mock_backfill:
        out = revaluate_signal_activations(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            sync_missing=True,
        )

    mock_backfill.assert_called_once()
    assert out["backfill_summary"]["signals_created"] == 5


def test_summary_include_diagnostics():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []

    with patch(
        "app.services.cecchino.cecchino_signal_backfill.build_signal_diagnostics",
        return_value={"today_fixtures_count": 5, "signal_activations_count": 0},
    ):
        summary = build_signals_summary(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            include_diagnostics=True,
        )

    assert summary["diagnostics"]["today_fixtures_count"] == 5


def _draw_si_fixture_row(*, book: float = 3.40, cecchino: float = 3.20, **kwargs) -> CecchinoTodayFixture:
    row = _fixture_row(**kwargs)
    row.kpi_panel_json = _kpi_panel(SEL_DRAW, book=book, cecchino=cecchino)
    return row


def test_sync_value_gate_creates_when_book_above_cecchino():
    db = MagicMock()
    row = _draw_si_fixture_row(book=3.40, cecchino=3.20)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 2
    assert counts["value_passed"] == 1
    assert counts["draw_pt_created"] == 1
    assert counts["si_cells_seen"] == 1
    assert counts["no_value_skipped"] == 0


def test_sync_value_gate_creates_when_book_equals_cecchino():
    db = MagicMock()
    row = _draw_si_fixture_row(book=3.20, cecchino=3.20)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 2
    assert counts["value_passed"] == 1
    assert counts["draw_pt_created"] == 1


def test_sync_value_gate_skips_when_book_below_cecchino():
    db = MagicMock()
    row = _draw_si_fixture_row(book=2.90, cecchino=3.20)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 0
    assert counts["no_value_skipped"] == 1
    assert counts["value_passed"] == 0
    assert not db.add.called


def test_sync_value_gate_deactivates_existing_no_value_without_delete():
    db = MagicMock()
    row = _draw_si_fixture_row(book=2.90, cecchino=3.20)
    existing = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="DRAW",
        signal_label="SEGNO X",
        source_column="EXCEL_D",
        signal_value=True,
        target_market_key=SEL_DRAW,
        target_period="FT",
        evaluation_status=EVAL_WON,
        is_current=True,
    )
    existing.id = 1
    db.get.return_value = row
    db.scalars.return_value.all.return_value = [existing]

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 0
    assert counts["deactivated_no_value"] == 1
    assert existing.is_current is False
    assert existing.deactivated_at is not None
    assert existing.evaluation_reason == "no_value_book_below_cecchino"
    assert not db.add.called


def test_sync_value_gate_skips_missing_kpi_panel():
    db = MagicMock()
    row = _draw_si_fixture_row()
    row.kpi_panel_json = None
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["created"] == 0
    assert counts["missing_book_quote_skipped"] == 1
    assert counts["no_value_skipped"] == 1


def test_sync_value_gate_skips_missing_book_quote():
    db = MagicMock()
    row = _draw_si_fixture_row()
    row.kpi_panel_json = {"rows": [{"market_key": SEL_DRAW, "quota_cecchino": 3.20}]}
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["missing_book_quote_skipped"] == 1
    assert counts["no_value_skipped"] == 1


def test_sync_value_gate_skips_missing_cecchino_quote():
    db = MagicMock()
    row = _draw_si_fixture_row()
    row.kpi_panel_json = {"rows": [{"market_key": SEL_DRAW, "quota_book": 3.40}]}
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)

    assert counts["missing_cecchino_quote_skipped"] == 1


def test_sync_value_gate_no_evaluate_when_no_value():
    db = MagicMock()
    row = _draw_si_fixture_row(book=2.90, cecchino=3.20)
    row.ft_home_goals = 1
    row.ft_away_goals = 1
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    with patch(
        "app.services.cecchino.cecchino_signal_sync.evaluate_signal_activation",
    ) as mock_eval:
        sync_cecchino_signal_activations(db, 99)

    mock_eval.assert_not_called()


def test_backfill_aggregates_value_gate_counters():
    db = MagicMock()
    fixture = _fixture_row()
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.return_value = 0

    sync_return = {
        "created": 1,
        "updated": 0,
        "deactivated": 0,
        "skipped": 0,
        "si_cells_seen": 2,
        "value_passed": 1,
        "no_value_skipped": 1,
        "missing_book_quote_skipped": 0,
        "missing_cecchino_quote_skipped": 0,
        "invalid_quote_skipped": 0,
        "deactivated_no_value": 0,
    }

    with patch(
        "app.services.cecchino.cecchino_signal_backfill.sync_cecchino_signal_activations",
        return_value=sync_return,
    ), patch(
        "app.services.cecchino.cecchino_signal_backfill.remap_under_over_activations_in_range",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_signal_odds_refresh.refresh_activation_odds_from_kpi",
        return_value={"odds_refreshed": 0},
    ):
        out = backfill_signal_activations(
            db,
            date_from=date(2026, 6, 8),
            date_to=date(2026, 6, 8),
            evaluate_after=False,
        )

    assert out["si_cells_seen"] == 2
    assert out["value_passed"] == 1
    assert out["no_value_skipped"] == 1
    assert out["missing_value_quote"] == 0


def test_diagnostics_includes_monitoring_note():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.side_effect = [0, 0, 0]
    db.execute.return_value.all.return_value = []

    diag = build_signal_diagnostics(db, date_from=date(2026, 6, 8), date_to=date(2026, 6, 8))

    assert "monitoring_note" in diag
    assert "quota book >= quota Cecchino" in diag["monitoring_note"]
    assert diag["value_eligible_activations_count"] == diag["current_signal_activations_count"]


def test_matrix_unchanged_by_value_gate():
    matrix = build_signals_matrix(q1=2.50, qx=3.20, q2=2.90, sample_home_away_split=16)
    assert matrix["status"] == STATUS_AVAILABLE
    assert isinstance(matrix["rows"], list)
