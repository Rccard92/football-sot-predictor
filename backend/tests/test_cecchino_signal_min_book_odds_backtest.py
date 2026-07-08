"""Test save-and-backtest soglie quota book."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_ONE_X
from app.services.cecchino.cecchino_signal_min_book_odds_backtest_service import (
    save_signal_min_book_odds_and_backtest,
)
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations


def test_save_and_backtest_orchestrates_save_and_backfill():
    db = MagicMock()
    backfill_payload = {
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
        "evaluated": 2,
        "won": 1,
        "lost": 0,
        "pending": 1,
        "not_evaluable": 0,
        "warnings": [],
    }
    with patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.save_signal_min_book_odds",
        return_value={"items": []},
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.load_signal_min_book_odds",
        return_value={SEL_DRAW: Decimal("2.80")},
    ), patch(
        "app.services.cecchino.cecchino_signal_min_book_odds_backtest_service.backfill_signal_activations",
        return_value=backfill_payload,
    ) as backfill_mock:
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
    backfill_mock.assert_called_once()
    kwargs = backfill_mock.call_args.kwargs
    assert kwargs["only_missing"] is False
    assert kwargs["force_remap"] is True
    assert kwargs["min_book_odds"][SEL_DRAW] == Decimal("2.80")


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
        return_value={"fixtures_found": 0, "warnings": []},
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


def test_sync_reactivates_with_lowered_threshold():
    from datetime import date

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
