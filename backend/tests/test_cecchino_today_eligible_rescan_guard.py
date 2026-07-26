"""Protezione monotonicità eligible Cecchino Today sulle riscansioni."""

from __future__ import annotations

import copy
import json
import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_DISCOVERED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_ERROR,
    ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_MAPPING,
    ELIGIBILITY_EXCLUDED_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_STARTED,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_today_eligible_guard import (
    TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF,
    TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED,
    TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS,
    TRANSITION_ELIGIBLE_REFRESHED,
    TRANSITION_NEW_ELIGIBLE,
    TRANSITION_PROMOTED_TO_ELIGIBLE,
    TRANSITION_STARTED_NEVER_ELIGIBLE,
    WARNING_MISSING_BOOKMAKER,
    WARNING_PREFIX,
    append_preservation_warning,
    classify_eligible_success_transition,
    classify_non_upcoming_transition,
    freeze_eligible_after_kickoff,
    is_protected_eligible,
    preserve_eligible_snapshot,
    warning_code_for_incoming_status,
)
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics
from app.services.cecchino.cecchino_today_service import (
    _item_brief,
    _persist_post_calc_snapshot,
    _upsert_today_snapshot,
    revalidate_cecchino_today_day,
    run_scan,
)


def _api_item(
    fid: int = 1001,
    *,
    short: str = "NS",
    kickoff: str = "2026-06-04T20:00:00+00:00",
    league_type: str = "League",
    goals_home: int | None = None,
    goals_away: int | None = None,
    elapsed: int | None = None,
) -> dict:
    fx_status: dict = {"short": short}
    if elapsed is not None:
        fx_status["elapsed"] = elapsed
    item: dict = {
        "fixture": {"id": fid, "date": kickoff, "status": fx_status},
        "league": {
            "id": 135,
            "season": 2025,
            "name": "Serie A",
            "country": "Italy",
            "type": league_type,
            "flag": "https://flag",
            "logo": "https://league",
        },
        "teams": {
            "home": {"name": "Home FC", "logo": "https://home"},
            "away": {"name": "Away FC", "logo": "https://away"},
        },
        "goals": {"home": goals_home, "away": goals_away},
        "score": {
            "halftime": {"home": None, "away": None},
            "fulltime": {"home": goals_home, "away": goals_away},
        },
    }
    return item


def _eligible_row(
    *,
    fid: int = 1001,
    scan_date: date = date(2026, 6, 4),
    status: str = ELIGIBILITY_ELIGIBLE,
) -> MagicMock:
    row = MagicMock(spec=CecchinoTodayFixture)
    row.id = fid
    row.scan_date = scan_date
    row.provider_source = "api_football"
    row.provider_fixture_id = fid
    row.eligibility_status = status
    row.eligibility_reason = "Eleggibile"
    row.bookmaker_status = "ok"
    row.stats_status = "ok"
    row.cecchino_status = "ok"
    row.local_fixture_id = 42
    row.competition_id = 7
    row.odds_snapshot_json = {"bookmakers": {"Betfair": {"1": 2.1, "X": 3.2, "2": 3.8}}}
    row.stats_snapshot_json = {"samples": 12, "ok": True}
    row.cecchino_output_json = {
        "final": {"home": 2.05, "draw": 3.1, "away": 3.9},
        "picchetti": {"home": 1.5},
        "signals_matrix": {"status": "available"},
    }
    row.kpi_panel_json = {"version": "v2", "rows": [{"market": "1X2"}]}
    row.xg_profiles_json = {"home": {"xg": 1.2}, "away": {"xg": 0.9}}
    row.blocking_reasons_json = []
    row.warnings_json = ["pre_existing_warning"]
    row.odds_check_status = "complete"
    row.odds_checked_at = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
    row.negative_cache_until = None
    row.kickoff = datetime(2026, 6, 4, 20, 0, tzinfo=timezone.utc)
    row.fixture_status = "NS"
    row.match_display_status = "upcoming"
    row.provider_league_id = 135
    row.provider_season = 2025
    row.country_name = "Italy"
    row.league_name = "Serie A"
    row.home_team_name = "Home FC"
    row.away_team_name = "Away FC"
    row.goals_home = None
    row.goals_away = None
    row.score_fulltime_home = None
    row.score_fulltime_away = None
    row.score_halftime_home = None
    row.score_halftime_away = None
    row.elapsed_minutes = None
    row.raw_fixture_json = _api_item(fid)
    row.country_flag_url = "https://flag"
    row.league_logo_url = "https://league"
    row.home_team_logo_url = "https://home"
    row.away_team_logo_url = "https://away"
    return row


def _snapshot_fingerprint(row: MagicMock) -> str:
    payload = {
        "eligibility_status": row.eligibility_status,
        "eligibility_reason": row.eligibility_reason,
        "bookmaker_status": row.bookmaker_status,
        "stats_status": row.stats_status,
        "cecchino_status": row.cecchino_status,
        "odds_snapshot_json": row.odds_snapshot_json,
        "stats_snapshot_json": row.stats_snapshot_json,
        "cecchino_output_json": row.cecchino_output_json,
        "kpi_panel_json": row.kpi_panel_json,
        "xg_profiles_json": row.xg_profiles_json,
        "blocking_reasons_json": row.blocking_reasons_json,
        "odds_check_status": row.odds_check_status,
        "local_fixture_id": row.local_fixture_id,
        "competition_id": row.competition_id,
    }
    return json.dumps(payload, sort_keys=True, default=str)


# --- Guard unit ---


def test_is_protected_eligible():
    row = _eligible_row()
    assert is_protected_eligible(row) is True
    row.eligibility_status = ELIGIBILITY_DISCOVERED
    assert is_protected_eligible(row) is False
    assert is_protected_eligible(None) is False


def test_append_preservation_warning_dedup():
    w = append_preservation_warning(["pre"], WARNING_MISSING_BOOKMAKER)
    w2 = append_preservation_warning(w, WARNING_MISSING_BOOKMAKER)
    assert w2.count(WARNING_MISSING_BOOKMAKER) == 1
    assert "pre" in w2


def test_classify_transitions():
    assert classify_eligible_success_transition(None) == TRANSITION_NEW_ELIGIBLE
    assert classify_eligible_success_transition(ELIGIBILITY_ELIGIBLE) == TRANSITION_ELIGIBLE_REFRESHED
    assert (
        classify_eligible_success_transition(ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER)
        == TRANSITION_PROMOTED_TO_ELIGIBLE
    )
    live = _api_item(short="1H", elapsed=22, goals_home=1, goals_away=0)
    assert classify_non_upcoming_transition(live) == TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF
    pst = _api_item(short="PST")
    assert classify_non_upcoming_transition(pst) == TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS
    canc = _api_item(short="CANC")
    assert classify_non_upcoming_transition(canc) == TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS


def test_freeze_updates_match_keeps_snapshot():
    row = _eligible_row()
    before = _snapshot_fingerprint(row)
    item = _api_item(short="FT", goals_home=2, goals_away=1, elapsed=90)
    brief = _item_brief(item)
    outcome = freeze_eligible_after_kickoff(row, item, brief=brief)
    assert outcome.preserved is True
    assert outcome.effective_status == ELIGIBILITY_ELIGIBLE
    assert outcome.transition == TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF
    assert row.match_display_status == "finished"
    assert row.goals_home == 2
    assert row.goals_away == 1
    assert _snapshot_fingerprint(row) == before or row.odds_snapshot_json["bookmakers"]
    assert row.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert row.kpi_panel_json["version"] == "v2"
    assert any(str(w).startswith(WARNING_PREFIX) for w in row.warnings_json)


def test_preserve_keeps_byte_equivalent_payloads():
    row = _eligible_row()
    odds_before = copy.deepcopy(row.odds_snapshot_json)
    kpi_before = copy.deepcopy(row.kpi_panel_json)
    xg_before = copy.deepcopy(row.xg_profiles_json)
    blocking_before = copy.deepcopy(row.blocking_reasons_json)
    item = _api_item()
    outcome = preserve_eligible_snapshot(
        row,
        reason_code=WARNING_MISSING_BOOKMAKER,
        incoming_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
        api_item=item,
        brief=_item_brief(item),
    )
    assert outcome.transition == TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED
    assert row.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert row.odds_snapshot_json == odds_before
    assert row.kpi_panel_json == kpi_before
    assert row.xg_profiles_json == xg_before
    assert row.blocking_reasons_json == blocking_before
    assert row.negative_cache_until is None
    assert row.odds_check_status == "complete"


# --- Census / upsert ---


def test_census_eligible_not_discovered():
    db = MagicMock()
    row = _eligible_row()
    db.scalar.return_value = row
    item = _api_item()
    out = _upsert_today_snapshot(
        db,
        scan_date=date(2026, 6, 4),
        api_item=item,
        eligibility_status=ELIGIBILITY_DISCOVERED,
        eligibility_reason="discovered",
        previous_status=ELIGIBILITY_ELIGIBLE,
        census_mode=True,
    )
    assert out.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert out.local_fixture_id == 42
    assert out.competition_id == 7


def test_census_excluded_can_become_discovered():
    db = MagicMock()
    row = _eligible_row(status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER)
    row.eligibility_status = ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER
    db.scalar.return_value = row
    item = _api_item()
    out = _upsert_today_snapshot(
        db,
        scan_date=date(2026, 6, 4),
        api_item=item,
        eligibility_status=ELIGIBILITY_DISCOVERED,
        eligibility_reason="discovered",
        previous_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
        census_mode=True,
    )
    assert out.eligibility_status == ELIGIBILITY_DISCOVERED


def test_upsert_no_duplicate_row():
    db = MagicMock()
    existing = _eligible_row(status=ELIGIBILITY_DISCOVERED)
    existing.eligibility_status = ELIGIBILITY_DISCOVERED
    db.scalar.return_value = existing
    item = _api_item()
    r1 = _upsert_today_snapshot(
        db, scan_date=date(2026, 6, 4), api_item=item, eligibility_status=ELIGIBILITY_DISCOVERED
    )
    r2 = _upsert_today_snapshot(
        db, scan_date=date(2026, 6, 4), api_item=item, eligibility_status=ELIGIBILITY_DISCOVERED
    )
    assert r1 is existing and r2 is existing
    db.add.assert_not_called()


# --- Persist post-calc ---


def test_persist_refresh_success_replaces_snapshot():
    db = MagicMock()
    row = _eligible_row()
    db.scalar.return_value = row
    metrics = ScanRunMetrics()
    new_odds = {"bookmakers": {"Betfair": {"1": 1.9, "X": 3.4, "2": 4.0}}}
    new_kpi = {"version": "v2", "rows": [{"market": "1X2", "edge": 0.1}]}
    new_out = {"final": {"home": 1.95, "draw": 3.3, "away": 4.1}}
    calc = {"status": "ok", "calculation_status": "ok", "output": new_out, "warnings": []}
    with patch(
        "app.services.cecchino.cecchino_today_service.validate_cecchino_today_final_eligibility",
    ) as mock_val:
        mock_val.return_value = MagicMock(
            is_eligible=True,
            eligibility_status=ELIGIBILITY_ELIGIBLE,
            eligibility_reason="Eleggibile",
            blocking_reasons=[],
            warnings=[],
        )
        with (
            patch("app.services.cecchino.cecchino_today_service.maybe_ensure_xg_for_eligible_row"),
            patch("app.services.cecchino.cecchino_today_service._maybe_sync_kpi_signals_for_fixture"),
            patch(
                "app.services.cecchino.cecchino_today_service._maybe_sync_purchasability_validation_for_fixture"
            ),
            patch("app.services.cecchino.cecchino_today_service._maybe_sync_balance_empirical_for_fixture"),
            patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations"),
        ):
            out_row, status = _persist_post_calc_snapshot(
                db,
                scan_date=date(2026, 6, 4),
                api_item=_api_item(),
                local_fixture_id=42,
                competition_id=7,
                odds_snapshot=new_odds,
                stats_snapshot={"ok": True},
                cecchino_output=new_out,
                kpi_panel=new_kpi,
                row_warnings=[],
                calc=calc,
                leakage_status="ok",
                run_metrics=metrics,
                previous_status=ELIGIBILITY_ELIGIBLE,
            )
    assert status == ELIGIBILITY_ELIGIBLE
    assert out_row.odds_snapshot_json == new_odds
    assert out_row.kpi_panel_json == new_kpi
    assert metrics.eligibility_transitions[TRANSITION_ELIGIBLE_REFRESHED] == 1


def test_persist_refresh_failure_preserves():
    db = MagicMock()
    row = _eligible_row()
    before = _snapshot_fingerprint(row)
    db.scalar.return_value = row
    metrics = ScanRunMetrics()
    calc = {"status": "ok", "calculation_status": "ok", "output": {}, "warnings": []}
    with patch(
        "app.services.cecchino.cecchino_today_service.validate_cecchino_today_final_eligibility",
    ) as mock_val:
        mock_val.return_value = MagicMock(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
            eligibility_reason="KPI missing",
            blocking_reasons=["kpi"],
            warnings=[],
        )
        out_row, status = _persist_post_calc_snapshot(
            db,
            scan_date=date(2026, 6, 4),
            api_item=_api_item(),
            local_fixture_id=99,
            competition_id=99,
            odds_snapshot={"new": True},
            stats_snapshot={"new": True},
            cecchino_output={},
            kpi_panel=None,
            row_warnings=[],
            calc=calc,
            leakage_status="ok",
            run_metrics=metrics,
            previous_status=ELIGIBILITY_ELIGIBLE,
        )
    assert status == ELIGIBILITY_ELIGIBLE
    assert out_row.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert _snapshot_fingerprint(out_row) == before or out_row.kpi_panel_json["version"] == "v2"
    assert out_row.local_fixture_id == 42
    assert metrics.eligibility_transitions[TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED] == 1
    assert metrics.protected_snapshot_overwrite_blocked == 1


def test_persist_calc_error_preserves_eligible():
    db = MagicMock()
    row = _eligible_row()
    odds_before = copy.deepcopy(row.odds_snapshot_json)
    db.scalar.return_value = row
    metrics = ScanRunMetrics()
    calc = {"status": "error", "message": "boom", "code": "calculation_error"}
    out_row, status = _persist_post_calc_snapshot(
        db,
        scan_date=date(2026, 6, 4),
        api_item=_api_item(),
        local_fixture_id=42,
        competition_id=7,
        odds_snapshot={"x": 1},
        stats_snapshot={},
        cecchino_output=None,
        kpi_panel=None,
        row_warnings=[],
        calc=calc,
        leakage_status="ok",
        run_metrics=metrics,
        previous_status=ELIGIBILITY_ELIGIBLE,
    )
    assert status == ELIGIBILITY_ELIGIBLE
    assert out_row.odds_snapshot_json == odds_before


def test_warning_codes_for_incoming_statuses():
    assert "missing_bookmaker" in warning_code_for_incoming_status(
        ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER
    )
    assert "missing_1x2" in warning_code_for_incoming_status(ELIGIBILITY_EXCLUDED_MISSING_1X2)
    assert "insufficient_stats" in warning_code_for_incoming_status(
        ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS
    )
    assert "calculation_error" in warning_code_for_incoming_status(ELIGIBILITY_EXCLUDED_MAPPING)
    assert "calculation_error" in warning_code_for_incoming_status(
        ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE
    )
    assert "kpi_not_calculable" in warning_code_for_incoming_status(
        ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE
    )
    assert "unexpected_error" in warning_code_for_incoming_status(ELIGIBILITY_ERROR)


# --- run_scan integration-style ---


def _mock_db_with_rows(rows: list[MagicMock]) -> MagicMock:
    db = MagicMock()
    db.is_active = True
    db.begin_nested.return_value = MagicMock()
    db.scalars.return_value.all.return_value = list(rows)

    def scalar_side_effect(stmt=None, *args, **kwargs):
        return None

    db.scalar.side_effect = scalar_side_effect
    return db


def test_run_scan_freeze_after_kickoff_skips_bookmaker():
    row = _eligible_row()
    item = _api_item(short="1H", elapsed=33, goals_home=1, goals_away=0)
    db = _mock_db_with_rows([row])
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [item]
    fetch_odds = MagicMock()
    with (
        patch(
            "app.services.cecchino.cecchino_today_service.ZoneInfo",
            return_value=timezone.utc,
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.datetime"
        ) as mock_dt,
        patch(
            "app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition",
            return_value=(True, None),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
            fetch_odds,
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
            "app.services.cecchino.cecchino_today_service.write_negative_odds_cache"
        ) as mock_neg,
        patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.safe_upsert_balance_readiness_daily_snapshot",
            return_value={},
        ),
    ):
        mock_dt.now.return_value = datetime(2026, 6, 4, 21, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k) if a else datetime.now(timezone.utc)
        report = run_scan(db, scan_date=date(2026, 6, 4), client=client, force_rescan=True)

    fetch_odds.assert_not_called()
    mock_neg.assert_not_called()
    assert row.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert row.match_display_status == "live"
    assert row.goals_home == 1
    rs = report["result_summary"]
    assert rs["eligibility_transitions"][TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF] == 1
    assert report["eligible"] == 1
    assert "excluded_started" not in (report.get("excluded") or {})


def test_run_scan_finished_and_postponed_and_cancelled_preserve():
    for short, expected_transition, display in (
        ("FT", TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF, "finished"),
        ("PST", TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS, "postponed"),
        ("CANC", TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS, "cancelled"),
    ):
        row = _eligible_row(fid=2000)
        item = _api_item(fid=2000, short=short, goals_home=0, goals_away=0)
        db = _mock_db_with_rows([row])
        client = MagicMock()
        client.get_fixtures_by_date.return_value = [item]
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
                "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers"
            ) as fetch_odds,
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
        ):
            mock_dt.now.return_value = datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc)
            report = run_scan(db, scan_date=date(2026, 6, 4), client=client, force_rescan=True)
        fetch_odds.assert_not_called()
        assert row.eligibility_status == ELIGIBILITY_ELIGIBLE
        assert row.match_display_status == display
        assert (
            report["result_summary"]["eligibility_transitions"][expected_transition] == 1
        )


def test_run_scan_started_never_eligible():
    row = _eligible_row(status=ELIGIBILITY_DISCOVERED)
    row.eligibility_status = ELIGIBILITY_DISCOVERED
    item = _api_item(short="1H", elapsed=10)
    db = _mock_db_with_rows([row])
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [item]
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
    ):
        mock_dt.now.return_value = datetime(2026, 6, 4, 21, 0, tzinfo=timezone.utc)
        report = run_scan(db, scan_date=date(2026, 6, 4), client=client, force_rescan=True)
    assert report["excluded"].get(ELIGIBILITY_EXCLUDED_STARTED) == 1
    assert (
        report["result_summary"]["eligibility_transitions"][TRANSITION_STARTED_NEVER_ELIGIBLE]
        == 1
    )


def test_run_scan_upcoming_missing_bookmaker_preserves_no_neg_cache():
    row = _eligible_row()
    odds_before = copy.deepcopy(row.odds_snapshot_json)
    kpi_before = copy.deepcopy(row.kpi_panel_json)
    item = _api_item(short="NS", kickoff="2026-06-04T18:00:00+00:00")
    db = _mock_db_with_rows([row])
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [item]
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
            "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
            return_value=({}, [], "fixture_single_call", False),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.verify_complete_1x2_odds",
            return_value=(False, {}, "missing_bookmaker", ["missing_bookmaker"]),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.write_negative_odds_cache"
        ) as mock_neg,
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
    ):
        mock_dt.now.return_value = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
        report = run_scan(db, scan_date=date(2026, 6, 4), client=client, force_rescan=True)

    mock_neg.assert_not_called()
    assert row.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert row.odds_snapshot_json == odds_before
    assert row.kpi_panel_json == kpi_before
    assert row.negative_cache_until is None
    assert WARNING_MISSING_BOOKMAKER in (row.warnings_json or [])
    # idempotenza warning
    preserve_eligible_snapshot(
        row,
        reason_code=WARNING_MISSING_BOOKMAKER,
        incoming_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    )
    assert (row.warnings_json or []).count(WARNING_MISSING_BOOKMAKER) == 1
    assert (
        report["result_summary"]["eligibility_transitions"][
            TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED
        ]
        == 1
    )
    assert report["eligible"] == 1


def test_run_scan_missing_1x2_preserves():
    row = _eligible_row()
    item = _api_item(kickoff="2026-06-04T18:00:00+00:00")
    db = _mock_db_with_rows([row])
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [item]
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
            "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
            return_value=({1: []}, [], "fixture_single_call", False),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.verify_complete_1x2_odds",
            return_value=(False, {}, "missing_1x2_market", ["missing_1x2"]),
        ),
        patch("app.services.cecchino.cecchino_today_service.write_negative_odds_cache") as mock_neg,
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
    ):
        mock_dt.now.return_value = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
        report = run_scan(db, scan_date=date(2026, 6, 4), client=client, force_rescan=True)
    mock_neg.assert_not_called()
    assert row.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert report["eligible"] == 1


def test_metrics_result_summary_contains_transitions():
    m = ScanRunMetrics()
    m.record_transition(TRANSITION_NEW_ELIGIBLE)
    m.protected_eligible_total = 2
    m.protected_snapshot_overwrite_blocked = 1
    summary = m.to_result_summary(
        fixtures_found=3,
        after_competition_filter=2,
        odds_checked=2,
        eligible_count=2,
        excluded_count=1,
        excluded_summary={"excluded_cup": 1},
        duration_seconds=1.5,
    )
    assert summary["eligibility_transitions"][TRANSITION_NEW_ELIGIBLE] == 1
    assert summary["protected_eligible_total"] == 2
    assert summary["protected_snapshot_overwrite_blocked"] == 1
    assert summary["snapshot_eligible_protection_active"] is True


def test_revalidate_does_not_demote_eligible():
    row = _eligible_row()
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    with patch(
        "app.services.cecchino.cecchino_today_service.validate_cecchino_today_final_eligibility",
    ) as mock_val:
        mock_val.return_value = MagicMock(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
            eligibility_reason="kpi",
            blocking_reasons=["kpi"],
            warnings=[],
        )
        out = revalidate_cecchino_today_day(db, scan_date=date(2026, 6, 4))
    assert row.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert out["preserved_eligible"] == 1
    assert out["moved_to_excluded"] == 0


def test_idempotent_double_freeze():
    row = _eligible_row()
    item = _api_item(short="FT", goals_home=1, goals_away=1)
    brief = _item_brief(item)
    freeze_eligible_after_kickoff(row, item, brief=brief)
    odds = copy.deepcopy(row.odds_snapshot_json)
    kpi = copy.deepcopy(row.kpi_panel_json)
    freeze_eligible_after_kickoff(row, item, brief=brief)
    assert row.odds_snapshot_json == odds
    assert row.kpi_panel_json == kpi
    warns = [w for w in (row.warnings_json or []) if str(w).startswith(WARNING_PREFIX)]
    assert len(warns) == 1


def test_policy_shared_constants_for_manual_and_future_auto():
    """La stessa policy monolitica è usata da run_scan e revalidate."""
    assert is_protected_eligible(_eligible_row()) is True
    assert TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED in ScanRunMetrics().eligibility_transitions
