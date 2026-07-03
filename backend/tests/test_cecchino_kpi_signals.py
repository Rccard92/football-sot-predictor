"""Test Segnali KPI Cecchino (modulo separato)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_kpi_signal_activation import (
    KPI_EVAL_LOST,
    KPI_EVAL_PENDING,
    KPI_EVAL_WON,
    CecchinoKpiSignalActivation,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_kpi_signals import (
    compute_profit_units,
    extract_kpi_rating_score,
    extract_kpi_signal_candidates,
    normalize_kpi_row,
    rating_bucket,
    sync_kpi_signals_for_fixture,
)
from app.services.cecchino.cecchino_kpi_signals_aggregation import _profit_metrics
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_UNDER_PT_1_5, SEL_X_TWO
from app.services.cecchino.cecchino_signal_evaluation import evaluate_market_selection


def _kpi_row(**kwargs):
    base = {
        "market_key": "HOME",
        "segno": "1",
        "label": "1",
        "quota_book": 2.0,
        "quota_cecchino": 1.8,
        "rating": 75,
        "rating_label": "Premium",
    }
    base.update(kwargs)
    return base


def test_rating_49_not_candidate():
    row = normalize_kpi_row(_kpi_row(rating=49))
    assert row is None


def test_rating_50_bucket_50_59():
    row = normalize_kpi_row(_kpi_row(rating=50))
    assert row is not None
    assert row["rating_bucket"] == "50-59"


def test_rating_89_bucket_80_89():
    row = normalize_kpi_row(_kpi_row(rating=89))
    assert row is not None
    assert row["rating_bucket"] == "80-89"


def test_rating_100_bucket_100():
    row = normalize_kpi_row(_kpi_row(rating=100))
    assert row is not None
    assert row["rating_bucket"] == "100"


def test_missing_quota_book_not_candidate():
    row = normalize_kpi_row(_kpi_row(quota_book=None))
    assert row is None


def test_parse_rating_premium_string():
    assert extract_kpi_rating_score({"rating": "89 Premium"}) == 89


def test_parse_rating_elite_string():
    assert extract_kpi_rating_score({"rating": "100 Elite"}) == 100


def test_eval_away_wins_when_away_ft_greater():
    result = evaluate_market_selection(
        SEL_AWAY,
        {"fulltime": {"home": 1, "away": 2}, "halftime": {"home": 0, "away": 1}},
    )
    assert result["evaluation_status"] == KPI_EVAL_WON


def test_eval_x2_wins_on_draw():
    result = evaluate_market_selection(
        SEL_X_TWO,
        {"fulltime": {"home": 1, "away": 1}, "halftime": {"home": 0, "away": 0}},
    )
    assert result["evaluation_status"] == KPI_EVAL_WON


def test_eval_under_pt_15_wins_when_ht_total_le_1():
    result = evaluate_market_selection(
        SEL_UNDER_PT_1_5,
        {"fulltime": {"home": 2, "away": 1}, "halftime": {"home": 1, "away": 0}},
    )
    assert result["evaluation_status"] == KPI_EVAL_WON


def test_profit_won_is_quota_minus_one():
    assert compute_profit_units(KPI_EVAL_WON, Decimal("2.5")) == Decimal("1.5")


def test_profit_lost_is_minus_one():
    assert compute_profit_units(KPI_EVAL_LOST, Decimal("2.5")) == Decimal("-1")


def test_roi_and_quota_void():
    rows = [
        MagicMock(
            evaluation_status=KPI_EVAL_WON,
            quota_book=Decimal("2.0"),
            profit_units=Decimal("1.0"),
        ),
        MagicMock(
            evaluation_status=KPI_EVAL_LOST,
            quota_book=Decimal("1.8"),
            profit_units=Decimal("-1"),
        ),
    ]
    metrics = _profit_metrics(rows)
    assert metrics["settled"] == 2
    assert metrics["profit_units"] == 0.0
    assert metrics["roi_pct"] == 0.0
    assert metrics["quota_void"] == 2.0


def test_pending_when_ft_missing():
    result = evaluate_market_selection(
        SEL_AWAY,
        {"fulltime": {"home": None, "away": None}, "halftime": {"home": None, "away": None}},
    )
    assert result["evaluation_status"] == "result_missing"


def test_backfill_range_no_external_api():
    db = MagicMock()
    fixture = MagicMock()
    fixture.id = 1
    fixture.eligibility_status = ELIGIBILITY_ELIGIBLE
    fixture.kpi_panel_json = {"version": "cecchino_kpi_v2_betfair", "rows": [_kpi_row(rating=80)]}
    db.scalars.return_value.all.return_value = [fixture]
    db.scalar.return_value = None

    with patch(
        "app.services.cecchino.cecchino_kpi_signals.sync_kpi_signals_for_fixture",
        return_value={"created": 1, "updated": 0, "deactivated": 0, "evaluated": 1},
    ) as sync_mock:
        with patch("app.services.cecchino.cecchino_kpi_signals.revaluate_kpi_signals_for_range", return_value={}):
            from app.services.cecchino.cecchino_kpi_signals import sync_kpi_signals_for_range

            sync_kpi_signals_for_range(
                db,
                date_from=date(2026, 6, 18),
                date_to=date(2026, 7, 4),
                only_missing=False,
            )
    sync_mock.assert_called_once()
    db.commit.assert_called()


def test_extract_candidates_from_fixture():
    fixture = MagicMock()
    fixture.kpi_panel_json = {
        "rows": [
            _kpi_row(rating=100),
            _kpi_row(market_key="AWAY", segno="2", label="2", rating=40),
            _kpi_row(rating=55, quota_book=None),
        ],
    }
    candidates = extract_kpi_signal_candidates(fixture)
    assert len(candidates) == 1
    assert candidates[0]["rating_score"] == 100


def test_sync_does_not_touch_signal_activations_table():
    db = MagicMock()
    row = MagicMock()
    row.id = 10
    row.provider_fixture_id = 999
    row.scan_date = date(2026, 7, 4)
    row.kickoff = datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc)
    row.country_name = "Italy"
    row.league_name = "Serie A"
    row.home_team_name = "A"
    row.away_team_name = "B"
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    row.kpi_panel_json = {"version": "cecchino_kpi_v2_betfair", "rows": [_kpi_row(rating=90, market_key="AWAY", segno="2", label="2")]}
    row.score_fulltime_home = 0
    row.score_fulltime_away = 2
    row.score_halftime_home = 0
    row.score_halftime_away = 1
    row.match_display_status = "finished"
    row.fixture_status = "FT"
    db.get.return_value = row
    db.scalar.return_value = None
    added: list = []

    def _track_add(obj):
        added.append(obj)

    db.add.side_effect = _track_add
    db.flush = MagicMock()

    sync_kpi_signals_for_fixture(db, 10)
    assert len(added) == 1
    assert isinstance(added[0], CecchinoKpiSignalActivation)
    assert added[0].selection_key == SEL_AWAY
