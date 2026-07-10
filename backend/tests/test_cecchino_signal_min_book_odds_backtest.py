"""Test save-and-backtest soglie quota book."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.cecchino.cecchino_constants import CECCHINO_WEIGHT_MODEL_KEYS
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_ONE_X
from app.services.cecchino.cecchino_signal_min_book_odds_backtest_service import (
    save_signal_min_book_odds_and_backtest,
)
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations


def _backfill_payload(**overrides) -> dict:
    base = {
        "fixtures_found": 2,
        "fixtures_with_signals": 2,
        "si_cells_seen": 4,
        "value_passed": 3,
        "no_value_skipped": 1,
        "min_book_odd_skipped": 1,
        "deactivated_min_book_odd": 0,
        "missing_book_quote_skipped": 0,
        "missing_cecchino_quote_skipped": 0,
        "invalid_quote_skipped": 0,
        "deactivated_no_value": 0,
        "signals_created": 2,
        "signals_updated": 1,
        "signals_deactivated": 0,
        "evaluated": 2,
        "won": 1,
        "lost": 0,
        "pending": 1,
        "not_evaluable": 0,
        "warnings": [],
    }
    base.update(overrides)
    return base


def _models_payload(**overrides) -> dict:
    base = {
        "status": "ok",
        "fixtures_found": 2,
        "models_processed": list(CECCHINO_WEIGHT_MODEL_KEYS),
        "by_model": [],
        "value_passed": 10,
        "min_book_odd_skipped": 4,
        "deactivated_min_book_odd": 2,
        "warnings": [],
    }
    base.update(overrides)
    return base


def test_save_and_backtest_orchestrates_save_backfill_and_models():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.save_signal_min_book_odds",
        return_value={"items": []},
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.load_signal_min_book_odds",
        return_value={SEL_DRAW: Decimal("2.80")},
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.backfill_signal_activations",
        return_value=_backfill_payload(),
    ) as backfill_mock, patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.backtest_cecchino_weight_models",
        return_value=_models_payload(),
    ) as models_mock:
        result = save_signal_min_book_odds_and_backtest(
            db,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 5),
            items=[{"target_market_key": SEL_DRAW, "min_book_odd": 2.80}],
            rebuild_kpi_from_cache=False,
        )

    assert result["status"] == "ok"
    assert result["backtest"]["value_passed"] == 3
    assert result["backtest"]["min_book_odd_skipped"] == 1
    assert result["backtest"]["models_processed"] == list(CECCHINO_WEIGHT_MODEL_KEYS)
    assert result["backtest"]["models_value_passed"] == 10
    assert result["default_backtest"]["value_passed"] == 3
    assert result["models_backtest"]["models_processed"] == list(CECCHINO_WEIGHT_MODEL_KEYS)

    backfill_mock.assert_called_once()
    backfill_kwargs = backfill_mock.call_args.kwargs
    assert backfill_kwargs["only_missing"] is False
    assert backfill_kwargs["force_remap"] is True
    assert backfill_kwargs["min_book_odds"][SEL_DRAW] == Decimal("2.80")

    models_mock.assert_called_once()
    models_kwargs = models_mock.call_args.kwargs
    assert models_kwargs["models"] == list(CECCHINO_WEIGHT_MODEL_KEYS)
    assert models_kwargs["force"] is True
    assert models_kwargs["min_book_odds"][SEL_DRAW] == Decimal("2.80")


def test_save_and_backtest_optional_kpi_rebuild():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.save_signal_min_book_odds",
        return_value={"items": []},
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.load_signal_min_book_odds",
        return_value={SEL_DRAW: Decimal("2.80")},
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.rebuild_kpi_panels_from_cache",
        return_value={"status": "ok", "errors": []},
    ) as rebuild_mock, patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.backfill_signal_activations",
        return_value=_backfill_payload(fixtures_found=0),
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.backtest_cecchino_weight_models",
        return_value=_models_payload(fixtures_found=0),
    ):
        result = save_signal_min_book_odds_and_backtest(
            db,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 2),
            items=[{"target_market_key": SEL_DRAW, "min_book_odd": 2.80}],
            rebuild_kpi_from_cache=True,
        )
    rebuild_mock.assert_called_once()
    assert result["status"] == "ok"
    assert "default_backtest" in result
    assert "models_backtest" in result


def test_save_and_backtest_lowered_threshold_increases_value_passed():
    db = MagicMock()
    strict_backfill = _backfill_payload(value_passed=1, min_book_odd_skipped=3)
    relaxed_backfill = _backfill_payload(value_passed=3, min_book_odd_skipped=1)

    with patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.save_signal_min_book_odds",
        return_value={"items": []},
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.load_signal_min_book_odds",
        side_effect=[{SEL_DRAW: Decimal("3.00")}, {SEL_DRAW: Decimal("2.80")}],
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.backfill_signal_activations",
        side_effect=[strict_backfill, relaxed_backfill],
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.backtest_cecchino_weight_models",
        return_value=_models_payload(),
    ):
        strict = save_signal_min_book_odds_and_backtest(
            db,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 5),
            items=[{"target_market_key": SEL_DRAW, "min_book_odd": 3.00}],
        )
        relaxed = save_signal_min_book_odds_and_backtest(
            db,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 5),
            items=[{"target_market_key": SEL_DRAW, "min_book_odd": 2.80}],
        )

    assert strict["default_backtest"]["value_passed"] == 1
    assert strict["default_backtest"]["min_book_odd_skipped"] == 3
    assert relaxed["default_backtest"]["value_passed"] == 3
    assert relaxed["default_backtest"]["min_book_odd_skipped"] == 1


def test_recompute_for_model_forwards_min_book_odds():
    from app.services.cecchino.cecchino_signal_model_backtest import recompute_cecchino_signals_for_model

    db = MagicMock()
    row = MagicMock()
    row.cecchino_output_json = {"picchetti": {"home": {}, "away": {}}}
    db.get.return_value = row
    custom = {SEL_DRAW: Decimal("2.50")}
    with patch(
        "app.services.cecchino.cecchino_signal_model_backtest.build_signals_matrix_for_model",
        return_value={"status": "available", "rows": []},
    ), patch(
        "app.services.cecchino.cecchino_signal_model_backtest.sync_cecchino_signal_activations",
        return_value={"created": 1},
    ) as sync_mock, patch(
        "app.services.cecchino.cecchino_signal_model_backtest.evaluate_activations_for_fixture",
        return_value={},
    ):
        recompute_cecchino_signals_for_model(
            db, 42, "A", evaluate_after=False, min_book_odds=custom,
        )

    sync_mock.assert_called_once()
    assert sync_mock.call_args.kwargs["min_book_odds"] == custom


def test_sync_reactivates_with_lowered_threshold():
    from app.models.cecchino_signal_activation import CecchinoSignalActivation
    from app.models.cecchino_today_fixture import (
        ELIGIBILITY_ELIGIBLE,
        CecchinoTodayFixture,
        PROVIDER_API_FOOTBALL,
    )
    from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE

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
    row.id = 100
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [
                {"key": "one_x", "label": "SEGNO 1X", "signals": {"excel_d": "SI"}},
            ],
        },
    }
    row.kpi_panel_json = {
        "rows": [
            {"market_key": SEL_ONE_X, "quota_book": 1.40, "quota_cecchino": 1.30},
        ],
    }

    activation = CecchinoSignalActivation(
        today_fixture_id=100,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="ONE_X",
        signal_label="SEGNO 1X",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=False,
        target_market_key=SEL_ONE_X,
        evaluation_reason="deactivated_book_odd_below_min_threshold",
    )

    custom_odds = {SEL_ONE_X: Decimal("1.35")}
    mock_db = MagicMock()
    mock_db.get.return_value = row
    mock_db.scalars.return_value.all.return_value = [activation]

    counts = sync_cecchino_signal_activations(mock_db, 100, min_book_odds=custom_odds)

    assert activation.is_current is True
    assert activation.deactivated_at is None
    assert counts["updated"] == 1
    mock_db.delete.assert_not_called()
