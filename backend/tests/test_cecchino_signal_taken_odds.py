"""Test Quota media prese e Quota Void — Cecchino Fase 42."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON
from app.services.cecchino.cecchino_signal_aggregation import (
    _enrich_taken_odds_metrics,
    build_signals_summary,
)
from app.services.cecchino.cecchino_signal_evaluation import revaluate_signal_activations
from app.services.cecchino.cecchino_signal_odds_refresh import (
    apply_kpi_odds_to_activation,
    refresh_activation_odds_from_kpi,
    resolve_kpi_odds_for_activation,
)
from app.services.cecchino.cecchino_selection_keys import SEL_HOME


def _row(status: str, quota: float | None = None):
    return SimpleNamespace(
        evaluation_status=status,
        quota_book=Decimal(str(quota)) if quota is not None else None,
    )


def test_avg_won_book_odds_uses_only_won_with_quota():
    rows = [
        _row(EVAL_WON, 1.70),
        _row(EVAL_WON, 1.80),
        _row(EVAL_LOST, 2.50),
        _row(EVAL_WON, None),
    ]
    bucket = _enrich_taken_odds_metrics({"won": 3, "lost": 1, "settled": 4}, rows)
    assert bucket["won_with_odds"] == 2
    assert bucket["avg_won_book_odds"] == pytest.approx(1.75)


def test_lost_not_in_avg_won_book_odds():
    rows = [_row(EVAL_LOST, 2.00), _row(EVAL_LOST, 3.00)]
    bucket = _enrich_taken_odds_metrics({"won": 0, "lost": 2, "settled": 2}, rows)
    assert bucket["won_with_odds"] == 0
    assert bucket["avg_won_book_odds"] is None


def test_won_without_quota_excluded():
    rows = [_row(EVAL_WON, None), _row(EVAL_WON, 2.00)]
    bucket = _enrich_taken_odds_metrics({"won": 2, "lost": 0, "settled": 2}, rows)
    assert bucket["won_with_odds"] == 1
    assert bucket["avg_won_book_odds"] == pytest.approx(2.00)


def test_quota_void_formula():
    rows = [_row(EVAL_WON, 1.70) for _ in range(7)] + [_row(EVAL_LOST, 3.00) for _ in range(3)]
    bucket = _enrich_taken_odds_metrics({"won": 7, "lost": 3, "settled": 10}, rows)
    assert bucket["quota_void"] == pytest.approx(1.43, abs=0.01)


def test_void_margin_formula():
    rows = [_row(EVAL_WON, 1.74) for _ in range(7)] + [_row(EVAL_LOST, 2.00) for _ in range(3)]
    bucket = _enrich_taken_odds_metrics({"won": 7, "lost": 3, "settled": 10}, rows)
    assert bucket["void_margin"] == pytest.approx(
        bucket["avg_won_book_odds"] - bucket["quota_void"],
        abs=0.01,
    )


def test_taken_yield_and_profit():
    rows = [_row(EVAL_WON, 2.00) for _ in range(6)] + [_row(EVAL_LOST, 2.00) for _ in range(4)]
    bucket = _enrich_taken_odds_metrics({"won": 6, "lost": 4, "settled": 10}, rows)
    win_rate = 0.6
    assert bucket["taken_yield_index"] == pytest.approx(win_rate * 2.0, abs=0.001)
    assert bucket["taken_profit_indicator"] == pytest.approx(bucket["taken_yield_index"] - 1.0, abs=0.001)


def test_example_7_won_3_lost_odds():
    won_odds = [1.70, 1.80, 1.60, 2.00, 1.50, 1.90, 1.75]
    rows = [_row(EVAL_WON, o) for o in won_odds] + [_row(EVAL_LOST, 3.00) for _ in range(3)]
    bucket = _enrich_taken_odds_metrics({"won": 7, "lost": 3, "settled": 10}, rows)
    expected_avg = sum(won_odds) / len(won_odds)
    assert bucket["avg_won_book_odds"] == pytest.approx(round(expected_avg, 2))
    assert bucket["won_with_odds"] == 7


def test_resolve_kpi_odds_by_target_market_key():
    kpi = {
        "rows": [
            {"market_key": SEL_HOME, "quota_book": 2.10, "quota_cecchino": 2.05, "rating": 55},
        ],
    }
    ctx = resolve_kpi_odds_for_activation(kpi, signal_group="HOME", target_market_key=SEL_HOME)
    assert ctx["quota_book"] == 2.10


def test_apply_kpi_odds_to_activation():
    activation = MagicMock()
    activation.signal_group = "HOME"
    activation.target_market_key = SEL_HOME
    activation.quota_book = None
    activation.quota_cecchino = None
    activation.prob_book = None
    activation.prob_cecchino = None
    activation.edge_pct = None
    activation.rating = None

    kpi = {"rows": [{"market_key": SEL_HOME, "quota_book": 1.95, "rating": 60}]}
    assert apply_kpi_odds_to_activation(activation, kpi) is True
    assert activation.quota_book == Decimal("1.95")
    assert activation.rating == 60


def test_refresh_activation_odds_from_kpi_offline():
    from app.models.cecchino_signal_activation import CecchinoSignalActivation
    from app.models.cecchino_today_fixture import CecchinoTodayFixture

    activation = CecchinoSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=100,
        scan_date=date(2026, 6, 1),
        signal_group="HOME",
        signal_label="1",
        source_column="EXCEL_D",
        target_market_key=SEL_HOME,
    )
    activation.is_current = True
    activation.signal_value = True

    fixture = CecchinoTodayFixture(
        id=1,
        provider_fixture_id=100,
        scan_date=date(2026, 6, 1),
        kpi_panel_json={
            "rows": [{"market_key": SEL_HOME, "quota_book": 2.20, "rating": 70}],
        },
    )

    db = MagicMock()
    db.scalars.return_value.all.side_effect = [[activation], [fixture]]

    with patch(
        "app.services.cecchino.cecchino_signal_odds_refresh.apply_kpi_odds_to_activation",
        return_value=True,
    ) as mock_apply:
        result = refresh_activation_odds_from_kpi(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 7),
        )

    assert result["odds_refreshed"] == 1
    mock_apply.assert_called_once()


def test_revaluate_refresh_signal_odds_no_api_football():
    db = MagicMock()
    with (
        patch(
            "app.services.cecchino.cecchino_signal_evaluation.remap_under_over_activations_in_range",
            return_value=0,
        ),
        patch(
            "app.services.cecchino.cecchino_signal_odds_refresh.refresh_activation_odds_from_kpi",
            return_value={"odds_refreshed": 5, "odds_still_missing": 1, "odds_skipped_no_kpi": 0},
        ) as mock_refresh,
        patch(
            "app.services.cecchino.cecchino_signal_evaluation.evaluate_activations_for_fixture",
            return_value={"evaluated": 1, "pending": 0, "not_evaluable": 0},
        ),
    ):
        db.scalars.return_value.all.return_value = [42]
        db.commit = MagicMock()

        result = revaluate_signal_activations(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 7),
            refresh_signal_odds=True,
        )

    mock_refresh.assert_called_once()
    assert result["odds_refresh_summary"]["odds_refreshed"] == 5


def test_build_signals_summary_includes_taken_odds(db_session=None):
    """Summary overall/by_signal/by_combo include taken odds fields."""
    rows = []
    for _ in range(5):
        r = MagicMock()
        r.evaluation_status = EVAL_WON
        r.quota_book = Decimal("1.80")
        r.signal_group = "HOME"
        r.signal_label = "1"
        r.source_column = "EXCEL_D"
        r.today_fixture_id = 1
        rows.append(r)
    for _ in range(2):
        r = MagicMock()
        r.evaluation_status = EVAL_LOST
        r.quota_book = Decimal("2.50")
        r.signal_group = "HOME"
        r.signal_label = "1"
        r.source_column = "EXCEL_D"
        r.today_fixture_id = 1
        rows.append(r)

    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    db.scalar.side_effect = [0, 0]

    with patch(
        "app.services.cecchino.cecchino_signal_aggregation._count_eligible_fixtures",
        return_value=1,
    ):
        summary = build_signals_summary(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 7),
        )

    assert summary["overall"]["avg_won_book_odds"] == pytest.approx(1.80)
    assert summary["overall"]["quota_void"] is not None
    assert "taken_profit_indicator" in summary["overall"]
    assert summary["by_signal"][0]["avg_won_book_odds"] == pytest.approx(1.80)
    assert summary["by_signal_and_column"][0]["void_margin"] is not None
