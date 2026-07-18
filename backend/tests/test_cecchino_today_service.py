"""Smoke test get_today_fixture_detail — identity read-only (Fase 2A.3)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_today_service import get_today_fixture_detail


KO = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
KO_BAD = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)


def _eligible_row(**kwargs):
    base = dict(
        id=9510,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        local_fixture_id=562,
        provider_fixture_id=1492291,
        competition_id=10,
        country_name="Brazil",
        league_name="Serie A",
        home_team_name="Botafogo",
        away_team_name="Santos",
        kickoff=KO,
        fixture_status="FT",
        match_display_status="finished",
        goals_home=2,
        goals_away=1,
        score_fulltime_home=2,
        score_fulltime_away=1,
        scan_date=date(2026, 7, 16),
        odds_snapshot_json={},
        stats_snapshot_json={},
        cecchino_output_json={
            "final": {
                "status": "available",
                "quota_1": 2.1,
                "quota_x": 3.4,
                "quota_2": 3.6,
                "prob_1": 0.42,
                "prob_x": 0.28,
                "prob_2": 0.30,
            },
            "data_quality": {
                "leakage_check": {"target_kickoff": KO.isoformat()},
            },
            "signals_matrix": {},
        },
        warnings_json=[],
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _local_fixture(**kwargs):
    base = dict(
        id=562,
        api_fixture_id=1492291,
        competition_id=10,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=KO,
        status="FT",
        status_long="Match Finished",
        goals_home=2,
        goals_away=1,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations")
@patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={})
@patch(
    "app.services.cecchino.cecchino_today_service.build_expected_goal_engine_diagnostics_for_today_row",
)
@patch(
    "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
    return_value={"status": "unavailable", "error": "bundle_missing"},
)
@patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={})
@patch("app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail", return_value={"rows": []})
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={})
def test_detail_includes_identity_and_preview_ok(
    _sum,
    _debug,
    _kpi,
    _goal,
    _v5_preview,
    mock_xg,
    _icm,
    _book,
    _signals,
):
    mock_xg.return_value = {
        "xg_profiles": {"anti_leakage": {"fixture_date_cutoff": KO.isoformat()}},
    }
    row = _eligible_row()
    local = _local_fixture()
    home = SimpleNamespace(name="Botafogo")
    away = SimpleNamespace(name="Santos")
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "CecchinoTodayFixture" in name:
            return row
        if "Fixture" in name and "Today" not in name:
            return local
        if "Team" in name:
            return home if int(pk) == 1 else away
        return None

    db.get.side_effect = _get

    detail = get_today_fixture_detail(db, 9510)
    assert detail["status"] == "ok"
    assert detail["kickoff"].startswith("2026-07-16")
    assert detail["fixture_identity_consistency"]["status"] == "consistent"
    assert detail["balance_v5_preview"]["status"] == "ok"
    assert detail["balance_v5_preview"]["version"] == "balance_v5_v1"
    assert detail["balance_v5"] is detail["balance_v5_preview"]
    assert detail["balance_v5"]["version"] == "balance_v5_v1"
    db.commit.assert_not_called()


@patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations")
@patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={})
@patch(
    "app.services.cecchino.cecchino_today_service.build_expected_goal_engine_diagnostics_for_today_row",
)
@patch(
    "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
    return_value={"status": "unavailable", "error": "bundle_missing"},
)
@patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={})
@patch("app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail", return_value={"rows": []})
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={})
def test_detail_preview_blocked_on_identity_mismatch_no_write(
    _sum,
    _debug,
    _kpi,
    _goal,
    _v5_preview,
    mock_xg,
    _icm,
    _book,
    _signals,
):
    mock_xg.return_value = {
        "xg_profiles": {"anti_leakage": {"fixture_date_cutoff": KO_BAD.isoformat()}},
    }
    row = _eligible_row(
        cecchino_output_json={
            "final": {
                "status": "available",
                "quota_1": 2.1,
                "quota_x": 3.4,
                "quota_2": 3.6,
                "prob_1": 0.42,
                "prob_x": 0.28,
                "prob_2": 0.30,
            },
            "data_quality": {
                "leakage_check": {"target_kickoff": KO_BAD.isoformat()},
            },
            "signals_matrix": {},
        },
    )
    local = _local_fixture(kickoff_at=KO_BAD, status="NS", goals_home=None, goals_away=None)
    home = SimpleNamespace(name="Botafogo")
    away = SimpleNamespace(name="Santos")
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "CecchinoTodayFixture" in name:
            return row
        if "Fixture" in name and "Today" not in name:
            return local
        if "Team" in name:
            return home if int(pk) == 1 else away
        return None

    db.get.side_effect = _get

    detail = get_today_fixture_detail(db, 9510)
    assert detail["kickoff"].startswith("2026-07-16")
    assert row.kickoff == KO
    assert detail["fixture_identity_consistency"]["status"] == "inconsistent"
    assert detail["fixture_identity_consistency"]["raw_sources"]["today"]["kickoff"].startswith("2026-07-16")
    assert detail["fixture_identity_consistency"]["raw_sources"]["local_fixture"]["kickoff"].startswith(
        "2026-07-22"
    )
    preview = detail["balance_v5_preview"]
    assert preview["status"] == "unavailable"
    assert preview["version"] == "balance_v5_v1"
    assert detail["balance_v5"] is preview
    assert "fixture_identity_mismatch" in preview["warnings"]
    db.commit.assert_not_called()
    assert "fixture_identity_minimal_fix_applied" not in (detail["warnings"] or [])
