"""Test xG storico campionato corrente — Cecchino Fase 52."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models import FixtureTeamStat
from app.services.cecchino.cecchino_current_season_xg import (
    MIN_XG_SAMPLE_AVAILABLE,
    SOURCE_NAME,
    build_current_season_team_xg_profile,
    extract_expected_goals_from_fixture_statistics,
)
from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
    _finalize_xg_entry,
    _resolve_variables,
)

FIXTURE_STATS = [
    {
        "team": {"id": 101, "name": "Home Team"},
        "statistics": [{"type": "expected_goals", "value": "2.24"}],
    },
    {
        "team": {"id": 202, "name": "Away Team"},
        "statistics": [{"type": "Expected Goals", "value": "0.19"}],
    },
]


def test_extract_expected_goals_from_fixture_statistics():
    out = extract_expected_goals_from_fixture_statistics(FIXTURE_STATS)
    assert out["home"] == pytest.approx(2.24)
    assert out["away"] == pytest.approx(0.19)
    assert out["home_team_id"] == 101
    assert out["away_team_id"] == 202


def _make_fixture(
    fid: int,
    *,
    api_fixture_id: int,
    home_id: int = 1,
    away_id: int = 2,
    kickoff: datetime | None = None,
) -> MagicMock:
    fx = MagicMock()
    fx.id = fid
    fx.api_fixture_id = api_fixture_id
    fx.home_team_id = home_id
    fx.away_team_id = away_id
    fx.kickoff_at = kickoff or datetime(2026, 6, 9, 20, 0, tzinfo=timezone.utc)
    fx.competition_id = 10
    fx.season_id = 99
    fx.home_team = MagicMock(api_team_id=101)
    fx.away_team = MagicMock(api_team_id=202)
    return fx


def _stat_row(fixture_id: int, team_id: int, xg: float) -> MagicMock:
    st = MagicMock(spec=FixtureTeamStat)
    st.fixture_id = fixture_id
    st.team_id = team_id
    st.expected_goals = xg
    st.raw_json = {
        "statistics": [{"type": "expected_goals", "value": str(xg)}],
    }
    return st


def test_build_profile_three_matches_averages():
    target = _make_fixture(100, api_fixture_id=9000)
    prior = [
        _make_fixture(1, api_fixture_id=1001, kickoff=datetime(2026, 5, 1, tzinfo=timezone.utc)),
        _make_fixture(2, api_fixture_id=1002, kickoff=datetime(2026, 5, 8, tzinfo=timezone.utc)),
        _make_fixture(3, api_fixture_id=1003, kickoff=datetime(2026, 5, 15, tzinfo=timezone.utc)),
    ]
    db = MagicMock()

    stats_map = {
        (1, 1): _stat_row(1, 1, 1.20),
        (1, 2): _stat_row(1, 2, 0.80),
        (2, 1): _stat_row(2, 1, 2.00),
        (2, 2): _stat_row(2, 2, 1.00),
        (3, 1): _stat_row(3, 1, 0.90),
        (3, 2): _stat_row(3, 2, 1.30),
    }

    with patch(
        "app.services.cecchino.cecchino_current_season_xg.load_finished_fixtures_for_team",
        return_value=prior,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg._team_stats_map",
        return_value=stats_map,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg._resolve_season_league_ids",
        return_value=(2026, 31, 72),
    ):
        profile = build_current_season_team_xg_profile(db, target, team_id=1)

    assert profile["sample_size"] == 3
    assert profile["xg_for_avg"] == pytest.approx(1.3667, rel=1e-3)
    assert profile["xg_against_avg"] == pytest.approx(1.0333, rel=1e-3)
    assert profile["source"] == SOURCE_NAME


def test_anti_leakage_excludes_current_fixture():
    target = _make_fixture(100, api_fixture_id=9000)
    prior = [
        target,
        _make_fixture(1, api_fixture_id=1001, kickoff=datetime(2026, 5, 1, tzinfo=timezone.utc)),
    ]
    db = MagicMock()
    stats_map = {
        (1, 1): _stat_row(1, 1, 1.5),
        (1, 2): _stat_row(1, 2, 0.5),
    }

    with patch(
        "app.services.cecchino.cecchino_current_season_xg.load_finished_fixtures_for_team",
        return_value=prior,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg._team_stats_map",
        return_value=stats_map,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg._resolve_season_league_ids",
        return_value=(2026, 31, 72),
    ):
        profile = build_current_season_team_xg_profile(
            db,
            target,
            team_id=1,
            exclude_provider_fixture_id=9000,
        )

    assert profile["sample_size"] == 1
    assert "current_fixture_xg_excluded_to_prevent_leakage" in profile["warnings"]


@pytest.mark.parametrize(
    ("sample_size", "value", "expected_status"),
    [
        (0, None, "missing"),
        (1, 1.1, "insufficient_sample"),
        (2, 1.2, "insufficient_sample"),
        (3, 1.3, "available"),
    ],
)
def test_finalize_xg_entry_availability(sample_size: int, value: float | None, expected_status: str):
    entry = {
        "key": "home_xg_for",
        "label": "xG For Casa",
        "warnings": [],
    }
    profile = {
        "sample_size": sample_size,
        "xg_for_avg": value,
        "warnings": [],
        "anti_leakage": {"current_fixture_excluded": True, "scope": "current season matches before fixture"},
    }
    out = _finalize_xg_entry(
        entry,
        profile,
        value_key="xg_for_avg",
        source_field="statistics[type=expected_goals].value averaged as team xG For",
        ideal_sample=10,
    )
    assert out["availability_status"] == expected_status
    if expected_status == "missing":
        assert out["available"] is False
    else:
        assert out["available"] is True
        assert out["value"] == pytest.approx(float(value))


def test_diagnostics_xg_variables_use_current_season_source():
    db = MagicMock()
    fixture = _make_fixture(200, api_fixture_id=8000)

    profile_home = {
        "sample_size": 4,
        "xg_for_avg": 1.42,
        "xg_against_avg": 1.18,
        "warnings": ["current_fixture_xg_excluded_to_prevent_leakage"],
        "anti_leakage": {
            "current_fixture_excluded": True,
            "fixture_date_cutoff": "2026-06-09T20:00:00+00:00",
            "scope": "current season matches before fixture",
        },
    }
    profile_away = {
        "sample_size": 4,
        "xg_for_avg": 0.88,
        "xg_against_avg": 1.42,
        "warnings": [],
        "anti_leakage": profile_home["anti_leakage"],
    }

    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics.build_current_season_team_xg_profile",
        side_effect=[profile_home, profile_away],
    ), patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics._resolve_context",
    ) as ctx_mock:
        ctx_mock.return_value = {
            "slices": MagicMock(
                home_total_10=MagicMock(over_2_5_hits=0, sample=0),
                away_total_10=MagicMock(over_2_5_hits=0, sample=0),
                home_home_5=MagicMock(total_goals=0, sample=0),
                away_away_5=MagicMock(total_goals=0, sample=0),
            ),
            "home_home_10": [],
            "away_away_10": [],
            "combined_last_10": [],
            "ht_home": MagicMock(sample=0, goals_for=0, over_pt_0_5_hits=0),
            "ht_away": MagicMock(sample=0, goals_for=0, over_pt_0_5_hits=0),
        }
        variables = _resolve_variables(db, fixture, exclude_provider_fixture_id=8000)

    for key in ("home_xg_for", "home_xg_against", "away_xg_for", "away_xg_against"):
        assert variables[key]["source"] == SOURCE_NAME
        assert variables[key]["period"] == "current_season_before_fixture"
        assert variables[key].get("anti_leakage") is not None
        assert variables[key].get("note")

    assert variables["home_xg_for"]["availability_status"] == "available"
    assert variables["home_xg_for"]["value"] == pytest.approx(1.42)
    assert variables["rolling_avg_goals_last_10"]["source"] is None or variables["rolling_avg_goals_last_10"]["source"] == "cecchino_fixture_history"
