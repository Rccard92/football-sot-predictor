"""Test sync/backfill con soglie minime quota book Cecchino."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.models.cecchino_signal_activation import CecchinoSignalActivation
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
    PROVIDER_API_FOOTBALL,
)
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_DRAW_PT, SEL_ONE_X
from app.services.cecchino.cecchino_signal_backfill import backfill_signal_activations
from app.services.cecchino.cecchino_signal_min_odds import DEFAULT_SIGNAL_MIN_BOOK_ODDS
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_signal_value_gate import (
    DEACTIVATION_REASON_BOOK_BELOW_MIN,
    VALUE_REASON_BOOK_BELOW_MIN,
)


def _kpi_rows(*rows: dict) -> dict:
    return {"rows": list(rows)}


def _one_x_fixture_row(*, book: float, cecchino: float) -> CecchinoTodayFixture:
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
    row.kpi_panel_json = _kpi_rows(
        {"market_key": SEL_ONE_X, "quota_book": book, "quota_cecchino": cecchino},
    )
    return row


def _draw_fixture_row(*, draw_book: float, draw_cecchino: float, pt_book: float, pt_cecchino: float):
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
    row.id = 101
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": STATUS_AVAILABLE,
            "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9},
            "rows": [{"key": "draw", "label": "SEGNO X", "signals": {"excel_d": "SI"}}],
        },
    }
    row.kpi_panel_json = _kpi_rows(
        {"market_key": SEL_DRAW, "quota_book": draw_book, "quota_cecchino": draw_cecchino},
        {"market_key": SEL_DRAW_PT, "quota_book": pt_book, "quota_cecchino": pt_cecchino},
    )
    return row


def test_sync_si_below_min_threshold_does_not_create_activation():
    db = MagicMock()
    row = _one_x_fixture_row(book=1.30, cecchino=1.20)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(
        db, 100, min_book_odds=DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    )

    assert counts["created"] == 0
    assert counts["min_book_odd_skipped"] == 1
    assert counts["no_value_skipped"] == 1
    assert not db.add.called


def test_sync_si_at_threshold_creates_activation():
    db = MagicMock()
    row = _one_x_fixture_row(book=1.37, cecchino=1.30)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(
        db, 100, min_book_odds=DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    )

    assert counts["created"] == 1
    assert counts["value_passed"] == 1
    assert counts["min_book_odd_threshold_applied"] == 1


def test_sync_deactivates_existing_current_below_min_threshold():
    db = MagicMock()
    row = _one_x_fixture_row(book=1.30, cecchino=1.20)
    activation = CecchinoSignalActivation(
        today_fixture_id=100,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="ONE_X",
        signal_label="SEGNO 1X",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=True,
        target_market_key=SEL_ONE_X,
    )
    db.get.return_value = row
    db.scalars.return_value.all.return_value = [activation]

    counts = sync_cecchino_signal_activations(
        db, 100, min_book_odds=DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    )

    assert activation.is_current is False
    assert activation.evaluation_reason == DEACTIVATION_REASON_BOOK_BELOW_MIN
    assert counts["deactivated_min_book_odd"] == 1
    assert not db.add.called


def test_sync_above_threshold_keeps_current():
    db = MagicMock()
    row = _one_x_fixture_row(book=1.40, cecchino=1.30)
    activation = CecchinoSignalActivation(
        today_fixture_id=100,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="ONE_X",
        signal_label="SEGNO 1X",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=True,
        target_market_key=SEL_ONE_X,
    )
    db.get.return_value = row
    db.scalars.return_value.all.return_value = [activation]

    counts = sync_cecchino_signal_activations(
        db, 100, min_book_odds=DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    )

    assert activation.is_current is True
    assert counts["updated"] == 1
    assert counts["deactivated_min_book_odd"] == 0


def test_sync_no_delete_on_deactivation():
    db = MagicMock()
    row = _one_x_fixture_row(book=1.30, cecchino=1.20)
    activation = CecchinoSignalActivation(
        today_fixture_id=100,
        provider_fixture_id=12345,
        scan_date=date(2026, 6, 8),
        model_key="F",
        signal_group="ONE_X",
        signal_label="SEGNO 1X",
        source_column="EXCEL_D",
        signal_value=True,
        is_current=True,
    )
    db.get.return_value = row
    db.scalars.return_value.all.return_value = [activation]

    sync_cecchino_signal_activations(db, 100, min_book_odds=DEFAULT_SIGNAL_MIN_BOOK_ODDS)

    db.delete.assert_not_called()


def test_draw_pt_below_min_threshold_skips_pt_but_draw_passes():
    db = MagicMock()
    row = _draw_fixture_row(draw_book=3.10, draw_cecchino=2.90, pt_book=1.85, pt_cecchino=1.70)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    counts = sync_cecchino_signal_activations(
        db, 101, min_book_odds=DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    )

    assert counts["created"] == 1
    assert counts["draw_pt_created"] == 0
    assert counts["min_book_odd_skipped"] == 1
    groups = {call.args[0].signal_group for call in db.add.call_args_list}
    assert groups == {"DRAW"}


def test_draw_pt_uses_real_x_pt_quotes():
    db = MagicMock()
    row = _draw_fixture_row(draw_book=3.10, draw_cecchino=2.90, pt_book=1.95, pt_cecchino=1.80)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []

    sync_cecchino_signal_activations(db, 101, min_book_odds=DEFAULT_SIGNAL_MIN_BOOK_ODDS)

    pt = next(call.args[0] for call in db.add.call_args_list if call.args[0].signal_group == "DRAW_PT")
    assert float(pt.quota_book) == pytest.approx(1.95)
    assert float(pt.quota_cecchino) == pytest.approx(1.80)
    assert pt.target_market_key == SEL_DRAW_PT


def test_backfill_merges_min_book_odd_counters(monkeypatch):
    db = MagicMock()
    row = _one_x_fixture_row(book=1.30, cecchino=1.20)
    row.eligibility_status = ELIGIBILITY_ELIGIBLE

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_min_book_odd_settings_service.load_signal_min_book_odds",
        lambda _db: DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_backfill._fixtures_in_range",
        lambda _db, _f, _t: [row],
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_backfill._fixture_has_current_activations",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_backfill._ensure_signals_matrix_on_row",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_backfill.sync_cecchino_signal_activations",
        lambda *_a, **_k: {
            "created": 0,
            "updated": 0,
            "deactivated": 0,
            "si_cells_seen": 1,
            "no_value_skipped": 1,
            "min_book_odd_skipped": 1,
            "deactivated_min_book_odd": 0,
            "min_book_odd_threshold_applied": 1,
        },
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_backfill.remap_under_over_activations_in_range",
        lambda *_a, **_k: 0,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_odds_refresh.refresh_activation_odds_from_kpi",
        lambda *_a, **_k: {"odds_refreshed": 0},
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_backfill._activation_status_counts",
        lambda *_a, **_k: {
            "won": 0,
            "lost": 0,
            "pending": 0,
            "not_evaluable": 0,
            "evaluated_count": 0,
        },
    )

    payload = backfill_signal_activations(
        db,
        date_from=date(2026, 6, 8),
        date_to=date(2026, 6, 8),
        only_missing=False,
        evaluate_after=False,
        force_remap=False,
    )

    assert payload["min_book_odd_skipped"] == 1
    assert payload["min_book_odd_threshold_applied"] == 1
    assert VALUE_REASON_BOOK_BELOW_MIN == "book_odd_below_min_threshold"
