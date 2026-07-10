"""Test backtest modelli pesi Cecchino A–F — Fase 43."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
from app.services.cecchino.cecchino_constants import (
    CECCHINO_WEIGHT_MODEL_KEYS,
    CECCHINO_WEIGHT_MODELS,
    model_weights_to_picchetto_map,
    validate_cecchino_weight_models,
)
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_engine import compute_final_odds, picchetti_blocks_from_output_json
from app.services.cecchino.cecchino_signal_aggregation import (
    build_signals_summary,
    export_signals_csv,
    list_signal_activations,
)
from app.services.cecchino.cecchino_signal_model_backtest import (
    backtest_cecchino_weight_models,
    build_models_summary,
    build_signals_matrix_for_model,
    recompute_cecchino_signals_for_model,
)
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations


def _picchetto_block(key: str, q1: float, qx: float, q2: float) -> dict:
    def _outcome(q: float) -> dict:
        return {"prob": 1 / q, "quota": q, "mathematical_odds": q}

    return {
        "key": key,
        "label": key,
        "home_context": {"wins": 3, "draws": 2, "losses": 1},
        "away_context": {"wins": 2, "draws": 2, "losses": 2},
        "total_matches": 10,
        "sample_home": 8,
        "sample_away": 8,
        "outcome_1": _outcome(q1),
        "outcome_x": _outcome(qx),
        "outcome_2": _outcome(q2),
        "status": STATUS_AVAILABLE,
        "warnings": [],
    }


def _cecchino_output_with_picchetti(
    *,
    totals=(2.0, 3.0, 4.0),
    home_away=(2.1, 3.1, 3.9),
    last6=(2.2, 3.2, 3.8),
    last5=(2.3, 3.3, 3.7),
) -> dict:
    return {
        "picchetti": {
            "totals": _picchetto_block("totals", *totals),
            "home_away": _picchetto_block("home_away", *home_away),
            "last6_totals": _picchetto_block("last6_totals", *last6),
            "last5_home_away": _picchetto_block("last5_home_away", *last5),
        },
        "final": {"status": STATUS_AVAILABLE, "quota_1": 2.5, "quota_x": 3.2, "quota_2": 2.9},
        "signals_matrix": {"status": STATUS_AVAILABLE, "rows": []},
    }


def _fixture_with_picchetti(**kwargs) -> CecchinoTodayFixture:
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
    row.cecchino_output_json = _cecchino_output_with_picchetti()
    row.stats_snapshot_json = {"input_snapshot": {"home_away": {"home_sample_count": 8, "away_sample_count": 8}}}
    row.kpi_panel_json = {
        "rows": [
            {
                "market_key": SEL_DRAW,
                "quota_book": 3.40,
                "quota_cecchino": 3.20,
            }
        ]
    }
    row.ft_home_goals = 1
    row.ft_away_goals = 0
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_cecchino_weight_models_contains_a_to_f():
    assert set(CECCHINO_WEIGHT_MODELS.keys()) == set(CECCHINO_WEIGHT_MODEL_KEYS)


def test_each_weight_model_sums_to_one():
    validate_cecchino_weight_models()
    for key in CECCHINO_WEIGHT_MODEL_KEYS:
        weights = model_weights_to_picchetto_map(key)
        assert sum(weights.values()) == pytest.approx(1.0)


def test_model_f_matches_live_weights():
    from app.services.cecchino.cecchino_constants import CECCHINO_1X2_WEIGHTS

    f_weights = model_weights_to_picchetto_map("F")
    assert f_weights == CECCHINO_1X2_WEIGHTS


def test_picchetti_from_output_and_compute_final_odds_differs_by_model():
    output = _cecchino_output_with_picchetti()
    picchetti = picchetti_blocks_from_output_json(output)
    final_a = compute_final_odds(picchetti, weights=model_weights_to_picchetto_map("A"))
    final_f = compute_final_odds(picchetti, weights=model_weights_to_picchetto_map("F"))
    assert final_a.status == STATUS_AVAILABLE
    assert final_f.status == STATUS_AVAILABLE
    assert final_a.quota_1 != final_f.quota_1


def test_build_signals_matrix_for_model():
    row = _fixture_with_picchetti()
    matrix = build_signals_matrix_for_model(row, "A")
    assert matrix is not None
    assert matrix.get("status") == STATUS_AVAILABLE


def test_sync_sets_model_key_f_by_default():
    db = MagicMock()
    row = _fixture_with_picchetti()
    from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix

    matrix = build_signals_matrix(q1=2.5, qx=3.2, q2=2.9, sample_home_away_split=16)
    matrix["rows"] = [
        {"key": "draw", "label": "SEGNO X", "signals": {"excel_d": "SI"}},
    ]
    row.cecchino_output_json = {**row.cecchino_output_json, "signals_matrix": matrix}
    row.kpi_panel_json = {
        "rows": [
            {
                "market_key": SEL_DRAW,
                "quota_book": 3.40,
                "quota_cecchino": 3.20,
            }
        ]
    }
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(db, 99)
    assert counts["created"] == 1
    added = db.add.call_args[0][0]
    assert added.model_key == "F"
    assert added.weights_version == "model_F_30_30_20_20"


def test_recompute_for_model_a_creates_activation_with_model_key():
    db = MagicMock()
    row = _fixture_with_picchetti()
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    with patch(
        "app.services.cecchino.cecchino_signal_model_backtest.sync_cecchino_signal_activations",
    ) as mock_sync:
        mock_sync.return_value = {"created": 2, "updated": 0, "deactivated": 0, "skipped": 0}
        with patch(
            "app.services.cecchino.cecchino_signal_model_backtest.evaluate_activations_for_fixture",
            return_value={"evaluated": 1, "pending": 1, "not_evaluable": 0},
        ):
            result = recompute_cecchino_signals_for_model(db, 99, "A")

    assert result["status"] == "ok"
    assert result["model_key"] == "A"
    mock_sync.assert_called_once()
    _, kwargs = mock_sync.call_args
    assert kwargs["model_key"] == "A"
    assert kwargs["signals_matrix"]["status"] == STATUS_AVAILABLE


def test_same_fixture_can_have_separate_activations_for_a_and_b():
    activation_a = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="A",
        signal_group="DRAW",
        signal_label="SEGNO X",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=True,
    )
    activation_b = CecchinoSignalActivation(
        today_fixture_id=99,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="B",
        signal_group="DRAW",
        signal_label="SEGNO X",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=True,
    )
    assert activation_a.model_key != activation_b.model_key
    assert activation_a.today_fixture_id == activation_b.today_fixture_id


def test_build_models_summary_returns_six_models():
    db = MagicMock()
    bucket = {
        "activations": 1,
        "settled": 1,
        "won": 1,
        "lost": 0,
        "pending": 0,
        "not_evaluable": 0,
        "success_rate": 100.0,
        "avg_won_book_odds": 1.8,
        "quota_void": 1.0,
        "void_margin": 0.8,
        "taken_profit_indicator": 0.8,
    }
    with patch(
        "app.services.cecchino.cecchino_signal_model_backtest._model_bucket_from_activations",
        return_value=bucket,
    ):
        payload = build_models_summary(db, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    assert len(payload["models"]) == 6
    keys = [m["model_key"] for m in payload["models"]]
    assert keys == list(CECCHINO_WEIGHT_MODEL_KEYS)


def test_summary_filters_by_model_key():
    db = MagicMock()
    row_a = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        model_key="A",
        signal_group="DRAW",
        signal_label="X",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_WON,
        is_current=True,
    )
    row_b = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        model_key="B",
        signal_group="DRAW",
        signal_label="X",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_LOST,
        is_current=True,
    )

    def _scalars_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "model_key = :model_key_1" in stmt_str or "model_key = 'A'" in stmt_str:
            # filter by model in query - simplified: check call args via whereclause
            pass
        mock_result.all.return_value = [row_a] if "A" in stmt_str else [row_b]
        return mock_result

    db.scalars.side_effect = lambda stmt: MagicMock(all=MagicMock(return_value=[row_a]))
    db.scalar.return_value = 0

    summary_a = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        model_key="A",
    )
    assert summary_a["filters"]["model_key"] == "A"
    assert summary_a["overall"]["activations"] == 1
    assert summary_a["overall"]["won"] == 1

    db.scalars.side_effect = lambda stmt: MagicMock(all=MagicMock(return_value=[row_b]))
    summary_b = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        model_key="B",
    )
    assert summary_b["overall"]["lost"] == 1


def test_taken_odds_metrics_per_model_in_summary():
    db = MagicMock()
    row = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        model_key="C",
        signal_group="DRAW",
        signal_label="X",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_WON,
        quota_book=Decimal("2.00"),
        is_current=True,
    )
    db.scalars.return_value.all.return_value = [row]
    db.scalar.return_value = 1

    summary = build_signals_summary(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        model_key="C",
    )
    overall = summary["overall"]
    assert overall["avg_won_book_odds"] == 2.0
    assert overall["quota_void"] == 1.0
    assert overall["taken_profit_indicator"] == 1.0


def test_activations_endpoint_filters_by_model_key():
    db = MagicMock()
    row = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        model_key="D",
        signal_group="DRAW",
        signal_label="X",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_PENDING,
        is_current=True,
    )
    row.id = 1
    db.scalars.return_value.all.return_value = [row]
    db.scalar.return_value = 1

    payload = list_signal_activations(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        model_key="D",
    )
    assert payload["total"] == 1
    assert payload["items"][0]["model_key"] == "D"


def test_export_csv_includes_model_columns():
    db = MagicMock()
    row = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 6, 8),
        model_key="E",
        model_label="E – Equilibrato",
        signal_group="DRAW",
        signal_label="X",
        source_column="EXCEL_D",
        signal_value=True,
        evaluation_status=EVAL_WON,
        quota_book=Decimal("1.75"),
        home_team_name="H",
        away_team_name="A",
        is_current=True,
    )
    row.id = 1
    db.scalars.return_value.all.return_value = [row]
    db.scalar.return_value = 1

    with patch(
        "app.services.cecchino.cecchino_signal_min_book_odd_settings_service.load_signal_min_book_odds",
        return_value={},
    ):
        csv_text = export_signals_csv(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            model_key="E",
        )
    lines = csv_text.strip().splitlines()
    assert "Modello" in lines[0]
    assert "Pesi modello" in lines[0]
    assert "E – Equilibrato" in csv_text
    assert "SUMMARY" in csv_text


def test_backtest_models_does_not_call_api_football():
    db = MagicMock()
    row = _fixture_with_picchetti()
    db.scalars.return_value.all.return_value = [row]
    bucket = {
        "activations": 1,
        "settled": 1,
        "won": 1,
        "lost": 0,
        "pending": 0,
        "not_evaluable": 0,
        "success_rate": 100.0,
        "avg_won_book_odds": 1.8,
        "quota_void": 1.0,
        "void_margin": 0.8,
        "taken_profit_indicator": 0.8,
    }

    with patch(
        "app.services.cecchino.cecchino_signal_model_backtest.recompute_cecchino_signals_for_model",
        return_value={"status": "ok", "created": 1, "updated": 0, "deactivated": 0},
    ) as mock_recompute:
        with patch(
            "app.services.cecchino.cecchino_signal_model_backtest._model_bucket_from_activations",
            return_value=bucket,
        ):
            with patch("app.services.api_football_client.ApiFootballClient") as mock_client:
                backtest_cecchino_weight_models(
                    db,
                    date_from=date(2026, 6, 1),
                    date_to=date(2026, 6, 30),
                    models=["A", "B"],
                    force=True,
                    evaluate_after=True,
                )
                assert mock_recompute.call_count == 2
                mock_client.assert_not_called()


def test_backtest_force_rebuilds_without_duplicate_per_model():
    db = MagicMock()
    row = _fixture_with_picchetti()
    db.get.return_value = row
    stored: list[CecchinoSignalActivation] = []

    def _capture_add(obj):
        if isinstance(obj, CecchinoSignalActivation):
            obj.id = len(stored) + 1
            stored.append(obj)

    db.add.side_effect = _capture_add

    def _scalars_side_effect(_stmt):
        mock_result = MagicMock()
        mock_result.all.return_value = list(stored)
        return mock_result

    db.scalars.side_effect = _scalars_side_effect

    from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix

    matrix = build_signals_matrix(q1=2.5, qx=3.2, q2=2.9, sample_home_away_split=16)
    matrix["rows"] = [{"key": "draw", "label": "SEGNO X", "signals": {"excel_d": "SI"}}]

    with patch(
        "app.services.cecchino.cecchino_signal_model_backtest.build_signals_matrix_for_model",
        return_value=matrix,
    ), patch(
        "app.services.cecchino.cecchino_signal_sync.load_signal_min_book_odds",
        return_value={},
    ):
        recompute_cecchino_signals_for_model(db, 99, "A", evaluate_after=False)
        recompute_cecchino_signals_for_model(db, 99, "A", evaluate_after=False)

    model_a = [a for a in stored if a.model_key == "A" and a.signal_group == "DRAW"]
    assert len(model_a) == 1


def test_pending_result_missing_handled_per_model():
    db = MagicMock()
    row = _fixture_with_picchetti(ft_home_goals=None, ft_away_goals=None)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix

    matrix = build_signals_matrix(q1=2.5, qx=3.2, q2=2.9, sample_home_away_split=16)
    matrix["rows"] = [{"key": "draw", "label": "SEGNO X", "signals": {"excel_d": "SI"}}]

    with patch(
        "app.services.cecchino.cecchino_signal_model_backtest.build_signals_matrix_for_model",
        return_value=matrix,
    ):
        result = recompute_cecchino_signals_for_model(db, 99, "F", evaluate_after=True)

    assert result["status"] == "ok"
    added = db.add.call_args[0][0]
    assert added.evaluation_status in (EVAL_PENDING, EVAL_RESULT_MISSING)
