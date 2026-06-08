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
    _success_rate,
    build_signals_summary,
    export_signals_csv,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_signal_activation,
    revaluate_signal_activations,
)
from app.services.cecchino.cecchino_signal_backfill import (
    backfill_signal_activations,
    build_signal_diagnostics,
)
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_signal_target_mapping import (
    map_cecchino_signal_to_target,
    map_row_key_to_signal_group,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
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


def test_under_over_generic_not_evaluable():
    under = map_cecchino_signal_to_target("UNDER_UNDER_PT", "EXCEL_D")
    over = map_cecchino_signal_to_target("OVER_OVER_PT", "EXCEL_E")
    assert under["target_market_key"] is None
    assert under["evaluation_status"] == EVAL_NOT_EVALUABLE
    assert over["evaluation_status"] == EVAL_NOT_EVALUABLE


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


def test_sync_saves_only_si_and_is_idempotent():
    db = MagicMock()
    row = _fixture_row()
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts1 = sync_cecchino_signal_activations(db, 99)
    assert counts1["created"] == 1
    assert db.add.called

    existing = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        signal_group="DRAW",
        signal_label="SEGNO X",
        source_column="EXCEL_D",
        signal_value=True,
        target_market_key=SEL_DRAW,
        target_period="FT",
        evaluation_status=EVAL_PENDING,
    )
    existing.id = 1
    db.scalars.return_value.all.return_value = [existing]
    db.add.reset_mock()

    counts2 = sync_cecchino_signal_activations(db, 99)
    assert counts2["updated"] == 1
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
    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    assert summary["overall"]["won"] == 1
    assert summary["overall"]["lost"] == 1
    assert summary["overall"]["success_rate"] == 50.0
    assert len(summary["by_signal_and_column"]) == 1


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
    assert "SEGNO X" in csv_text
    assert "EXCEL_D" in csv_text


def test_revaluate_does_not_call_api():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [99]
    with patch(
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
    mock_eval.assert_called_once_with(db, 99)
    db.commit.assert_called_once()


def test_diagnostics_detects_fixtures_without_activations():
    db = MagicMock()
    fixture = _fixture_row()
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.side_effect = [0, 0]
    db.execute.return_value.all.return_value = []

    diag = build_signal_diagnostics(db, date_from=date(2026, 6, 8), date_to=date(2026, 6, 8))
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
    ) as mock_sync:
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
        "app.services.api_football_client.ApiFootballClient",
    ) as mock_client:
        backfill_signal_activations(
            db,
            date_from=date(2026, 6, 8),
            date_to=date(2026, 6, 8),
            evaluate_after=False,
        )
    mock_client.assert_not_called()


def test_revaluate_sync_missing_triggers_backfill():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    with patch(
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
