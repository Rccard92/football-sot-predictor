"""Test baseline Intensità Goal v2 — Cecchino Fase 47."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_goal_intensity_baselines import (
    _median_baselines,
    _try_scope_baseline,
    clear_goal_intensity_baseline_cache,
    get_goal_intensity_baselines,
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


def test_get_goal_intensity_baselines_fallback_country():
    clear_goal_intensity_baseline_cache()
    db = MagicMock()
    target = MagicMock()
    target.id = 1000
    target.competition_id = 10
    target.kickoff_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    country_result = {
        "source": "country",
        "sample_size": 45,
        "baseline_over_q44": 1.7,
        "baseline_under_q44": 2.9,
        "method": "median",
    }

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines.load_league_finished_fixtures_before",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._load_country_finished_fixtures_before",
        return_value=[MagicMock()] * 45,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_baseline",
        side_effect=[None, country_result, None],
    ):
        result = get_goal_intensity_baselines(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] == "country"


def test_get_goal_intensity_baselines_fallback_global():
    clear_goal_intensity_baseline_cache()
    db = MagicMock()
    target = MagicMock()
    target.id = 1001
    target.competition_id = 10
    target.kickoff_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    global_result = {
        "source": "global",
        "sample_size": 55,
        "baseline_over_q44": 1.75,
        "baseline_under_q44": 2.95,
        "method": "median",
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
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_baseline",
        side_effect=[None, None, global_result],
    ):
        result = get_goal_intensity_baselines(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] == "global"


def test_get_goal_intensity_baselines_insufficient():
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
        "app.services.cecchino.cecchino_goal_intensity_baselines._try_scope_baseline",
        return_value=None,
    ):
        result = get_goal_intensity_baselines(
            db,
            target,
            competition_id=10,
            country_name="Italy",
        )

    assert result["source"] is None
    assert result["sample_size"] == 0
    assert result["baseline_over_q44"] is None
