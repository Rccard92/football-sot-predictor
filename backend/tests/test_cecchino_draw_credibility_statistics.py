"""Test analisi statistica Credibilità X — Fase 1C."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, MATCH_FINISHED, CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_draw_credibility_research_common import (
    COHORT_ELIGIBLE_PRIMARY,
    resolve_cecchino_final_version,
)
from app.services.cecchino.cecchino_draw_credibility_statistics import (
    VERSION,
    _enrich_research_features,
    _quantile_bins,
    auc_mann_whitney,
    bootstrap_auc,
    brier_score,
    build_draw_credibility_statistical_analysis,
    classify_trend,
    log_loss_score,
    pearson_r,
    spearman_rho,
    wilson_ci,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME, SEL_OVER_2_5, SEL_UNDER_2_5


def _final(**kwargs) -> dict:
    base = {
        "status": STATUS_AVAILABLE,
        "quota_1": 2.0,
        "quota_x": 3.2,
        "quota_2": 3.5,
        "prob_1": 0.45,
        "prob_x": 0.28,
        "prob_2": 0.27,
    }
    base.update(kwargs)
    return base


def _goal_markets() -> dict:
    return {
        SEL_UNDER_2_5: {"final_odd": 1.85, "status": STATUS_AVAILABLE, "probability": 0.52},
        SEL_OVER_2_5: {"final_odd": 2.05, "status": STATUS_AVAILABLE, "probability": 0.48},
    }


def _kpi_panel(*, with_book: bool = True) -> dict:
    rows = [
        {"market_key": SEL_HOME, "quota_cecchino": 2.0, "quota_book": 2.1 if with_book else None},
        {"market_key": SEL_DRAW, "quota_cecchino": 3.2, "quota_book": 3.3 if with_book else None},
        {"market_key": SEL_AWAY, "quota_cecchino": 3.5, "quota_book": 3.6 if with_book else None},
        {"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85, "quota_book": 1.9 if with_book else None},
        {"market_key": SEL_OVER_2_5, "quota_cecchino": 2.05, "quota_book": 2.1 if with_book else None},
    ]
    return {"version": "cecchino_kpi_v2_betfair", "rows": rows}


def _row(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    kickoff = datetime(2025, 6, 15, 18, 0, tzinfo=timezone.utc)
    created = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
    defaults = {
        "id": 1,
        "provider_fixture_id": 9001,
        "local_fixture_id": 501,
        "scan_date": date(2025, 6, 15),
        "competition_id": 39,
        "country_name": "England",
        "league_name": "Premier League",
        "home_team_name": "Home FC",
        "away_team_name": "Away FC",
        "match_display_status": MATCH_FINISHED,
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "score_fulltime_home": 1,
        "score_fulltime_away": 1,
        "goals_home": 1,
        "goals_away": 1,
        "kickoff": kickoff,
        "created_at": created,
        "cecchino_output_json": {"version": "cecchino_v1", "final": _final(), "goal_markets": _goal_markets()},
        "kpi_panel_json": _kpi_panel(),
        "odds_snapshot_json": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


class TestWilsonCi:
    def test_zero_n(self):
        assert wilson_ci(0, 0)["lower_pct"] is None

    def test_perfect_rate(self):
        ci = wilson_ci(10, 10)
        assert ci["lower_pct"] is not None
        assert ci["upper_pct"] == 100.0

    def test_half_rate(self):
        ci = wilson_ci(50, 100)
        assert 40 <= ci["lower_pct"] <= 50 <= ci["upper_pct"] <= 60

    def test_bounds_within_0_100(self):
        ci = wilson_ci(1, 1000)
        assert ci["lower_pct"] >= 0
        assert ci["upper_pct"] <= 100


class TestAuc:
    def test_perfect_separation(self):
        y = [1, 1, 0, 0]
        s = [0.9, 0.8, 0.2, 0.1]
        assert auc_mann_whitney(y, s) == 1.0

    def test_random_scores(self):
        y = [1, 0, 1, 0]
        s = [0.5, 0.5, 0.5, 0.5]
        assert auc_mann_whitney(y, s) == 0.5

    def test_single_class_returns_none(self):
        assert auc_mann_whitney([1, 1], [0.1, 0.2]) is None

    def test_tie_handling(self):
        y = [1, 0, 1, 0]
        s = [0.5, 0.5, 0.6, 0.4]
        assert auc_mann_whitney(y, s) is not None


class TestBootstrap:
    def test_reproducible_seed(self):
        y = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0] * 5
        s = [float(i % 10) / 10 for i in range(len(y))]
        a = bootstrap_auc(y, s, iterations=100, seed=42)
        b = bootstrap_auc(y, s, iterations=100, seed=42)
        assert a["auc"] == b["auc"]

    def test_insufficient_iterations(self):
        y = [1, 0]
        s = [0.9, 0.1]
        out = bootstrap_auc(y, s, iterations=5, seed=1)
        assert out["valid_bootstrap_iterations"] <= 5


class TestCorrelations:
    def test_pearson_perfect_positive(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        assert pearson_r(xs, xs) == pytest.approx(1.0)

    def test_pearson_perfect_negative(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [4.0, 3.0, 2.0, 1.0]
        assert pearson_r(xs, ys) == pytest.approx(-1.0)

    def test_spearman_monotonic(self):
        xs = [1.0, 2.0, 3.0, 100.0]
        ys = [1.0, 2.0, 3.0, 4.0]
        assert spearman_rho(xs, ys) == pytest.approx(1.0)

    def test_pearson_constant_returns_none(self):
        assert pearson_r([1.0, 1.0, 1.0], [2.0, 3.0, 4.0]) is None


class TestQuantileBins:
    def test_empty(self):
        assert _quantile_bins([], 5) == []

    def test_single_value(self):
        bins = _quantile_bins([5.0], 5)
        assert len(bins) >= 1

    def test_five_bins(self):
        vals = list(range(1, 101))
        bins = _quantile_bins([float(v) for v in vals], 5)
        assert 1 <= len(bins) <= 5


class TestTrend:
    def test_increasing(self):
        assert classify_trend([20.0, 25.0, 30.0, 35.0]) == "increasing"

    def test_decreasing(self):
        assert classify_trend([35.0, 30.0, 25.0, 20.0]) == "decreasing"

    def test_flat(self):
        assert classify_trend([25.0, 25.5, 25.2]) == "flat"

    def test_insufficient(self):
        assert classify_trend([25.0, 30.0]) == "insufficient_data"


class TestCalibration:
    def test_brier_perfect(self):
        probs = [1.0, 0.0, 1.0, 0.0]
        y = [1, 0, 1, 0]
        assert brier_score(probs, y) == 0.0

    def test_log_loss_finite(self):
        probs = [0.7, 0.3, 0.6, 0.4]
        y = [1, 0, 1, 0]
        ll = log_loss_score(probs, y)
        assert ll is not None and ll > 0


class TestEnrichFeatures:
    def test_hours_to_kickoff_class(self):
        base = {
            "feature_snapshot_at": "2025-06-15T10:00:00+00:00",
            "kickoff": "2025-06-15T18:00:00+00:00",
            "prob_1_norm": 45.0,
            "prob_x_norm": 28.0,
            "prob_2_norm": 27.0,
        }
        out = _enrich_research_features(base)
        assert out["hours_to_kickoff"] == 8.0
        assert out["hours_to_kickoff_class"] == "<=24h"
        assert out["dominance_normalized_pp"] == 17.0

    def test_x_directional_conviction(self):
        base = {
            "conviction_index_candidate": 12.5,
            "dominant_sign": "X",
            "prob_1_norm": 30.0,
            "prob_x_norm": 40.0,
            "prob_2_norm": 30.0,
            "x_rank": 1,
        }
        out = _enrich_research_features(base)
        assert out["x_directional_conviction_candidate"] == 12.5
        assert out["x_is_top"] == 1


class TestFinalVersionFix:
    def test_weights_not_used_as_version(self):
        final = {"weights": {"totals": 0.5}}
        assert resolve_cecchino_final_version(final) is None


class TestIntegration:
    def test_build_analysis_payload_structure(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = [_row()]
        payload = build_draw_credibility_statistical_analysis(
            db,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
        )
        assert payload["status"] == "ok"
        assert payload["version"] == VERSION
        assert "dataset_summary" in payload
        assert payload["dataset_summary"]["primary"]["rows"] >= 1
        assert "feature_leaderboard" in payload
        assert payload["performance"]["total_ms"] >= 0

    def test_empty_db(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        payload = build_draw_credibility_statistical_analysis(
            db,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
        )
        assert payload["dataset_summary"]["primary"]["rows"] == 0

    @patch(
        "app.services.cecchino.cecchino_draw_credibility_statistics.build_draw_credibility_all_rows",
    )
    def test_uses_shared_all_rows(self, mock_all_rows):
        mock_all_rows.return_value = ([], {})
        db = MagicMock()
        build_draw_credibility_statistical_analysis(
            db, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31),
        )
        mock_all_rows.assert_called_once()

    def test_leaderboard_sorted_by_auc(self):
        db = MagicMock()
        rows = [_row(id=i, provider_fixture_id=9000 + i) for i in range(1, 6)]
        db.scalars.return_value.all.return_value = rows
        payload = build_draw_credibility_statistical_analysis(
            db, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31),
            bootstrap_iterations=100,
        )
        lb = payload["feature_leaderboard"]
        aucs = [x.get("discriminative_auc") or 0 for x in lb]
        assert aucs == sorted(aucs, reverse=True)

    def test_categorical_analysis_present(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = [_row()]
        payload = build_draw_credibility_statistical_analysis(
            db, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31),
        )
        cats = payload["categorical_feature_analysis"][COHORT_ELIGIBLE_PRIMARY]
        assert len(cats) > 0
