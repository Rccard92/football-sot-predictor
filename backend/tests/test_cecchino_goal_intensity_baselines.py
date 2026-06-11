"""Test baseline Intensità Goal — Cecchino Fase 47/48."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_goal_intensity_baselines import (
    _median_baselines,
    _over_distribution,
    _try_scope_baseline,
    _try_scope_over_baseline,
    clear_goal_intensity_baseline_cache,
    get_goal_intensity_baselines,
    get_goal_intensity_over_baseline,
    percentile_rank_percent,
)


def _fixture_row(fid: int, kickoff: datetime) -> MagicMock:
    fx = MagicMock()
    fx.id = fid
    fx.kickoff_at = kickoff
    fx.goals_home = 1
    fx.goals_away = 1
    return fx


def test_median_baselines():
    pairs = [(1.8, 3.0), (2.0, 2.8), (1.6, 3.2)]
    med_over, med_under = _median_baselines(pairs)
    assert med_over == pytest.approx(1.8)
    assert med_under == pytest.approx(3.0)


def test_percentile_rank_proportion_leq():
    assert percentile_rank_percent([1, 2, 3, 4, 5], 4) == pytest.approx(80.0)


def test_over_distribution_percentiles():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    dist = _over_distribution(values)
    assert dist["median_over_q44"] == pytest.approx(3.0)
    assert dist["p20_over_q44"] is not None
    assert dist["p80_over_q44"] is not None


def test_try_scope_over_baseline_min_sample():
    db = MagicMock()
    fixtures = [_fixture_row(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 25)]
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._collect_over_values",
        return_value=[1.8] * 25,
    ):
        result = _try_scope_over_baseline(db, fixtures, source="league", min_sample=30)
    assert result is None

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._collect_over_values",
        return_value=[1.8] * 30,
    ):
        result = _try_scope_over_baseline(db, fixtures, source="league", min_sample=30)
    assert result is not None
    assert result["source"] == "league"
    assert result["sample_size"] == 30
    assert result["median_over_q44"] == pytest.approx(1.8)
    assert result["method"] == "percentile_distribution"
    assert "p20_over_q44" in result


def test_try_scope_baseline_min_sample():
    db = MagicMock()
    fixtures = [_fixture_row(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 25)]
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._collect_pairs",
        return_value=[(1.8, 3.0)] * 25,
    ):
        result = _try_scope_baseline(db, fixtures, source="league", min_sample=30)
    assert result is None

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._collect_pairs",
        return_value=[(1.8, 3.0)] * 30,
    ):
        result = _try_scope_baseline(db, fixtures, source="league", min_sample=30)
    assert result is not None
    assert result["source"] == "league"
    assert result["sample_size"] == 30
    assert result["baseline_over_q44"] == pytest.approx(1.8)
    assert result["method"] == "median"


def test_get_goal_intensity_over_baseline_fallback_league():
    clear_goal_intensity_baseline_cache()
    db = MagicMock()
    target = MagicMock()
    target.id = 999
    target.competition_id = 10
    target.kickoff_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    league_result = {
        "source": "league",
        "sample_size": 35,
        "median_over_q44": 1.8,
        "p20_over_q44": 1.2,
        "p40_over_q44": 1.5,
        "p60_over_q44": 2.0,
        "p80_over_q44": 2.5,
        "method": "percentile_distribution",
        "over_values": [1.8] * 35,
    }

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines.load_league_finished_fixtures_before",
        return_value=[MagicMock()] * 35,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_over_baseline",
        side_effect=[league_result, None, None],
    ):
        result = get_goal_intensity_over_baseline(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] == "league"
    assert result["sample_size"] == 35
    assert result["median_over_q44"] == pytest.approx(1.8)


def test_get_goal_intensity_over_baseline_fallback_country():
    clear_goal_intensity_baseline_cache()
    db = MagicMock()
    target = MagicMock()
    target.id = 1000
    target.competition_id = 10
    target.kickoff_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    country_result = {
        "source": "country",
        "sample_size": 45,
        "median_over_q44": 1.7,
        "p20_over_q44": 1.1,
        "p40_over_q44": 1.4,
        "p60_over_q44": 1.9,
        "p80_over_q44": 2.4,
        "method": "percentile_distribution",
        "over_values": [1.7] * 45,
    }

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines.load_league_finished_fixtures_before",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._load_country_finished_fixtures_before",
        return_value=[MagicMock()] * 45,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_over_baseline",
        side_effect=[None, country_result, None],
    ):
        result = get_goal_intensity_over_baseline(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] == "country"


def test_get_goal_intensity_over_baseline_fallback_global():
    clear_goal_intensity_baseline_cache()
    db = MagicMock()
    target = MagicMock()
    target.id = 1001
    target.competition_id = 10
    target.kickoff_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    global_result = {
        "source": "global",
        "sample_size": 55,
        "median_over_q44": 1.75,
        "p20_over_q44": 1.15,
        "p40_over_q44": 1.45,
        "p60_over_q44": 1.95,
        "p80_over_q44": 2.45,
        "method": "percentile_distribution",
        "over_values": [1.75] * 55,
    }

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines.load_league_finished_fixtures_before",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._load_country_finished_fixtures_before",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._load_global_finished_fixtures_before",
        return_value=[MagicMock()] * 55,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_over_baseline",
        side_effect=[None, None, global_result],
    ):
        result = get_goal_intensity_over_baseline(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] == "global"


def test_get_goal_intensity_over_baseline_insufficient():
    clear_goal_intensity_baseline_cache()
    db = MagicMock()
    target = MagicMock()
    target.id = 1002
    target.competition_id = 10
    target.kickoff_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines.load_league_finished_fixtures_before",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._load_country_finished_fixtures_before",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._load_global_finished_fixtures_before",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_over_baseline",
        return_value=None,
    ):
        result = get_goal_intensity_over_baseline(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] is None
    assert result["sample_size"] == 0
    assert result["median_over_q44"] is None


def test_get_goal_intensity_baselines_fallback_league():
    clear_goal_intensity_baseline_cache()
    db = MagicMock()
    target = MagicMock()
    target.id = 999
    target.competition_id = 10
    target.kickoff_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    league_result = {
        "source": "league",
        "sample_size": 35,
        "baseline_over_q44": 1.8,
        "baseline_under_q44": 3.0,
        "method": "median",
    }

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines.load_league_finished_fixtures_before",
        return_value=[MagicMock()] * 35,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_baseline",
        side_effect=[league_result, None, None],
    ):
        result = get_goal_intensity_baselines(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] == "league"
    assert result["sample_size"] == 35
