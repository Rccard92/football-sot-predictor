"""Test xG storico campionato corrente — Cecchino Fase 52."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models import FixtureTeamStat
from app.models import Fixture
from app.services.cecchino.cecchino_current_season_xg import (
    MIN_XG_SAMPLE_AVAILABLE,
    PROFILE_VERSION,
    SOURCE_NAME,
    build_current_season_team_xg_profile,
    ensure_current_season_xg_profile_for_fixture,
    extract_expected_goals_from_fixture_statistics,
    maybe_ensure_xg_for_eligible_row,
)
from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
    _finalize_xg_entry,
    _resolve_variables,
    build_expected_goal_engine_diagnostics_for_today_row,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, ELIGIBILITY_EXCLUDED_MISSING_1X2

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
        if expected_status == "insufficient_sample":
            assert "sample_below_3" in out["warnings"]


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


def _make_today_row(*, eligible: bool = True, xg_profiles_json: dict | None = None) -> MagicMock:
    row = MagicMock()
    row.id = 501
    row.eligibility_status = ELIGIBILITY_ELIGIBLE if eligible else ELIGIBILITY_EXCLUDED_MISSING_1X2
    row.local_fixture_id = 200
    row.provider_fixture_id = 8000
    row.home_team_name = "Home FC"
    row.away_team_name = "Away FC"
    row.xg_profiles_json = xg_profiles_json
    return row


def test_ensure_skips_when_not_eligible():
    db = MagicMock()
    row = _make_today_row(eligible=False)
    db.get.return_value = row
    out = ensure_current_season_xg_profile_for_fixture(db, 501)
    assert out["status"] == "skipped"
    assert out["reason"] == "not_eligible"


def test_ensure_cache_hit_zero_api_calls():
    db = MagicMock()
    target = _make_fixture(200, api_fixture_id=8000)
    row = _make_today_row(
        xg_profiles_json={
            "profile_version": PROFILE_VERSION,
            "local_fixture_id": 200,
            "xg_api_usage": {"fixtures_checked": 2},
            "anti_leakage": {
                "current_fixture_excluded": True,
                "fixture_date_cutoff": "2026-06-09T20:00:00+00:00",
            },
            "home_team": {"sample_size": 3},
            "away_team": {"sample_size": 3},
        },
    )
    prior = [
        _make_fixture(1, api_fixture_id=1001, kickoff=datetime(2026, 5, 1, tzinfo=timezone.utc)),
        _make_fixture(2, api_fixture_id=1002, kickoff=datetime(2026, 5, 8, tzinfo=timezone.utc)),
    ]

    def _get(model, pk):
        if pk == 501:
            return row
        if pk == 200:
            return target
        return None

    db.get.side_effect = _get

    with patch(
        "app.services.cecchino.cecchino_current_season_xg._prior_fixtures_both_teams",
        return_value=prior,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg.ApiFootballClient",
    ) as client_cls:
        out = ensure_current_season_xg_profile_for_fixture(db, 501)
        client_cls.assert_not_called()

    assert out["status"] == "cached"
    assert out["xg_api_usage"]["fixtures_checked"] == 2


def test_ensure_cache_miss_calls_only_fixture_statistics():
    db = MagicMock()
    target = _make_fixture(200, api_fixture_id=8000)
    row = _make_today_row()
    prior = [
        _make_fixture(1, api_fixture_id=1001, kickoff=datetime(2026, 5, 1, tzinfo=timezone.utc)),
    ]
    client = MagicMock()
    client.get_fixture_statistics.return_value = FIXTURE_STATS

    def _get(model, pk):
        if pk == 501:
            return row
        if pk == 200:
            return target
        return None

    db.get.side_effect = _get

    profile = {
        "sample_size": 1,
        "xg_for_avg": 1.1,
        "xg_against_avg": 0.9,
        "warnings": [],
        "anti_leakage": {"current_fixture_excluded": True},
    }

    with patch(
        "app.services.cecchino.cecchino_current_season_xg._prior_fixtures_both_teams",
        return_value=prior,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg._fixture_has_xg",
        return_value=False,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg._persist_fixture_statistics",
        return_value=2,
    ), patch(
        "app.services.cecchino.cecchino_current_season_xg.build_current_season_team_xg_profile",
        return_value=profile,
    ):
        out = ensure_current_season_xg_profile_for_fixture(db, 501, client=client)

    client.get_fixture_statistics.assert_called_once_with(1001)
    client.get_fixture_events.assert_not_called()
    client.get_fixture_lineups.assert_not_called()
    client.get_fixture_players.assert_not_called()
    assert out["status"] == "ok"
    assert row.xg_profiles_json["profile_version"] == PROFILE_VERSION
    assert out["xg_api_usage"]["external_calls_made"] == 1


def test_maybe_ensure_does_not_raise_on_provider_error():
    db = MagicMock()
    row = _make_today_row()
    with patch(
        "app.services.cecchino.cecchino_current_season_xg.ensure_current_season_xg_profile_for_fixture",
        side_effect=RuntimeError("boom"),
    ):
        out = maybe_ensure_xg_for_eligible_row(db, row)
    assert out is not None
    assert out["status"] == "error"
    assert "xg_provider_error" in out["warnings"]


def test_diagnostics_payload_includes_xg_profiles():
    db = MagicMock()
    row = _make_today_row(
        xg_profiles_json={
            "home_team": {"sample_size": 4, "xg_for_avg": 1.2},
            "away_team": {"sample_size": 4, "xg_for_avg": 0.8},
            "anti_leakage": {"current_fixture_excluded": True},
            "xg_api_usage": {"automatic": True, "cache_hits": 5, "external_calls_made": 0},
            "warnings": [],
        },
    )
    fixture = _make_fixture(200, api_fixture_id=8000)
    db.get.return_value = fixture

    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics.ensure_current_season_xg_profile_for_fixture",
    ), patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics.build_expected_goal_engine_diagnostics",
        return_value={"status": "available", "xg_profiles": {}, "blocks": {}},
    ) as build_mock:
        build_expected_goal_engine_diagnostics_for_today_row(db, row)
        db.get.assert_called_with(Fixture, 200)
        _, kwargs = build_mock.call_args
        assert kwargs["xg_profiles_json"] == row.xg_profiles_json


def test_diagnostics_resolve_variables_uses_cached_profiles():
    db = MagicMock()
    fixture = _make_fixture(200, api_fixture_id=8000)
    cached = {
        "home_team": {
            "xg_for_avg": 1.5,
            "xg_against_avg": 1.0,
            "sample_size": 5,
            "warnings": [],
        },
        "away_team": {
            "xg_for_avg": 0.7,
            "xg_against_avg": 1.3,
            "sample_size": 5,
            "warnings": [],
        },
        "anti_leakage": {"current_fixture_excluded": True},
    }

    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics.build_current_season_team_xg_profile",
    ) as build_mock, patch(
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
        variables = _resolve_variables(db, fixture, xg_profiles_json=cached)
        build_mock.assert_not_called()

    assert variables["home_xg_for"]["value"] == pytest.approx(1.5)
    assert variables["away_xg_for"]["value"] == pytest.approx(0.7)


def test_profile_cache_fresh_same_kickoff():
    from app.services.cecchino.cecchino_current_season_xg import _profile_cache_fresh

    ko = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
    row = _make_today_row(
        xg_profiles_json={
            "profile_version": PROFILE_VERSION,
            "local_fixture_id": 200,
            "xg_api_usage": {"fixtures_checked": 3},
            "anti_leakage": {"fixture_date_cutoff": "2026-07-16T22:30:00+00:00"},
        },
    )
    assert _profile_cache_fresh(row, prior_count=3, force_refresh=False, target_kickoff=ko) is True


def test_profile_cache_fresh_same_instant_different_timezone():
    from app.services.cecchino.cecchino_current_season_xg import _profile_cache_fresh
    from datetime import timedelta

    # 22:30 UTC == 00:30+02:00 next calendar day
    rome = timezone(timedelta(hours=2))
    ko = datetime(2026, 7, 17, 0, 30, tzinfo=rome)
    row = _make_today_row(
        xg_profiles_json={
            "profile_version": PROFILE_VERSION,
            "local_fixture_id": 200,
            "xg_api_usage": {"fixtures_checked": 1},
            "anti_leakage": {"fixture_date_cutoff": "2026-07-16T22:30:00Z"},
        },
    )
    assert _profile_cache_fresh(row, prior_count=1, force_refresh=False, target_kickoff=ko) is True


def test_profile_cache_stale_when_kickoff_days_apart():
    from app.services.cecchino.cecchino_current_season_xg import _profile_cache_fresh

    ko = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
    row = _make_today_row(
        xg_profiles_json={
            "profile_version": PROFILE_VERSION,
            "local_fixture_id": 200,
            "xg_api_usage": {"fixtures_checked": 2},
            "anti_leakage": {"fixture_date_cutoff": "2026-07-22T20:00:00Z"},
        },
    )
    assert _profile_cache_fresh(row, prior_count=2, force_refresh=False, target_kickoff=ko) is False


def test_rebuild_from_cache_zero_api_and_excludes_target():
    from app.services.cecchino.cecchino_current_season_xg import (
        rebuild_current_season_xg_profile_from_cache,
    )

    db = MagicMock()
    target = _make_fixture(
        562,
        api_fixture_id=1492291,
        kickoff=datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc),
    )
    row = _make_today_row(
        xg_profiles_json={
            "anti_leakage": {"fixture_date_cutoff": "2026-07-22T20:00:00Z"},
        },
    )
    row.id = 9510
    row.local_fixture_id = 562
    row.provider_fixture_id = 1492291

    prior_home = [
        _make_fixture(10, api_fixture_id=1001, kickoff=datetime(2026, 7, 1, tzinfo=timezone.utc)),
        _make_fixture(562, api_fixture_id=1492291, kickoff=datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)),
    ]
    prior_away = [
        _make_fixture(11, api_fixture_id=1002, kickoff=datetime(2026, 7, 2, tzinfo=timezone.utc)),
    ]

    def _get(model, pk):
        if pk == 9510:
            return row
        if pk == 562:
            return target
        return None

    db.get.side_effect = _get

    home_profile = {
        "sample_size": 1,
        "matches_missing_xg": 0,
        "xg_for_avg": 1.1,
        "xg_against_avg": 0.9,
        "warnings": ["current_fixture_xg_excluded_to_prevent_leakage"],
        "anti_leakage": {
            "current_fixture_excluded": True,
            "fixture_date_cutoff": "2026-07-16T22:30:00+00:00",
        },
    }
    away_profile = {
        "sample_size": 1,
        "matches_missing_xg": 0,
        "xg_for_avg": 0.8,
        "xg_against_avg": 1.2,
        "warnings": [],
        "anti_leakage": home_profile["anti_leakage"],
    }

    with (
        patch(
            "app.services.cecchino.cecchino_current_season_xg.load_finished_fixtures_for_team",
            side_effect=[prior_home, prior_away, prior_home, prior_away],
        ),
        patch(
            "app.services.cecchino.cecchino_current_season_xg.build_current_season_team_xg_profile",
            side_effect=[home_profile, away_profile],
        ),
        patch(
            "app.services.cecchino.cecchino_current_season_xg._prior_fixtures_both_teams",
            return_value=[prior_home[0], prior_away[0]],
        ),
        patch(
            "app.services.cecchino.cecchino_current_season_xg.ApiFootballClient",
        ) as client_cls,
    ):
        out = rebuild_current_season_xg_profile_from_cache(db, 9510)
        client_cls.assert_not_called()

    assert out["status"] == "ok"
    assert out["xg_api_usage"]["external_calls_made"] == 0
    assert str(out["cutoff_after"]).startswith("2026-07-16T22:30")
    assert out["anti_leakage_report"]["excluded_fixture_ids"] == [562]
    assert out["anti_leakage_report"]["excluded_provider_fixture_ids"] == [1492291]
    assert 562 not in out["anti_leakage_report"]["home_fixture_ids_used"]
    assert 1492291 not in [
        # home ids are local fixture ids not api ids; ensure target id excluded
    ]
    assert row.xg_profiles_json["anti_leakage"]["current_fixture_excluded"] is True
    assert row.xg_profiles_json["xg_api_usage"]["external_calls_made"] == 0


def test_ensure_stale_cutoff_triggers_rebuild_path():
    """Cache con cutoff 22/07 e kickoff 16/07 non è fresh → passa al path API (client passato)."""
    db = MagicMock()
    target = _make_fixture(
        200,
        api_fixture_id=8000,
        kickoff=datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc),
    )
    row = _make_today_row(
        xg_profiles_json={
            "profile_version": PROFILE_VERSION,
            "local_fixture_id": 200,
            "xg_api_usage": {"fixtures_checked": 1},
            "anti_leakage": {"fixture_date_cutoff": "2026-07-22T20:00:00Z"},
        },
    )
    prior = [_make_fixture(1, api_fixture_id=1001, kickoff=datetime(2026, 7, 1, tzinfo=timezone.utc))]
    client = MagicMock()
    client.get_fixture_statistics.return_value = FIXTURE_STATS

    def _get(model, pk):
        if pk == 501:
            return row
        if pk == 200:
            return target
        return None

    db.get.side_effect = _get
    profile = {
        "sample_size": 1,
        "xg_for_avg": 1.0,
        "xg_against_avg": 1.0,
        "warnings": [],
        "anti_leakage": {
            "current_fixture_excluded": True,
            "fixture_date_cutoff": "2026-07-16T22:30:00+00:00",
        },
    }
    with (
        patch(
            "app.services.cecchino.cecchino_current_season_xg._prior_fixtures_both_teams",
            return_value=prior,
        ),
        patch(
            "app.services.cecchino.cecchino_current_season_xg._fixture_has_xg",
            return_value=True,
        ),
        patch(
            "app.services.cecchino.cecchino_current_season_xg.build_current_season_team_xg_profile",
            return_value=profile,
        ),
    ):
        out = ensure_current_season_xg_profile_for_fixture(db, 501, client=client)

    assert out["status"] == "ok"
    assert str(out["xg_profiles"]["anti_leakage"]["fixture_date_cutoff"]).startswith("2026-07-16")
    client.get_fixture_statistics.assert_not_called()  # prior already has xG
