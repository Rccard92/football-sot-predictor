"""RESCHEDULE-01 — regressione fixture riprogrammate (stesso api_fixture_id)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_DISCOVERED,
    ELIGIBILITY_EXCLUDED_MAPPING,
    MATCH_POSTPONED,
    MATCH_UPCOMING,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXPECTED_FORMULA_FREEZE_SHA256,
    compute_v2_formula_freeze_sha256,
)
from app.services.cecchino.cecchino_today_reschedule import (
    CLASSIFICATION_RESCHEDULED,
    REASON_FINISHED,
    REASON_IDENTITY,
    REASON_NOT_RECONCILED,
    apply_old_today_rescheduled_postponed,
    assert_post_upsert_invariant,
    is_terminal_finished_status,
    provider_kickoff_moved_to_other_day,
    reconcile_canonical_fixture_from_api,
    today_row_needs_past_kickoff_id_reconciliation,
)
from app.services.cecchino.cecchino_today_service import run_scan, update_today_fixture_results

OLD_KO = "2026-07-20T18:00:00+00:00"
NEW_KO = "2026-08-26T18:00:00+00:00"
OLD_KO_B = "2026-07-20T23:00:00+00:00"
NEW_KO_B = "2026-08-26T18:30:00+00:00"

# Synthetic IDs ispirati ai casi reali (non production Today 25081/25116)
API_ID_A = 1498649
API_ID_B = 1498663

FREEZE_SHA = "3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe"


def _api_item(
    fid: int = API_ID_A,
    *,
    kickoff: str = NEW_KO,
    short: str = "NS",
    home_id: int = 10,
    away_id: int = 20,
    league_id: int = 135,
    season: int = 2025,
    goals_home: int | None = None,
    goals_away: int | None = None,
) -> dict:
    return {
        "fixture": {"id": fid, "date": kickoff, "status": {"short": short}},
        "league": {
            "id": league_id,
            "season": season,
            "name": "Serie A",
            "country": "Italy",
            "type": "League",
        },
        "teams": {
            "home": {"id": home_id, "name": "Home FC", "logo": ""},
            "away": {"id": away_id, "name": "Away FC", "logo": ""},
        },
        "goals": {"home": goals_home, "away": goals_away},
    }


def _local_fixture(
    *,
    api_id: int = API_ID_A,
    kickoff: str = OLD_KO,
    status: str = "NS",
    home_api: int = 10,
    away_api: int = 20,
    league_api: int = 135,
    season_year: int = 2025,
    goals_home: int | None = None,
    goals_away: int | None = None,
) -> MagicMock:
    fx = MagicMock()
    fx.id = 15931
    fx.api_fixture_id = api_id
    fx.competition_id = 7
    fx.league_id = 1
    fx.season_id = 2
    fx.home_team_id = 100
    fx.away_team_id = 200
    fx.kickoff_at = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    fx.status = status
    fx.status_long = None
    fx.elapsed = None
    fx.goals_home = goals_home
    fx.goals_away = goals_away
    fx.raw_json = None

    home = MagicMock()
    home.api_team_id = home_api
    away = MagicMock()
    away.api_team_id = away_api
    fx.home_team = home
    fx.away_team = away

    league = MagicMock()
    league.api_league_id = league_api
    season = MagicMock()
    season.year = season_year
    fx.league = league
    fx.season = season
    return fx


def test_finished_detection_status_only_not_goals():
    assert is_terminal_finished_status("FT") is True
    assert is_terminal_finished_status("AET") is True
    assert is_terminal_finished_status("PEN") is True
    assert is_terminal_finished_status("NS") is False
    assert is_terminal_finished_status("PST") is False
    assert is_terminal_finished_status("SUSP") is False
    assert is_terminal_finished_status("INT") is False
    assert is_terminal_finished_status("TBD") is False
    # goals valorizzati NON rendono finished
    fx = _local_fixture(status="SUSP", goals_home=1, goals_away=0)
    assert is_terminal_finished_status(fx.status) is False


def test_reconcile_detects_reschedule_and_updates_kickoff():
    db = MagicMock()
    local = _local_fixture(kickoff=OLD_KO, status="NS")
    item = _api_item(kickoff=NEW_KO, short="NS")
    out = reconcile_canonical_fixture_from_api(db, local, item)
    assert out.ok is True
    assert out.rescheduled is True
    assert out.classification == CLASSIFICATION_RESCHEDULED
    assert local.kickoff_at == datetime.fromisoformat(NEW_KO)
    db.flush.assert_called()
    inv = assert_post_upsert_invariant(db, local, item)
    assert inv.ok is True


def test_reconcile_same_day_time_shift():
    db = MagicMock()
    local = _local_fixture(kickoff="2026-08-26T17:00:00+00:00", status="NS")
    item = _api_item(kickoff="2026-08-26T19:30:00+00:00", short="NS")
    out = reconcile_canonical_fixture_from_api(db, local, item)
    assert out.ok is True
    assert out.rescheduled is True
    assert local.kickoff_at.hour == 19


def test_reconcile_finished_fail_closed_no_overwrite():
    db = MagicMock()
    local = _local_fixture(kickoff=OLD_KO, status="FT", goals_home=2, goals_away=1)
    old = local.kickoff_at
    item = _api_item(kickoff=NEW_KO, short="NS")
    out = reconcile_canonical_fixture_from_api(db, local, item)
    assert out.ok is False
    assert out.reason == REASON_FINISHED
    assert local.kickoff_at == old


def test_reconcile_susp_with_partial_goals_still_reconcilable():
    """Goals parziali + SUSP non bloccano il reschedule."""
    db = MagicMock()
    local = _local_fixture(kickoff=OLD_KO, status="SUSP", goals_home=1, goals_away=0)
    item = _api_item(kickoff=NEW_KO, short="NS")
    out = reconcile_canonical_fixture_from_api(db, local, item)
    assert out.ok is True
    assert out.rescheduled is True


def test_reconcile_teams_mismatch_fail_closed():
    db = MagicMock()
    local = _local_fixture(home_api=10, away_api=20)
    item = _api_item(home_id=99, away_id=20)
    out = reconcile_canonical_fixture_from_api(db, local, item)
    assert out.ok is False
    assert out.reason == REASON_IDENTITY


def test_reconcile_competition_mismatch_fail_closed():
    db = MagicMock()
    local = _local_fixture(league_api=135, season_year=2025)
    item = _api_item(league_id=39, season=2025)
    out = reconcile_canonical_fixture_from_api(db, local, item)
    assert out.ok is False
    assert out.reason == REASON_IDENTITY


def test_invariant_fails_if_kickoff_stale():
    db = MagicMock()
    local = _local_fixture(kickoff=OLD_KO)
    item = _api_item(kickoff=NEW_KO)
    inv = assert_post_upsert_invariant(db, local, item)
    assert inv.ok is False
    assert inv.reason == REASON_NOT_RECONCILED


def test_old_today_preserved_as_postponed_metadata():
    row = MagicMock()
    row.scan_date = date(2026, 7, 20)
    row.kickoff = datetime.fromisoformat(OLD_KO)
    historical_raw = {"fixture": {"id": API_ID_A, "date": OLD_KO}, "historic": True}
    row.raw_fixture_json = historical_raw
    row.warnings_json = []
    row.match_display_status = MATCH_UPCOMING
    row.fixture_status = "NS"
    row.goals_home = None
    row.goals_away = None
    apply_old_today_rescheduled_postponed(
        row,
        provider_kickoff=datetime.fromisoformat(NEW_KO),
    )
    assert row.scan_date == date(2026, 7, 20)
    assert row.kickoff == datetime.fromisoformat(OLD_KO)
    assert row.match_display_status == MATCH_POSTPONED
    assert row.raw_fixture_json is historical_raw
    assert row.goals_home is None
    assert "fixture_rescheduled" in row.warnings_json
    assert any(str(w).startswith("rescheduled_to=") for w in row.warnings_json)


def test_provider_kickoff_midnight_boundary_rome_same_day():
    """2026-08-26T22:30Z → 2026-08-27 00:30 Europe/Rome = stesso scan_date."""
    assert (
        provider_kickoff_moved_to_other_day(
            provider_kickoff=datetime(2026, 8, 26, 22, 30, tzinfo=timezone.utc),
            scan_date=date(2026, 8, 27),
            timezone_str="Europe/Rome",
        )
        is False
    )


def test_provider_kickoff_genuine_other_local_day():
    assert (
        provider_kickoff_moved_to_other_day(
            provider_kickoff=datetime.fromisoformat(NEW_KO),
            scan_date=date(2026, 7, 20),
            timezone_str="Europe/Rome",
        )
        is True
    )


def _run_scan_with_existing_local(
    *,
    local_fx: MagicMock,
    api_item: dict,
    scan_date: date = date(2026, 8, 26),
):
    """Path reale: Fixture+Competition già presenti → bootstrap saltato."""
    comp = MagicMock()
    comp.id = 7
    db = MagicMock()
    db.is_active = True
    db.begin_nested.return_value = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.get.return_value = comp

    def scalar_side_effect(stmt=None, *args, **kwargs):
        return local_fx

    db.scalar.side_effect = scalar_side_effect

    client = MagicMock()
    client.get_fixtures_by_date.return_value = [api_item]
    client.set_usage_context = MagicMock()

    calc_kickoffs: list[datetime] = []
    build_kickoffs: list[datetime] = []

    bundle = MagicMock()
    bundle.data_quality = {"leakage_check": {"status": "ok"}}

    def _capture_build(_db, fx):
        build_kickoffs.append(fx.kickoff_at)
        return bundle

    def _capture_calc(_db, _comp, fx, persist=True):
        calc_kickoffs.append(fx.kickoff_at)
        return {
            "status": "ok",
            "final": {"home": 2.0, "draw": 3.0, "away": 4.0},
            "picchetti": {"home": 1.5},
            "warnings": [],
        }

    with (
        patch(
            "app.services.cecchino.cecchino_today_service.ZoneInfo",
            return_value=timezone.utc,
        ),
        patch("app.services.cecchino.cecchino_today_service.datetime") as mock_dt,
        patch(
            "app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition",
            return_value=(True, None),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.is_fixture_not_started",
            return_value=True,
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_1x2_gate",
            return_value=(
                {8: [{"bet_id": 1}]},
                [],
                "fixture_single_call",
                False,
            ),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.verify_complete_1x2_odds",
            return_value=(True, {"Betfair": {"1": 2.0, "X": 3.0, "2": 4.0}}, None, []),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.ensure_competition_and_history",
        ) as bootstrap,
        patch(
            "app.services.cecchino.cecchino_today_service.build_calculation_input_for_fixture",
            side_effect=_capture_build,
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.build_fixture_contexts",
            return_value=MagicMock(),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.check_cecchino_today_stats_eligible",
            return_value=(True, {"ok": True}, None),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.enrich_fixture_odds_full_canonical",
            return_value=({8: []}, [], False),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.sync_today_bookmaker_odds",
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.calculate_and_persist_for_fixture",
            side_effect=_capture_calc,
        ),
        patch(
            "app.services.cecchino.cecchino_today_service._persist_post_calc_snapshot",
            return_value=(MagicMock(), "eligible"),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.sync_signals_for_scan_date",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.get_api_usage_summary",
            return_value={"total_calls": 0, "estimated_remaining_daily_budget": 7500},
        ),
        patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.safe_upsert_balance_readiness_daily_snapshot",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.attach_scan_odds_meta",
            side_effect=lambda snap, **kw: snap or {},
        ),
    ):
        mock_dt.now.return_value = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k) if a else datetime.now(timezone.utc)
        report = run_scan(
            db,
            scan_date=scan_date,
            timezone="UTC",
            client=client,
            force_rescan=True,
        )

    return report, bootstrap, calc_kickoffs, build_kickoffs, local_fx


def test_run_scan_path_updates_stale_canonical_kickoff_real_case_a():
    """Regression: bootstrap saltato ma kickoff deve aggiornarsi (caso 1498649)."""
    local = _local_fixture(api_id=API_ID_A, kickoff=OLD_KO, status="NS")
    item = _api_item(fid=API_ID_A, kickoff=NEW_KO, short="NS")
    report, bootstrap, calc_kos, build_kos, fx = _run_scan_with_existing_local(
        local_fx=local,
        api_item=item,
    )
    bootstrap.assert_not_called()
    assert fx.kickoff_at == datetime.fromisoformat(NEW_KO)
    assert build_kos and build_kos[0] == datetime.fromisoformat(NEW_KO)
    assert calc_kos and calc_kos[0] == datetime.fromisoformat(NEW_KO)
    assert report.get("excluded", {}).get(ELIGIBILITY_EXCLUDED_MAPPING, 0) == 0


def test_run_scan_path_updates_stale_canonical_kickoff_real_case_b():
    local = _local_fixture(api_id=API_ID_B, kickoff=OLD_KO_B, status="NS")
    item = _api_item(fid=API_ID_B, kickoff=NEW_KO_B, short="NS")
    _, bootstrap, calc_kos, _, fx = _run_scan_with_existing_local(
        local_fx=local,
        api_item=item,
    )
    bootstrap.assert_not_called()
    assert fx.kickoff_at == datetime.fromisoformat(NEW_KO_B)
    assert calc_kos and calc_kos[0] == datetime.fromisoformat(NEW_KO_B)


def test_run_scan_finished_conflict_no_calc():
    local = _local_fixture(api_id=API_ID_A, kickoff=OLD_KO, status="FT")
    old = local.kickoff_at
    item = _api_item(fid=API_ID_A, kickoff=NEW_KO, short="NS")
    report, bootstrap, calc_kos, _, fx = _run_scan_with_existing_local(
        local_fx=local,
        api_item=item,
    )
    bootstrap.assert_not_called()
    assert fx.kickoff_at == old
    assert calc_kos == []
    assert report["excluded"].get(ELIGIBILITY_EXCLUDED_MAPPING, 0) >= 1


def test_run_scan_identity_mismatch_no_calc():
    local = _local_fixture(api_id=API_ID_A, home_api=10, away_api=20)
    item = _api_item(fid=API_ID_A, home_id=77, away_id=20)
    report, _, calc_kos, _, _ = _run_scan_with_existing_local(
        local_fx=local,
        api_item=item,
    )
    assert calc_kos == []
    assert report["excluded"].get(ELIGIBILITY_EXCLUDED_MAPPING, 0) >= 1


def test_run_scan_unchanged_kickoff_passthrough():
    local = _local_fixture(api_id=API_ID_A, kickoff=NEW_KO, status="NS")
    item = _api_item(fid=API_ID_A, kickoff=NEW_KO, short="NS")
    _, bootstrap, calc_kos, _, fx = _run_scan_with_existing_local(
        local_fx=local,
        api_item=item,
    )
    bootstrap.assert_not_called()
    assert fx.kickoff_at == datetime.fromisoformat(NEW_KO)
    assert calc_kos and calc_kos[0] == datetime.fromisoformat(NEW_KO)


def test_update_results_pst_postponed():
    row = MagicMock()
    row.id = 1
    row.provider_fixture_id = API_ID_A
    row.scan_date = date(2026, 7, 20)
    row.kickoff = datetime.fromisoformat(OLD_KO)
    row.match_display_status = MATCH_UPCOMING
    row.warnings_json = []
    row.raw_fixture_json = None

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    db.begin_nested.return_value = MagicMock()

    client = MagicMock()
    client.get_fixtures_by_date.return_value = [
        _api_item(fid=API_ID_A, kickoff=OLD_KO, short="PST"),
    ]

    with (
        patch(
            "app.services.cecchino.cecchino_today_service.evaluate_activations_for_fixture",
            return_value={"evaluated": 0, "pending": 0},
        ),
        patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.safe_upsert_balance_readiness_daily_snapshot",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.attach_results_for_rows",
        ),
    ):
        out = update_today_fixture_results(
            db,
            scan_date=date(2026, 7, 20),
            timezone="UTC",
            client=client,
        )

    assert row.match_display_status == MATCH_POSTPONED
    assert out["status"] == "ok"


def test_update_results_id_lookup_rescheduled_marks_postponed_preserves_kickoff():
    row = MagicMock()
    row.id = 1
    row.provider_fixture_id = API_ID_A
    row.scan_date = date(2026, 7, 20)
    historical = datetime.fromisoformat(OLD_KO)
    row.kickoff = historical
    row.match_display_status = MATCH_UPCOMING
    row.warnings_json = []
    historical_raw = {"fixture": {"id": API_ID_A, "date": OLD_KO}, "scan": "2026-07-20"}
    row.raw_fixture_json = historical_raw
    row.goals_home = None
    row.goals_away = None
    row.score_fulltime_home = None
    row.score_fulltime_away = None

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    db.begin_nested.return_value = MagicMock()

    client = MagicMock()
    # Non più nella day-query del 20/07
    client.get_fixtures_by_date.return_value = []
    client.get_fixture_by_id.return_value = _api_item(
        fid=API_ID_A,
        kickoff=NEW_KO,
        short="NS",
    )

    with (
        patch(
            "app.services.cecchino.cecchino_today_service.evaluate_activations_for_fixture",
            return_value={"evaluated": 0, "pending": 0},
        ) as eval_mock,
        patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.safe_upsert_balance_readiness_daily_snapshot",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.attach_results_for_rows",
        ) as attach_mock,
    ):
        out = update_today_fixture_results(
            db,
            scan_date=date(2026, 7, 20),
            timezone="Europe/Rome",
            client=client,
        )

    assert row.scan_date == date(2026, 7, 20)
    assert row.kickoff == historical
    assert row.match_display_status == MATCH_POSTPONED
    assert row.raw_fixture_json is historical_raw
    assert "fixture_rescheduled" in (row.warnings_json or [])
    assert out["still_upcoming"] == 0
    client.get_fixture_by_id.assert_called()
    eval_mock.assert_not_called()
    attached_rows = attach_mock.call_args[0][1]
    assert all(int(r.id) != 1 for r in attached_rows)


def test_update_results_ft_new_date_does_not_absorb_score_or_settle():
    """FT 2-1 della nuova data non deve contaminare la vecchia Today 20/07."""
    historical_raw = {
        "fixture": {"id": API_ID_A, "date": OLD_KO, "status": {"short": "NS"}},
        "goals": {"home": None, "away": None},
    }
    row = MagicMock()
    row.id = 25081
    row.provider_fixture_id = API_ID_A
    row.scan_date = date(2026, 7, 20)
    row.kickoff = datetime.fromisoformat(OLD_KO)
    row.match_display_status = MATCH_UPCOMING
    row.fixture_status = "NS"
    row.warnings_json = []
    row.raw_fixture_json = historical_raw
    row.goals_home = None
    row.goals_away = None
    row.score_fulltime_home = None
    row.score_fulltime_away = None
    row.score_halftime_home = None
    row.score_halftime_away = None

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    db.begin_nested.return_value = MagicMock()

    client = MagicMock()
    client.get_fixtures_by_date.return_value = []
    client.get_fixture_by_id.return_value = _api_item(
        fid=API_ID_A,
        kickoff=NEW_KO,
        short="FT",
        goals_home=2,
        goals_away=1,
    )

    with (
        patch(
            "app.services.cecchino.cecchino_today_service.evaluate_activations_for_fixture",
            return_value={"evaluated": 0, "pending": 0},
        ) as eval_mock,
        patch(
            "app.services.cecchino.cecchino_kpi_signals.revaluate_kpi_signals_for_fixture",
        ) as kpi_mock,
        patch(
            "app.services.cecchino.cecchino_purchasability_validation.evaluate_purchasability_validation_for_fixture",
        ) as purch_mock,
        patch(
            "app.services.cecchino.cecchino_balance_v5_empirical.settle_balance_empirical_record",
        ) as settle_mock,
        patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.safe_upsert_balance_readiness_daily_snapshot",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.attach_results_for_rows",
        ) as attach_mock,
    ):
        update_today_fixture_results(
            db,
            scan_date=date(2026, 7, 20),
            timezone="Europe/Rome",
            client=client,
        )

    assert row.scan_date == date(2026, 7, 20)
    assert row.kickoff == datetime.fromisoformat(OLD_KO)
    assert row.match_display_status == MATCH_POSTPONED
    assert row.goals_home is None
    assert row.goals_away is None
    assert row.score_fulltime_home is None
    assert row.score_fulltime_away is None
    assert row.raw_fixture_json is historical_raw
    assert "fixture_rescheduled" in (row.warnings_json or [])

    eval_mock.assert_not_called()
    kpi_mock.assert_not_called()
    purch_mock.assert_not_called()
    settle_mock.assert_not_called()
    attached_rows = attach_mock.call_args[0][1]
    assert all(int(r.id) != 25081 for r in attached_rows)
    assert attached_rows == []


def test_update_results_same_local_day_rome_not_treated_as_reschedule():
    """Kickoff UTC giorno prima ma locale Rome = scan_date → flusso normale."""
    row = MagicMock()
    row.id = 99
    row.provider_fixture_id = API_ID_A
    row.scan_date = date(2026, 8, 27)
    row.kickoff = datetime(2026, 8, 26, 22, 30, tzinfo=timezone.utc)
    row.match_display_status = MATCH_UPCOMING
    row.warnings_json = []
    row.raw_fixture_json = None
    row.goals_home = None
    row.goals_away = None
    row.score_fulltime_home = None
    row.score_fulltime_away = None
    row.score_halftime_home = None
    row.score_halftime_away = None
    row.fixture_status = "NS"
    row.elapsed_minutes = None
    row.country_flag_url = None
    row.league_logo_url = None
    row.home_team_logo_url = None
    row.away_team_logo_url = None

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    db.begin_nested.return_value = MagicMock()

    client = MagicMock()
    client.get_fixtures_by_date.return_value = [
        _api_item(
            fid=API_ID_A,
            kickoff="2026-08-26T22:30:00+00:00",
            short="NS",
        ),
    ]

    with (
        patch(
            "app.services.cecchino.cecchino_today_service.evaluate_activations_for_fixture",
            return_value={"evaluated": 0, "pending": 0},
        ) as eval_mock,
        patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.safe_upsert_balance_readiness_daily_snapshot",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.attach_results_for_rows",
        ) as attach_mock,
    ):
        update_today_fixture_results(
            db,
            scan_date=date(2026, 8, 27),
            timezone="Europe/Rome",
            client=client,
        )

    assert row.match_display_status != MATCH_POSTPONED or "fixture_rescheduled" not in (
        row.warnings_json or []
    )
    # Stesso giorno locale: apply_display eseguito, non reschedule skip
    eval_mock.assert_called_once()
    attached_rows = attach_mock.call_args[0][1]
    assert any(int(r.id) == 99 for r in attached_rows)


def test_update_results_provider_fail_no_invention():
    row = MagicMock()
    row.id = 1
    row.provider_fixture_id = API_ID_A
    row.scan_date = date(2026, 7, 20)
    row.kickoff = datetime.fromisoformat(OLD_KO)
    row.match_display_status = MATCH_UPCOMING
    row.warnings_json = []

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    db.begin_nested.return_value = MagicMock()

    from app.services.api_football_client import ApiFootballError

    client = MagicMock()
    client.get_fixtures_by_date.return_value = []
    client.get_fixture_by_id.side_effect = ApiFootballError("timeout")

    with (
        patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.safe_upsert_balance_readiness_daily_snapshot",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.attach_results_for_rows",
        ),
    ):
        out = update_today_fixture_results(
            db,
            scan_date=date(2026, 7, 20),
            timezone="UTC",
            client=client,
        )

    assert row.match_display_status == MATCH_UPCOMING
    assert out["failed"]


def test_new_today_row_unique_key_allows_same_provider_id():
    """Documenta unique key scan_date+provider+id: due giorni = due row."""
    from app.models.cecchino_today_fixture import CecchinoTodayFixture

    constraint = CecchinoTodayFixture.__table_args__[0]
    cols = list(constraint.columns)
    assert [c.name for c in cols] == ["scan_date", "provider_source", "provider_fixture_id"]


def test_v36_freeze_sha_unchanged():
    assert compute_v2_formula_freeze_sha256() == EXPECTED_FORMULA_FREEZE_SHA256
    assert EXPECTED_FORMULA_FREEZE_SHA256 == FREEZE_SHA


def test_past_kickoff_needs_reconciliation_helper():
    row = MagicMock()
    row.match_display_status = MATCH_UPCOMING
    row.kickoff = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    assert today_row_needs_past_kickoff_id_reconciliation(row, now=now) is True
    row.match_display_status = MATCH_POSTPONED
    assert today_row_needs_past_kickoff_id_reconciliation(row, now=now) is False
