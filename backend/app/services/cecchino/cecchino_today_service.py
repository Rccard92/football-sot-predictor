"""Orchestrazione Cecchino Today — discovery manuale giornaliera."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Competition, Fixture
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_DISCOVERED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_ERROR,
    ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_CUP,
    ELIGIBILITY_EXCLUDED_FRIENDLY,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED,
    ELIGIBILITY_EXCLUDED_MAPPING,
    ELIGIBILITY_EXCLUDED_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO,
    ELIGIBILITY_EXCLUDED_STARTED,
    ELIGIBILITY_EXCLUDED_WOMEN,
    ELIGIBILITY_EXCLUDED_YOUTH,
    ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_UPCOMING,
    PROVIDER_API_FOOTBALL,
)
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.api_usage_context import ApiUsageContext, BudgetGuardStop
from app.services.api_usage_service import (
    build_api_usage_debug_for_fixture,
    check_api_budget_during_scan,
    count_job_api_calls,
    get_api_usage_summary,
)
from app.services.bookmakers.fixture_bookmaker_odds_repository import upsert_selection_odds
from app.services.cecchino.cecchino_bookmaker_odds_detail import build_bookmaker_odds_detail
from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_sync_service import SLEEP_BETWEEN_CALLS_S
from app.services.cecchino.cecchino_betfair_odds_payload import (
    build_betfair_payload_from_raw,
    build_betfair_payload_from_snapshot,
)
from app.services.cecchino.cecchino_bookmaker_odds_service import load_betfair_odds_payload
from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOKMAKER,
    CECCHINO_TODAY_BOOKMAKERS,
    KEY_AWAY_CONTEXT,
    KEY_AWAY_TOTAL,
    KEY_HOME_CONTEXT,
    KEY_HOME_TOTAL,
    PROVIDER_API_FOOTBALL as BM_PROVIDER,
    STATUS_AVAILABLE,
)
from app.services.cecchino.cecchino_balance_analysis import build_balance_analysis_from_final
from app.services.cecchino.cecchino_balance_v5 import build_cecchino_balance_v5
from app.services.cecchino.cecchino_balance_v5_detail import (
    MODE_HISTORICAL,
    apply_market_deviation_book_gate,
    build_balance_identity_for_detail,
    classify_book_snapshot_status,
    evaluate_balance_v5_snapshot_meta,
    identity_for_balance_build,
    prepare_kpi_for_historical_balance,
    resolve_balance_detail_mode,
    _kpi_has_book_odds,
)
from app.services.cecchino.cecchino_current_season_xg import maybe_ensure_xg_for_eligible_row
from app.models.team import Team
from app.services.datetime_utils import (
    build_datetime_debug,
    classify_datetime_blocking_reason,
    ensure_datetime_utc,
    is_datetime_error_message,
    safe_isoformat,
    utc_now,
)
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    build_goal_intensity_for_today_row,
)
from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
    build_expected_goal_engine_diagnostics_for_today_row,
)
from app.services.cecchino.cecchino_icm_analysis import build_cecchino_icm_analysis
from app.services.cecchino.cecchino_signal_goal_refs import (
    rebuild_signals_matrix_for_output,
    sample_home_away_split_from_stats,
)
from app.services.cecchino.cecchino_signal_evaluation import evaluate_activations_for_fixture
from app.services.cecchino.cecchino_signal_backfill import sync_signals_for_scan_date
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_picchetti_debug import (
    build_cecchino_picchetti_debug,
    build_picchetti_debug_summary,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import (
    KPI_V2_VERSION,
    build_cecchino_kpi_panel_v2_betfair,
    normalize_kpi_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_snapshot import (
    attach_purchasability_preview_to_output,
    resolve_purchasability_preview_for_detail,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    attach_balance_v5_monitoring_to_output,
)
from app.services.cecchino.cecchino_fixture_history import (
    build_fixture_contexts,
    build_goal_market_contexts,
)
from app.services.cecchino.cecchino_goal_formulas import build_goal_market_cecchino_odds
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, MARKET_1X2_FH, MARKET_DC, MARKET_OU, MARKET_OU_FH
from app.services.cecchino.cecchino_service import (
    build_calculation_input_for_fixture,
    calculate_and_persist_for_fixture,
)
from app.services.cecchino.cecchino_today_bookmaker_gate import verify_complete_1x2_odds
from app.services.cecchino.cecchino_today_bootstrap import ensure_competition_and_history
from app.services.cecchino.cecchino_today_competition_filter import is_cecchino_allowed_competition
from app.services.cecchino.cecchino_today_constants import (
    CECCHINO_TODAY_VERSION,
    CECCHINO_CLEANUP_CONFIRM_TOKEN,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_TODAY_TIMEZONE,
    CECCHINO_TODAY_TIMELINE_WINDOW_DAYS,
)
from app.services.cecchino.cecchino_today_display import (
    apply_display_from_api,
    extract_display_assets,
    map_fixture_display_status,
    recommended_prediction_placeholder,
    row_score_payload,
    status_label_for_row,
)
from app.services.cecchino.cecchino_today_fixture_filter import (
    fixture_belongs_to_scan_date,
    is_fixture_not_started,
)
from app.services.cecchino.league_ingest_helpers import recover_session_if_inactive
from app.services.cecchino.cecchino_today_final_eligibility import (
    build_cecchino_debug,
    build_kpi_debug,
    partition_scan_warnings,
    validate_cecchino_today_final_eligibility,
)
from app.services.cecchino.cecchino_today_stats_gate import check_cecchino_today_stats_eligible
from app.services.cecchino.cecchino_today_odds_fetch import (
    fetch_fixture_odds_for_cecchino_bookmakers,
    write_negative_odds_cache,
)
from app.services.cecchino.cecchino_today_odds_meta import attach_scan_odds_meta, read_odds_meta
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics

logger = logging.getLogger(__name__)

ProgressReporter = Callable[..., None]
SCAN_BATCH_SIZE = 10

_BOOK_REASON_TO_STATUS = {
    "missing_bookmaker": ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    "missing_1x2_market": ELIGIBILITY_EXCLUDED_MISSING_1X2,
}

_COMPETITION_EXCLUDED_STATUSES = frozenset(
    {
        ELIGIBILITY_EXCLUDED_WOMEN,
        ELIGIBILITY_EXCLUDED_CUP,
        ELIGIBILITY_EXCLUDED_FRIENDLY,
        ELIGIBILITY_EXCLUDED_YOUTH,
    },
)

_BOOKMAKER_NAMES = ("Betfair",)


def _mapping_blocking_reasons(exc: Exception) -> list[str]:
    from sqlalchemy.exc import IntegrityError

    reasons = ["league_upsert_error"]
    if isinstance(exc, IntegrityError):
        reasons.append("integrity_error")
    msg = str(exc).lower()
    if "uq_leagues_api_league_id" in msg or "api_league_id" in msg:
        reasons.append("duplicate_league_api_id")
    if "uq_seasons_league_year" in msg:
        reasons.append("duplicate_season")
    if "uq_competitions_key" in msg:
        reasons.append("duplicate_competition_key")
    if "uq_teams_api_team_id" in msg:
        reasons.append("duplicate_team")
    return reasons


def _merge_stats_import_info(
    stats_snapshot: dict[str, Any] | None,
    import_info: list[str],
) -> dict[str, Any] | None:
    if not import_info and not stats_snapshot:
        return stats_snapshot
    merged = dict(stats_snapshot or {})
    existing = list(merged.get("import_info") or [])
    for item in import_info:
        if item not in existing:
            existing.append(item)
    if existing:
        merged["import_info"] = existing
    return merged


def _extract_leakage_status(stats_snapshot: dict[str, Any] | None) -> str:
    if not stats_snapshot:
        return "undefined"
    return str(stats_snapshot.get("leakage_status") or "undefined")


def _persist_post_calc_snapshot(
    db: Session,
    *,
    scan_date: date,
    api_item: dict[str, Any],
    local_fixture_id: int,
    competition_id: int,
    odds_snapshot: dict[str, Any],
    stats_snapshot: dict[str, Any],
    cecchino_output: dict[str, Any] | None,
    kpi_panel: dict[str, Any] | None,
    row_warnings: list[str],
    calc: dict[str, Any],
    leakage_status: str,
) -> tuple[CecchinoTodayFixture, str]:
    cec_status = str(calc.get("calculation_status") or calc.get("status") or "")
    all_warnings = row_warnings + list(calc.get("warnings") or [])
    import_info, _, _ = partition_scan_warnings(all_warnings)
    stats_with_import = _merge_stats_import_info(stats_snapshot, import_info)

    if calc.get("status") != "ok":
        eligibility_status = ELIGIBILITY_ERROR
        raw_reason = str(calc.get("message") or calc.get("code") or "calculation_error")[:500]
        if is_datetime_error_message(raw_reason):
            blocking_code = classify_datetime_blocking_reason(raw_reason)
            eligibility_reason = raw_reason
            blocking_reasons = [blocking_code]
        else:
            eligibility_reason = raw_reason
            blocking_reasons = [str(calc.get("code") or "calculation_error")]
        stored_warnings: list[str] = []
    else:
        eligibility = validate_cecchino_today_final_eligibility(
            odds_snapshot=odds_snapshot,
            stats_snapshot=stats_with_import,
            cecchino_output=cecchino_output,
            kpi_panel=kpi_panel,
            warnings=all_warnings,
            leakage_status=leakage_status,
            calc_status=cec_status,
        )
        if eligibility.is_eligible:
            eligibility_status = ELIGIBILITY_ELIGIBLE
            eligibility_reason = eligibility.eligibility_reason
            blocking_reasons = []
            stored_warnings = eligibility.warnings
        else:
            eligibility_status = eligibility.eligibility_status
            eligibility_reason = eligibility.eligibility_reason
            blocking_reasons = eligibility.blocking_reasons
            stored_warnings = eligibility.warnings

    row = _upsert_today_snapshot(
        db,
        scan_date=scan_date,
        api_item=api_item,
        eligibility_status=eligibility_status,
        eligibility_reason=eligibility_reason,
        local_fixture_id=local_fixture_id,
        competition_id=competition_id,
        bookmaker_status="ok",
        stats_status="ok" if eligibility_status == ELIGIBILITY_ELIGIBLE else "insufficient",
        cecchino_status=cec_status,
        odds_snapshot=odds_snapshot,
        stats_snapshot=stats_with_import,
        cecchino_output=cecchino_output,
        kpi_panel=kpi_panel,
        warnings=stored_warnings,
        blocking_reasons=blocking_reasons,
    )
    if eligibility_status == ELIGIBILITY_ELIGIBLE:
        maybe_ensure_xg_for_eligible_row(db, row)
        _maybe_sync_kpi_signals_for_fixture(db, int(row.id))
        _maybe_sync_purchasability_validation_for_fixture(db, int(row.id))
        _maybe_sync_balance_empirical_for_fixture(db, int(row.id))
    return row, eligibility_status


def _maybe_sync_kpi_signals_for_fixture(db: Session, today_fixture_id: int) -> None:
    try:
        from app.services.cecchino.cecchino_kpi_signals import sync_kpi_signals_for_fixture

        sync_kpi_signals_for_fixture(db, today_fixture_id)
    except Exception:
        logger.exception("KPI signals sync skipped fixture_id=%s", today_fixture_id)


def _maybe_sync_purchasability_validation_for_fixture(
    db: Session, today_fixture_id: int
) -> None:
    """Sync coorte validazione Acquistabilità — non bloccante."""
    try:
        from app.services.cecchino.cecchino_purchasability_validation import (
            sync_purchasability_validation_for_fixture,
        )

        with db.begin_nested():
            sync_purchasability_validation_for_fixture(db, int(today_fixture_id))
    except Exception:
        logger.exception(
            "purchasability validation sync skipped fixture_id=%s", today_fixture_id
        )


def _maybe_sync_balance_empirical_for_fixture(
    db: Session, today_fixture_id: int
) -> None:
    """Upsert dataset empirico Balance — non bloccante."""
    try:
        from app.services.cecchino.cecchino_balance_v5_empirical import (
            upsert_balance_empirical_for_fixture_id,
        )

        with db.begin_nested():
            upsert_balance_empirical_for_fixture_id(
                db, int(today_fixture_id), commit=False
            )
    except Exception:
        logger.exception(
            "balance empirical upsert skipped fixture_id=%s", today_fixture_id
        )


def rome_today(tz_name: str = DEFAULT_TODAY_TIMEZONE) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def rome_tomorrow(tz_name: str = DEFAULT_TODAY_TIMEZONE) -> date:
    return rome_today(tz_name) + timedelta(days=1)


def resolve_scan_date(scan_date: date | None, tz_name: str = DEFAULT_TODAY_TIMEZONE) -> date:
    if scan_date is not None:
        return scan_date
    return datetime.now(ZoneInfo(tz_name)).date()


def _parse_kickoff(item: dict[str, Any]) -> datetime | None:
    fx = item.get("fixture") or {}
    raw = fx.get("date")
    if not raw:
        return None
    return ensure_datetime_utc(raw, field_name="fixture.date")


def _item_brief(item: dict[str, Any]) -> dict[str, Any]:
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    fx = item.get("fixture") or {}
    return {
        "provider_fixture_id": int(fx.get("id") or 0),
        "provider_league_id": int(league.get("id") or 0),
        "provider_season": int(league.get("season") or 0),
        "country_name": str(league.get("country") or ""),
        "league_name": str(league.get("name") or ""),
        "home_team_name": str(home.get("name") or ""),
        "away_team_name": str(away.get("name") or ""),
        "kickoff": _parse_kickoff(item),
        "fixture_status": str((fx.get("status") or {}).get("short") or "NS"),
    }


def fetch_today_bookmaker_odds(
    client: ApiFootballClient,
    api_fixture_id: int,
) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
    """Fetch quote 1X2 Betfair (legacy helper)."""
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    name = str(CECCHINO_BOOKMAKER["name"])
    try:
        odds_by_book[bid] = client.get_fixture_odds(api_fixture_id, bid)
    except ApiFootballError as exc:
        warnings.append(f"fixture {api_fixture_id} {name}: {exc}")
        odds_by_book[bid] = []
    return odds_by_book, warnings


def sync_today_bookmaker_odds(
    db: Session,
    *,
    competition_id: int,
    fixture_id: int,
    api_fixture_id: int,
    odds_by_bookmaker: dict[int, list[dict[str, Any]]],
) -> int:
    """Persiste quote 1X2/DC/OU parsed in fixture_bookmaker_odds."""
    saved = 0
    now = utc_now()
    wanted = [MARKET_1X2, MARKET_1X2_FH, MARKET_DC, MARKET_OU, MARKET_OU_FH]
    for bm in CECCHINO_TODAY_BOOKMAKERS:
        bid = int(bm["provider_bookmaker_id"])
        raw = odds_by_bookmaker.get(bid) or []
        parsed, _ = parse_api_football_odds_response(raw, requested_markets=wanted)
        for pr in parsed:
            upsert_selection_odds(
                db,
                competition_id=competition_id,
                fixture_id=fixture_id,
                provider_source=BM_PROVIDER,
                provider_bookmaker_id=str(bid),
                bookmaker_name=bm["name"],
                normalized_market=pr["normalized_market"],
                selection_key=pr["selection_key"],
                selection_label=pr.get("selection_label"),
                odds_value=pr["odds_value"],
                market_label=pr.get("market_label"),
                provider_fixture_id=api_fixture_id,
                provider_market_id=pr.get("provider_market_id"),
                raw_payload_json=pr.get("raw_payload_json"),
                odds_updated_at=now,
            )
            saved += 1
    return saved


def _upsert_today_snapshot(
    db: Session,
    *,
    scan_date: date,
    api_item: dict[str, Any],
    eligibility_status: str,
    eligibility_reason: str | None = None,
    local_fixture_id: int | None = None,
    competition_id: int | None = None,
    bookmaker_status: str | None = None,
    stats_status: str | None = None,
    cecchino_status: str | None = None,
    odds_snapshot: dict[str, Any] | None = None,
    stats_snapshot: dict[str, Any] | None = None,
    cecchino_output: dict[str, Any] | None = None,
    kpi_panel: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    odds_check_status: str | None = None,
    odds_checked_at: datetime | None = None,
    negative_cache_until: datetime | None = None,
) -> CecchinoTodayFixture:
    brief = _item_brief(api_item)
    provider_fixture_id = brief["provider_fixture_id"]
    existing = db.scalar(
        select(CecchinoTodayFixture).where(
            CecchinoTodayFixture.scan_date == scan_date,
            CecchinoTodayFixture.provider_source == PROVIDER_API_FOOTBALL,
            CecchinoTodayFixture.provider_fixture_id == provider_fixture_id,
        ),
    )
    if existing is None:
        row = CecchinoTodayFixture(
            scan_date=scan_date,
            provider_source=PROVIDER_API_FOOTBALL,
            provider_fixture_id=provider_fixture_id,
        )
        db.add(row)
    else:
        row = existing

    row.local_fixture_id = local_fixture_id
    row.competition_id = competition_id
    row.provider_league_id = brief["provider_league_id"]
    row.provider_season = brief["provider_season"]
    row.country_name = brief["country_name"] or None
    row.league_name = brief["league_name"] or None
    row.home_team_name = brief["home_team_name"] or None
    row.away_team_name = brief["away_team_name"] or None
    row.kickoff = brief["kickoff"]
    row.fixture_status = brief["fixture_status"]
    row.eligibility_status = eligibility_status
    row.eligibility_reason = eligibility_reason
    row.bookmaker_status = bookmaker_status
    row.stats_status = stats_status
    row.cecchino_status = cecchino_status
    row.odds_snapshot_json = odds_snapshot
    row.stats_snapshot_json = stats_snapshot
    row.cecchino_output_json = cecchino_output
    row.kpi_panel_json = kpi_panel
    row.raw_fixture_json = api_item
    # xg_profiles_json: non azzerare su upsert — preserva cache profili xG automatici (Fase 53)
    row.warnings_json = warnings or []
    row.blocking_reasons_json = blocking_reasons or []
    if odds_check_status is not None:
        row.odds_check_status = odds_check_status
    if odds_checked_at is not None:
        row.odds_checked_at = odds_checked_at
    if negative_cache_until is not None:
        row.negative_cache_until = negative_cache_until
    apply_display_from_api(row, api_item)
    if eligibility_status == ELIGIBILITY_ELIGIBLE and row.match_display_status not in (
        MATCH_LIVE,
        MATCH_FINISHED,
    ):
        row.match_display_status = MATCH_UPCOMING
    db.flush()
    if eligibility_status == ELIGIBILITY_ELIGIBLE and isinstance(cecchino_output, dict):
        sync_cecchino_signal_activations(db, int(row.id))
    return row


def build_cecchino_today_report(
    *,
    scan_date: date,
    total: int,
    by_status: dict[str, int],
    warnings: list[str],
    errors: list[str] | None = None,
) -> dict[str, Any]:
    eligible = by_status.get(ELIGIBILITY_ELIGIBLE, 0)
    excluded = {k: v for k, v in by_status.items() if k != ELIGIBILITY_ELIGIBLE}
    top = sorted(excluded.items(), key=lambda x: x[1], reverse=True)[:5]
    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "scan_date": scan_date.isoformat(),
        "fixtures_found": total,
        "total_discovered": total,
        "eligible": eligible,
        "excluded": excluded,
        "excluded_summary": dict(excluded),
        "excluded_total": sum(excluded.values()),
        "top_exclusion_reasons": [{"status": k, "count": v} for k, v in top],
        "warnings": warnings,
        "errors": list(errors or []),
    }


def _emit_progress(
    progress: ProgressReporter | None,
    *,
    current_step: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
    progress_pct: float | None = None,
    fixtures_found: int | None = None,
    fixtures_checked: int | None = None,
    odds_checked: int | None = None,
    fixtures_censused: int | None = None,
    fixtures_after_competition_gate: int | None = None,
    fixtures_after_bookmaker_gate: int | None = None,
    fixtures_after_stats_gate: int | None = None,
    odds_cache_hits: int | None = None,
    negative_cache_hits: int | None = None,
    api_calls_total: int | None = None,
    api_calls: dict[str, int] | None = None,
    eligible_count: int | None = None,
    excluded_count: int | None = None,
    excluded_summary: dict[str, int] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    provider_items_received: int | None = None,
    provider_out_of_scan_date_skipped: int | None = None,
    fixtures_in_scan_date: int | None = None,
) -> None:
    if progress is None:
        return
    payload: dict[str, Any] = {}
    if current_step is not None:
        payload["current_step"] = current_step
    if progress_current is not None:
        payload["progress_current"] = progress_current
    if progress_total is not None:
        payload["progress_total"] = progress_total
    if progress_pct is not None:
        payload["progress_pct"] = progress_pct
    if fixtures_found is not None:
        payload["fixtures_found"] = fixtures_found
    if fixtures_checked is not None:
        payload["fixtures_checked"] = fixtures_checked
    if odds_checked is not None:
        payload["odds_checked"] = odds_checked
    if fixtures_censused is not None:
        payload["fixtures_censused"] = fixtures_censused
    if fixtures_after_competition_gate is not None:
        payload["fixtures_after_competition_gate"] = fixtures_after_competition_gate
    if fixtures_after_bookmaker_gate is not None:
        payload["fixtures_after_bookmaker_gate"] = fixtures_after_bookmaker_gate
    if fixtures_after_stats_gate is not None:
        payload["fixtures_after_stats_gate"] = fixtures_after_stats_gate
    if odds_cache_hits is not None:
        payload["odds_cache_hits"] = odds_cache_hits
    if negative_cache_hits is not None:
        payload["negative_cache_hits"] = negative_cache_hits
    if api_calls_total is not None:
        payload["api_calls_total"] = api_calls_total
    if api_calls is not None:
        payload["api_calls_json"] = dict(api_calls)
    if eligible_count is not None:
        payload["eligible_count"] = eligible_count
    if excluded_count is not None:
        payload["excluded_count"] = excluded_count
    if excluded_summary is not None:
        payload["excluded_summary_json"] = dict(excluded_summary)
    if warnings is not None:
        payload["warnings_json"] = list(warnings)
    if errors is not None:
        payload["errors_json"] = list(errors)
    if provider_items_received is not None:
        payload["provider_items_received"] = provider_items_received
    if provider_out_of_scan_date_skipped is not None:
        payload["provider_out_of_scan_date_skipped"] = provider_out_of_scan_date_skipped
    if fixtures_in_scan_date is not None:
        payload["fixtures_in_scan_date"] = fixtures_in_scan_date
    if payload:
        progress(**payload)


def run_scan(
    db: Session,
    *,
    scan_date: date | None = None,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    client: ApiFootballClient | None = None,
    force_rescan: bool = False,
    progress: ProgressReporter | None = None,
    metrics: ScanRunMetrics | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Pipeline completa discovery Cecchino Today."""
    resolved_date = resolve_scan_date(scan_date, timezone)
    now_rome = datetime.now(ZoneInfo(timezone))
    usage_ctx = ApiUsageContext(
        job_id=job_id,
        scan_date=resolved_date,
        record_events=True,
    )
    af_client = client or ApiFootballClient()
    af_client.set_usage_db(db)
    af_client.set_usage_context(usage_ctx)
    warnings: list[str] = []
    errors: list[str] = []
    by_status: dict[str, int] = defaultdict(int)
    run_metrics = metrics or ScanRunMetrics(started_at=time.time())
    if run_metrics.started_at <= 0:
        run_metrics.started_at = time.time()
    bootstrapped_leagues: set[tuple[int, int]] = set()
    budget_stopped = False
    budget_stop_status = "partial_stopped_budget"
    budget_stop_message = "Scansione interrotta per proteggere il budget API giornaliero."

    _emit_progress(progress, current_step="fetching_fixtures")

    try:
        raw_items = af_client.get_fixtures_by_date(resolved_date.isoformat(), timezone=timezone)
        run_metrics.api_calls["fixtures"] = run_metrics.api_calls.get("fixtures", 0) + 1
        run_metrics.sync_api_calls_total()
    except ApiFootballError as exc:
        err_report = {
            "status": "error",
            "version": CECCHINO_TODAY_VERSION,
            "scan_date": resolved_date.isoformat(),
            "message": str(exc),
            "total_discovered": 0,
            "eligible": 0,
            "excluded": {},
            "warnings": [str(exc)],
            "errors": [str(exc)],
        }
        _emit_progress(progress, current_step="completed", errors=[str(exc)])
        return err_report

    provider_items_received = len(raw_items)
    in_scope_items: list[dict[str, Any]] = []
    out_of_scan_date_examples: list[dict[str, Any]] = []

    for item in raw_items:
        belongs, date_debug = fixture_belongs_to_scan_date(item, resolved_date, timezone)
        if belongs:
            in_scope_items.append(item)
            continue
        if date_debug.get("reason") != "fixture_out_of_scan_date":
            continue
        if len(out_of_scan_date_examples) >= 10:
            continue
        brief = _item_brief(item)
        out_of_scan_date_examples.append(
            {
                "provider_fixture_id": brief["provider_fixture_id"],
                "home": brief["home_team_name"],
                "away": brief["away_team_name"],
                "scan_date": resolved_date.isoformat(),
                "fixture_local_date": date_debug.get("fixture_local_date"),
                "timezone": timezone,
            },
        )

    provider_out_of_scan_date_skipped = provider_items_received - len(in_scope_items)
    fixtures_in_scan_date = len(in_scope_items)
    raw_items = in_scope_items
    total = fixtures_in_scan_date
    run_metrics.fixtures_found = total
    after_filter_count = 0
    fixtures_checked = 0
    odds_checked = 0

    for item in raw_items:
        _upsert_today_snapshot(
            db,
            scan_date=resolved_date,
            api_item=item,
            eligibility_status=ELIGIBILITY_DISCOVERED,
            eligibility_reason="discovered",
        )
    run_metrics.fixtures_censused = total
    db.commit()

    _emit_progress(
        progress,
        current_step="fetching_fixtures",
        fixtures_found=total,
        fixtures_censused=total,
        progress_total=total,
        progress_current=0,
    )

    def _progress_metrics_payload() -> dict[str, Any]:
        run_metrics.sync_api_calls_total()
        excluded_count = sum(v for k, v in by_status.items() if k != ELIGIBILITY_ELIGIBLE)
        return {
            "fixtures_found": total,
            "provider_items_received": provider_items_received,
            "provider_out_of_scan_date_skipped": provider_out_of_scan_date_skipped,
            "fixtures_in_scan_date": fixtures_in_scan_date,
            "fixtures_checked": fixtures_checked,
            "fixtures_censused": run_metrics.fixtures_censused,
            "fixtures_after_competition_gate": run_metrics.fixtures_after_competition_gate,
            "fixtures_after_bookmaker_gate": run_metrics.fixtures_after_bookmaker_gate,
            "fixtures_after_stats_gate": run_metrics.fixtures_after_stats_gate,
            "odds_checked": odds_checked,
            "odds_cache_hits": run_metrics.odds_cache_hits,
            "negative_cache_hits": run_metrics.negative_cache_hits,
            "api_calls_total": run_metrics.api_calls_total,
            "eligible_count": by_status.get(ELIGIBILITY_ELIGIBLE, 0),
            "excluded_count": excluded_count,
            "excluded_summary": {k: v for k, v in by_status.items() if k != ELIGIBILITY_ELIGIBLE},
            "warnings": warnings,
            "errors": errors,
        }

    signal_sync_summary = {
        "fixtures": 0,
        "created": 0,
        "updated": 0,
        "deactivated": 0,
        "skipped": 0,
    }

    for batch_start in range(0, total, SCAN_BATCH_SIZE):
        if budget_stopped:
            break
        batch = raw_items[batch_start : batch_start + SCAN_BATCH_SIZE]
        for item in batch:
            fixtures_checked += 1
            api_fid: int | None = None
            try:
                try:
                    check_api_budget_during_scan(
                        db,
                        job_id=job_id,
                        usage_date=resolved_date,
                        job_calls=count_job_api_calls(db, job_id) if job_id else run_metrics.api_calls_total,
                    )
                except BudgetGuardStop as bg:
                    budget_stopped = True
                    budget_stop_status = bg.status
                    budget_stop_message = bg.message
                    errors.append(bg.message)
                    break

                brief = _item_brief(item)
                api_fid = brief["provider_fixture_id"]
                row_warnings: list[str] = []
                af_client.set_usage_context(usage_ctx.with_fixture(api_fid))

                _emit_progress(
                    progress,
                    current_step="filtering_competitions",
                    progress_current=fixtures_checked,
                    progress_total=total,
                    **_progress_metrics_payload(),
                )

                allowed, excl_status = is_cecchino_allowed_competition(item)
                if not allowed:
                    _upsert_today_snapshot(
                        db,
                        scan_date=resolved_date,
                        api_item=item,
                        eligibility_status=excl_status or ELIGIBILITY_EXCLUDED_CUP,
                        eligibility_reason=excl_status,
                    )
                    by_status[excl_status or ELIGIBILITY_EXCLUDED_CUP] += 1
                    continue

                if not is_fixture_not_started(item, now_rome):
                    _upsert_today_snapshot(
                        db,
                        scan_date=resolved_date,
                        api_item=item,
                        eligibility_status=ELIGIBILITY_EXCLUDED_STARTED,
                        eligibility_reason="fixture_already_started_or_finished",
                    )
                    by_status[ELIGIBILITY_EXCLUDED_STARTED] += 1
                    continue

                after_filter_count += 1
                run_metrics.after_competition_filter = after_filter_count
                run_metrics.fixtures_after_competition_gate = after_filter_count

                _emit_progress(progress, current_step="fetching_odds")
                odds_by_book, odds_warnings, odds_strategy, neg_cache_hit = fetch_fixture_odds_for_cecchino_bookmakers(
                    af_client,
                    api_fid,
                    db=db,
                    scan_date=resolved_date,
                    force_rescan=force_rescan,
                    metrics=run_metrics,
                )
                odds_checked += 1
                run_metrics.odds_checked = odds_checked
                row_warnings.extend(odds_warnings)

                if neg_cache_hit:
                    neg_status = ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER
                    if odds_warnings and "negative_cache:" in odds_warnings[0]:
                        reason = odds_warnings[0].split(":", 1)[-1]
                        if "1x2" in reason:
                            neg_status = ELIGIBILITY_EXCLUDED_MISSING_1X2
                    _upsert_today_snapshot(
                        db,
                        scan_date=resolved_date,
                        api_item=item,
                        eligibility_status=neg_status,
                        eligibility_reason=odds_warnings[0] if odds_warnings else "negative_cache",
                        bookmaker_status="missing",
                        blocking_reasons=[odds_warnings[0]] if odds_warnings else ["negative_cache"],
                    )
                    by_status[neg_status] += 1
                    continue

                bm_ok, odds_snapshot, bm_reason, bm_blocking = verify_complete_1x2_odds(odds_by_book)
                if bm_ok:
                    odds_snapshot = attach_scan_odds_meta(
                        odds_snapshot,
                        from_cache=(odds_strategy == "cached"),
                    )
                if not bm_ok:
                    status = _BOOK_REASON_TO_STATUS.get(bm_reason or "", ELIGIBILITY_EXCLUDED_MISSING_1X2)
                    write_negative_odds_cache(
                        db,
                        None,
                        scan_date=resolved_date,
                        provider_fixture_id=api_fid,
                        odds_check_status=bm_reason or "missing_bookmaker",
                    )
                    _upsert_today_snapshot(
                        db,
                        scan_date=resolved_date,
                        api_item=item,
                        eligibility_status=status,
                        eligibility_reason=bm_reason,
                        bookmaker_status="missing",
                        odds_snapshot=odds_snapshot,
                        warnings=row_warnings,
                        blocking_reasons=bm_blocking,
                        odds_check_status=bm_reason or "missing_bookmaker",
                        odds_checked_at=utc_now(),
                    )
                    by_status[status] += 1
                    continue

                run_metrics.fixtures_after_bookmaker_gate += 1

                local_fx = db.scalar(select(Fixture).where(Fixture.api_fixture_id == api_fid))
                comp: Competition | None = None
                if local_fx is not None and local_fx.competition_id:
                    comp = db.get(Competition, int(local_fx.competition_id))

                league_meta = item.get("league") or {}
                provider_league_id = int(league_meta.get("id") or 0)
                af_client.set_usage_context(
                    usage_ctx.with_fixture(api_fid).with_league(provider_league_id or None),
                )

                if local_fx is None or comp is None:
                    _emit_progress(progress, current_step="importing_stats")
                    try:
                        with db.begin_nested():
                            comp, local_fx, boot_warnings = ensure_competition_and_history(
                                db,
                                api_item=item,
                                client=af_client,
                                bootstrapped_leagues=bootstrapped_leagues,
                                metrics=run_metrics,
                            )
                        row_warnings.extend(boot_warnings)
                    except Exception as exc:
                        logger.exception("Bootstrap Cecchino Today failed fixture=%s", api_fid)
                        recover_session_if_inactive(db)
                        detail = str(exc)[:200]
                        _upsert_today_snapshot(
                            db,
                            scan_date=resolved_date,
                            api_item=item,
                            eligibility_status=ELIGIBILITY_EXCLUDED_MAPPING,
                            eligibility_reason=f"Errore import lega/team/fixture: {detail}",
                            bookmaker_status="ok",
                            odds_snapshot=odds_snapshot,
                            warnings=row_warnings,
                            blocking_reasons=_mapping_blocking_reasons(exc),
                        )
                        by_status[ELIGIBILITY_EXCLUDED_MAPPING] += 1
                        continue

                if comp is None or local_fx is None:
                    _upsert_today_snapshot(
                        db,
                        scan_date=resolved_date,
                        api_item=item,
                        eligibility_status=ELIGIBILITY_EXCLUDED_MAPPING,
                        eligibility_reason="local_fixture_or_competition_missing",
                        bookmaker_status="ok",
                        odds_snapshot=odds_snapshot,
                        warnings=row_warnings,
                    )
                    by_status[ELIGIBILITY_EXCLUDED_MAPPING] += 1
                    continue

                _emit_progress(progress, current_step="importing_stats")
                bundle = build_calculation_input_for_fixture(db, local_fx)
                leakage_check = bundle.data_quality.get("leakage_check") or {}
                if isinstance(leakage_check, dict):
                    leakage_status = str(leakage_check.get("status") or "undefined")
                else:
                    leakage_status = str(leakage_check)

                ctx = build_fixture_contexts(db, local_fx)
                run_metrics.stats_checked += 1
                stats_ok, stats_snapshot, stats_reason = check_cecchino_today_stats_eligible(
                    ctx,
                    leakage_status=leakage_status,
                )
                if not stats_ok:
                    _upsert_today_snapshot(
                        db,
                        scan_date=resolved_date,
                        api_item=item,
                        eligibility_status=stats_reason or ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
                        eligibility_reason=(stats_snapshot.get("failures") or [""])[0],
                        local_fixture_id=int(local_fx.id),
                        competition_id=int(comp.id),
                        bookmaker_status="ok",
                        stats_status="insufficient",
                        odds_snapshot=odds_snapshot,
                        stats_snapshot=stats_snapshot,
                        warnings=row_warnings,
                    )
                    by_status[stats_reason or ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS] += 1
                    continue

                run_metrics.fixtures_after_stats_gate += 1

                _emit_progress(progress, current_step="calculating_cecchino")
                try:
                    sync_today_bookmaker_odds(
                        db,
                        competition_id=int(comp.id),
                        fixture_id=int(local_fx.id),
                        api_fixture_id=api_fid,
                        odds_by_bookmaker=odds_by_book,
                    )
                    db.flush()
                    calc = calculate_and_persist_for_fixture(db, comp, local_fx, persist=True)
                except Exception as exc:
                    logger.exception("Cecchino Today calc failed fixture=%s", api_fid)
                    recover_session_if_inactive(db)
                    _upsert_today_snapshot(
                        db,
                        scan_date=resolved_date,
                        api_item=item,
                        eligibility_status=ELIGIBILITY_ERROR,
                        eligibility_reason=str(exc)[:500],
                        local_fixture_id=int(local_fx.id),
                        competition_id=int(comp.id),
                        bookmaker_status="ok",
                        stats_status="ok",
                        cecchino_status="error",
                        odds_snapshot=odds_snapshot,
                        stats_snapshot=stats_snapshot,
                        warnings=row_warnings + [f"calc_error:{exc!s}"[:200]],
                    )
                    by_status[ELIGIBILITY_ERROR] += 1
                    errors.append(f"fixture {api_fid}: {exc!s}"[:200])
                    continue

                _emit_progress(progress, current_step="validating_eligibility")
                cecchino_output = calc.get("output") or {}
                if local_fx is not None:
                    goal_ctx = build_goal_market_contexts(db, local_fx)
                    cecchino_output["goal_markets"] = build_goal_market_cecchino_odds(
                        db,
                        local_fx,
                        goal_ctx,
                    )
                    rebuilt = rebuild_signals_matrix_for_output(
                        cecchino_output,
                        sample_home_away_split=sample_home_away_split_from_stats(stats_snapshot),
                    )
                    if isinstance(rebuilt, dict) and rebuilt.get("status") == STATUS_AVAILABLE:
                        cecchino_output["signals_matrix"] = rebuilt
                odds_source = "cached_betfair_odds" if odds_strategy == "cached" else "betfair"
                teams = item.get("teams") or {}
                home_name = (teams.get("home") or {}).get("name")
                away_name = (teams.get("away") or {}).get("name")
                betfair_payload = build_betfair_payload_from_raw(
                    odds_by_book,
                    source=odds_source,
                    home_team_name=home_name,
                    away_team_name=away_name,
                )
                if betfair_payload.get("status") == "not_available":
                    betfair_payload = build_betfair_payload_from_snapshot(
                        odds_snapshot,
                        source=odds_source,
                        home_team_name=home_name,
                        away_team_name=away_name,
                    )
                if betfair_payload.get("status") == "not_available":
                    betfair_payload = load_betfair_odds_payload(
                        db,
                        competition_id=int(comp.id),
                        fixture_id=int(local_fx.id),
                    )
                kpi_panel = build_cecchino_kpi_panel_v2_betfair(
                    final_odds=cecchino_output.get("final") or {},
                    betfair_payload=betfair_payload,
                    goal_markets=cecchino_output.get("goal_markets"),
                )
                meta = read_odds_meta(odds_snapshot)
                if meta:
                    kpi_panel["odds_meta"] = meta
                # Compact Acquistabilità preview → cecchino_output (pre-match only)
                existing_prev = None
                existing_row = db.scalar(
                    select(CecchinoTodayFixture).where(
                        CecchinoTodayFixture.scan_date == resolved_date,
                        CecchinoTodayFixture.provider_source == PROVIDER_API_FOOTBALL,
                        CecchinoTodayFixture.provider_fixture_id == api_fid,
                    )
                )
                if existing_row is not None and isinstance(
                    existing_row.cecchino_output_json, dict
                ):
                    existing_prev = existing_row.cecchino_output_json.get(
                        "purchasability_preview"
                    )
                snap_at = None
                snap_src = None
                snap_verified = False
                if isinstance(meta, dict):
                    for fld in ("odds_fetched_at", "fetched_at", "snapshot_at"):
                        if meta.get(fld):
                            snap_at = meta.get(fld)
                            snap_src = f"odds_meta.{fld}"
                            snap_verified = True
                            break
                attach_purchasability_preview_to_output(
                    cecchino_output=cecchino_output,
                    kpi_panel=kpi_panel,
                    fixture_meta={
                        "today_fixture_id": (
                            int(existing_row.id) if existing_row is not None else None
                        ),
                        "local_fixture_id": int(local_fx.id),
                        "provider_fixture_id": api_fid,
                        "competition_id": int(comp.id),
                        "scan_date": resolved_date,
                        "kickoff": getattr(local_fx, "kickoff", None)
                        or (item.get("fixture") or {}).get("date"),
                    },
                    snapshot_info={
                        "snapshot_at": snap_at,
                        "snapshot_source": snap_src,
                        "snapshot_fidelity": (
                            "verified_panel_odds_meta" if snap_verified else "missing"
                        ),
                        "snapshot_timestamp_verified": snap_verified,
                    },
                    existing_preview=existing_prev
                    if isinstance(existing_prev, dict)
                    else None,
                )
                existing_bal = None
                if existing_row is not None and isinstance(
                    existing_row.cecchino_output_json, dict
                ):
                    existing_bal = existing_row.cecchino_output_json.get(
                        "balance_v5_monitoring"
                    )
                attach_balance_v5_monitoring_to_output(
                    cecchino_output=cecchino_output,
                    kpi_panel=kpi_panel,
                    fixture_meta={
                        "today_fixture_id": (
                            int(existing_row.id) if existing_row is not None else None
                        ),
                        "local_fixture_id": int(local_fx.id),
                        "provider_fixture_id": api_fid,
                        "competition_id": int(comp.id),
                        "scan_date": resolved_date,
                        "kickoff": getattr(local_fx, "kickoff", None)
                        or (item.get("fixture") or {}).get("date"),
                    },
                    snapshot_info={
                        "snapshot_at": snap_at,
                        "snapshot_source": snap_src,
                        "snapshot_fidelity": (
                            "verified_panel_odds_meta" if snap_verified else "missing"
                        ),
                        "snapshot_timestamp_verified": snap_verified,
                    },
                    existing_monitoring=existing_bal
                    if isinstance(existing_bal, dict)
                    else None,
                )
                _emit_progress(progress, current_step="saving_snapshots")
                _, eligibility_status = _persist_post_calc_snapshot(
                    db,
                    scan_date=resolved_date,
                    api_item=item,
                    local_fixture_id=int(local_fx.id),
                    competition_id=int(comp.id),
                    odds_snapshot=odds_snapshot,
                    stats_snapshot=stats_snapshot,
                    cecchino_output=cecchino_output,
                    kpi_panel=kpi_panel,
                    row_warnings=row_warnings,
                    calc=calc,
                    leakage_status=leakage_status,
                )
                by_status[eligibility_status] += 1
            except Exception as exc:
                logger.exception(
                    "CecchinoTodayJob fixture_error job_id=%s provider_fixture_id=%s error=%s",
                    job_id,
                    api_fid,
                    exc,
                )
                recover_session_if_inactive(db)
                err_msg = str(exc)[:200]
                errors.append(err_msg)
                by_status[ELIGIBILITY_ERROR] += 1
                if is_datetime_error_message(err_msg):
                    blocking = [classify_datetime_blocking_reason(err_msg)]
                else:
                    blocking = ["calculation_error"]
                if api_fid is not None:
                    try:
                        _upsert_today_snapshot(
                            db,
                            scan_date=resolved_date,
                            api_item=item,
                            eligibility_status=ELIGIBILITY_ERROR,
                            eligibility_reason=err_msg,
                            warnings=[err_msg],
                            blocking_reasons=blocking,
                        )
                    except Exception:
                        logger.exception(
                            "CecchinoTodayJob fixture_error_persist failed provider_fixture_id=%s",
                            api_fid,
                        )
                        recover_session_if_inactive(db)
            finally:
                _emit_progress(
                    progress,
                    progress_current=fixtures_checked,
                    progress_total=total,
                    **_progress_metrics_payload(),
                )
                if job_id:
                    logger.info(
                        "CecchinoTodayJob job_id=%s fixture=%s/%s provider_fixture_id=%s step=%s",
                        job_id,
                        fixtures_checked,
                        total,
                        api_fid,
                        "budget_stop" if budget_stopped else "ok",
                    )
            if budget_stopped:
                break

    db.commit()
    signal_sync_summary = sync_signals_for_scan_date(db, resolved_date)
    db.commit()

    logger.info("Cecchino retention cleanup disabled: historical data is preserved")
    warnings.extend([w for w in warnings if w])
    report = build_cecchino_today_report(
        scan_date=resolved_date,
        total=total,
        by_status=dict(by_status),
        warnings=warnings,
        errors=errors,
    )
    report["fixtures_processed"] = total
    report["provider_items_received"] = provider_items_received
    report["provider_out_of_scan_date_skipped"] = provider_out_of_scan_date_skipped
    report["fixtures_in_scan_date"] = fixtures_in_scan_date
    if out_of_scan_date_examples:
        report["out_of_scan_date_examples"] = out_of_scan_date_examples
    report["signal_sync_summary"] = signal_sync_summary
    if job_id:
        report["job_id"] = job_id

    duration = time.time() - run_metrics.started_at
    excluded_summary = {k: v for k, v in by_status.items() if k != ELIGIBILITY_ELIGIBLE}
    run_metrics.excluded_summary = dict(excluded_summary)
    api_usage_summary = get_api_usage_summary(db, usage_date=resolved_date)
    run_metrics.budget_remaining_estimated = api_usage_summary.get("estimated_remaining_daily_budget")
    report["result_summary"] = run_metrics.to_result_summary(
        fixtures_found=total,
        after_competition_filter=after_filter_count,
        odds_checked=odds_checked,
        eligible_count=by_status.get(ELIGIBILITY_ELIGIBLE, 0),
        excluded_count=sum(excluded_summary.values()),
        excluded_summary=excluded_summary,
        duration_seconds=duration,
        api_usage=api_usage_summary,
        provider_items_received=provider_items_received,
        provider_out_of_scan_date_skipped=provider_out_of_scan_date_skipped,
        fixtures_in_scan_date=fixtures_in_scan_date,
        out_of_scan_date_examples=out_of_scan_date_examples,
    )
    if budget_stopped:
        report["status"] = budget_stop_status
        report["message"] = budget_stop_message
        report["budget_stopped"] = True
        if budget_stop_message not in report["errors"]:
            report["errors"].append(budget_stop_message)
    _emit_progress(
        progress,
        current_step="completed",
        progress_current=total,
        progress_total=total,
        progress_pct=100.0,
        fixtures_checked=total,
        eligible_count=by_status.get(ELIGIBILITY_ELIGIBLE, 0),
        excluded_count=sum(excluded_summary.values()),
    )
    if job_id:
        logger.info(
            "CecchinoTodayJob job_id=%s scan pipeline finished eligible=%s excluded=%s duration=%.1fs",
            job_id,
            by_status.get(ELIGIBILITY_ELIGIBLE, 0),
            sum(excluded_summary.values()),
            duration,
        )
    try:
        from app.services.cecchino.cecchino_balance_v5_readiness import (
            BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING,
            safe_upsert_balance_readiness_daily_snapshot,
        )

        readiness_out = safe_upsert_balance_readiness_daily_snapshot(
            phase="after_today_scan",
            scan_date=resolved_date,
            job_id=job_id,
        )
        if readiness_out.get("status") == "skipped":
            code = str(
                readiness_out.get("warning_code")
                or BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING
            )
            if code not in report["warnings"]:
                report["warnings"].append(code)
    except Exception:
        logger.exception("balance readiness snapshot skipped after scan")
    return report


def run_scan_today(
    db: Session,
    *,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    return run_scan(db, scan_date=rome_today(timezone), timezone=timezone, client=client)


def run_scan_tomorrow(
    db: Session,
    *,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    return run_scan(db, scan_date=rome_tomorrow(timezone), timezone=timezone, client=client)


def run_scan_day(
    db: Session,
    *,
    scan_date: date,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    force_rescan: bool = False,
    client: ApiFootballClient | None = None,
    job_id: str | None = None,
    progress: ProgressReporter | None = None,
    metrics: ScanRunMetrics | None = None,
) -> dict[str, Any]:
    meta = get_day_scan_meta(db, scan_date, timezone=timezone)
    if not force_rescan and meta.get("has_scan"):
        return {
            "status": "already_scanned",
            "version": CECCHINO_TODAY_VERSION,
            "scan_date": scan_date.isoformat(),
            "message": "Giornata già scansionata. Usa force_rescan=true per aggiornare.",
            "scan_meta": meta,
        }
    report = run_scan(
        db,
        scan_date=scan_date,
        timezone=timezone,
        client=client,
        force_rescan=force_rescan,
        progress=progress,
        metrics=metrics,
        job_id=job_id,
    )
    report["scan_meta"] = get_day_scan_meta(db, scan_date, timezone=timezone)
    return report


def revalidate_cecchino_today_day(
    db: Session,
    *,
    scan_date: date,
) -> dict[str, Any]:
    """Ricalcola eleggibilità finale su snapshot persistiti (senza API-Football)."""
    rows = list(
        db.scalars(
            select(CecchinoTodayFixture).where(CecchinoTodayFixture.scan_date == scan_date),
        ).all(),
    )
    kept_eligible = 0
    moved_to_excluded = 0
    reasons: dict[str, int] = defaultdict(int)
    checked = 0

    for row in rows:
        if row.cecchino_output_json is None:
            continue
        checked += 1
        was_eligible = row.eligibility_status == ELIGIBILITY_ELIGIBLE
        leakage_status = _extract_leakage_status(row.stats_snapshot_json)
        combined_warnings: list[str] = list(row.warnings_json or [])
        output = row.cecchino_output_json or {}
        for w in output.get("warnings") or []:
            combined_warnings.append(str(w))
        for w in (output.get("final") or {}).get("warnings") or []:
            combined_warnings.append(str(w))

        result = validate_cecchino_today_final_eligibility(
            odds_snapshot=row.odds_snapshot_json,
            stats_snapshot=row.stats_snapshot_json,
            cecchino_output=output,
            kpi_panel=row.kpi_panel_json,
            warnings=combined_warnings,
            leakage_status=leakage_status,
            calc_status=str(row.cecchino_status or ""),
        )

        row.eligibility_status = result.eligibility_status
        row.eligibility_reason = result.eligibility_reason
        row.blocking_reasons_json = result.blocking_reasons
        row.warnings_json = result.warnings
        if result.is_eligible:
            row.stats_status = "ok"
            kept_eligible += 1
            maybe_ensure_xg_for_eligible_row(db, row)
        else:
            reasons[result.eligibility_status] += 1
            if was_eligible:
                moved_to_excluded += 1
            if result.eligibility_status == ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS:
                row.stats_status = "insufficient"

    db.commit()
    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "date": scan_date.isoformat(),
        "checked": checked,
        "kept_eligible": kept_eligible,
        "moved_to_excluded": moved_to_excluded,
        "reasons": dict(reasons),
    }


def _resolve_row_match_status(row: CecchinoTodayFixture) -> str:
    if row.match_display_status:
        return row.match_display_status
    short = row.fixture_status or "NS"
    display, _ = map_fixture_display_status(short, row.elapsed_minutes)
    return display


def _count_eligible_by_status(rows: list[CecchinoTodayFixture]) -> dict[str, int]:
    counts = {"upcoming": 0, "live": 0, "finished": 0, "postponed": 0, "cancelled": 0, "unknown": 0}
    for row in rows:
        st = _resolve_row_match_status(row)
        if st in counts:
            counts[st] += 1
        else:
            counts["unknown"] += 1
    return counts


def _build_list_filters(rows: list[CecchinoTodayFixture]) -> dict[str, Any]:
    countries: list[str] = []
    leagues: list[str] = []
    statuses: set[str] = set()
    seen_c: set[str] = set()
    seen_l: set[str] = set()
    for row in rows:
        c = row.country_name or "Unknown"
        l = row.league_name or "Unknown"
        if c not in seen_c:
            countries.append(c)
            seen_c.add(c)
        key = f"{c}::{l}"
        if key not in seen_l:
            leagues.append(l)
            seen_l.add(key)
        statuses.add(_resolve_row_match_status(row))
    return {
        "countries": sorted(countries),
        "leagues": sorted(leagues),
        "statuses": sorted(statuses),
    }


def _row_list_item(row: CecchinoTodayFixture) -> dict[str, Any]:
    display_status = _resolve_row_match_status(row)
    kpi_panel = row.kpi_panel_json or {}
    output = row.cecchino_output_json or {}
    return {
        "today_fixture_id": int(row.id),
        "id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
        "competition_id": int(row.competition_id) if row.competition_id else None,
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "home_team_logo_url": row.home_team_logo_url,
        "away_team_logo_url": row.away_team_logo_url,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "status": display_status,
        "status_label": status_label_for_row(row),
        "score": row_score_payload(row),
        "cecchino_recommended_prediction": recommended_prediction_placeholder(),
        "kpi_status": "available" if kpi_panel else "pending",
        "signals_status": "available" if output.get("signals_matrix") else "pending",
    }


def list_eligible_today(
    db: Session,
    *,
    scan_date: date | None = None,
    country: str | None = None,
    league: str | None = None,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
) -> dict[str, Any]:
    resolved = resolve_scan_date(scan_date, timezone)
    meta = get_day_scan_meta(db, resolved, timezone=timezone)
    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date == resolved,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    all_rows = list(db.scalars(q.order_by(CecchinoTodayFixture.kickoff.asc())).all())
    status_counts = _count_eligible_by_status(all_rows)

    rows = all_rows
    if country:
        c_low = country.strip().lower()
        rows = [r for r in rows if (r.country_name or "").lower().find(c_low) >= 0]
    if league:
        l_low = league.strip().lower()
        rows = [r for r in rows if (r.league_name or "").lower().find(l_low) >= 0]

    grouped: dict[str, dict[str, Any]] = {}
    for r in rows:
        cname = r.country_name or "Unknown"
        lname = r.league_name or "Unknown"
        if cname not in grouped:
            grouped[cname] = {"country_name": cname, "country_flag_url": r.country_flag_url, "leagues": {}}
        if not grouped[cname]["country_flag_url"] and r.country_flag_url:
            grouped[cname]["country_flag_url"] = r.country_flag_url
        leagues_map = grouped[cname]["leagues"]
        if lname not in leagues_map:
            leagues_map[lname] = {"league_name": lname, "league_logo_url": r.league_logo_url, "fixtures": []}
        if not leagues_map[lname]["league_logo_url"] and r.league_logo_url:
            leagues_map[lname]["league_logo_url"] = r.league_logo_url
        leagues_map[lname]["fixtures"].append(_row_list_item(r))

    countries = []
    for cname in sorted(grouped.keys()):
        leagues = []
        for lname in sorted(grouped[cname]["leagues"].keys()):
            leagues.append(grouped[cname]["leagues"][lname])
        countries.append(
            {
                "country_name": grouped[cname]["country_name"],
                "country_flag_url": grouped[cname]["country_flag_url"],
                "leagues": leagues,
            },
        )

    summary = {
        "eligible_count": len(all_rows),
        "upcoming_count": status_counts["upcoming"],
        "live_count": status_counts["live"],
        "finished_count": status_counts["finished"],
        "excluded_count": int(meta.get("excluded_count") or 0),
        "last_scan_at": meta.get("last_scan_at"),
    }

    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "date": resolved.isoformat(),
        "scan_date": resolved.isoformat(),
        "is_scanned": bool(meta.get("has_scan")),
        "total": len(rows),
        "summary": summary,
        "filters": _build_list_filters(all_rows),
        "countries": countries,
        "scan_meta": meta,
    }


def update_today_fixture_results(
    db: Session,
    *,
    scan_date: date | None = None,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    resolved = resolve_scan_date(scan_date, timezone)
    af_client = client or ApiFootballClient()
    rows = list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date == resolved,
            ),
        ).all(),
    )
    if not rows:
        return {
            "status": "ok",
            "version": CECCHINO_TODAY_VERSION,
            "date": resolved.isoformat(),
            "fixtures_checked": 0,
            "results_updated": 0,
            "still_upcoming": 0,
            "live": 0,
            "failed": [],
            "warnings": [],
            "api_calls": 0,
        }

    warnings: list[str] = []
    failed: list[dict[str, Any]] = []
    results_updated = 0
    still_upcoming = 0
    live = 0
    api_calls = 0
    signals_evaluated = 0
    signals_pending = 0

    try:
        api_items = af_client.get_fixtures_by_date(resolved.isoformat(), timezone=timezone)
        api_calls += 1
    except ApiFootballError as exc:
        return {
            "status": "error",
            "version": CECCHINO_TODAY_VERSION,
            "date": resolved.isoformat(),
            "message": str(exc),
            "fixtures_checked": len(rows),
            "results_updated": 0,
            "failed": [],
            "warnings": [str(exc)],
            "api_calls": api_calls,
        }

    by_api_id = {
        int((item.get("fixture") or {}).get("id") or 0): item
        for item in api_items
        if (item.get("fixture") or {}).get("id") is not None
    }

    for row in rows:
        api_item = by_api_id.get(int(row.provider_fixture_id))
        if api_item is None:
            try:
                api_item = af_client.get_fixture_by_id(int(row.provider_fixture_id))
                api_calls += 1
            except ApiFootballError as exc:
                failed.append({"provider_fixture_id": row.provider_fixture_id, "error": str(exc)})
                warnings.append(str(exc))
                continue
        if not api_item:
            failed.append(
                {"provider_fixture_id": row.provider_fixture_id, "error": "fixture_not_found"},
            )
            continue

        apply_display_from_api(row, api_item)
        row.raw_fixture_json = api_item
        st = _resolve_row_match_status(row)
        if st == MATCH_UPCOMING:
            still_upcoming += 1
        elif st == MATCH_LIVE:
            live += 1
        results_updated += 1
        eval_counts = evaluate_activations_for_fixture(db, int(row.id))
        signals_evaluated += eval_counts.get("evaluated", 0)
        signals_pending += eval_counts.get("pending", 0)
        try:
            from app.services.cecchino.cecchino_kpi_signals import revaluate_kpi_signals_for_fixture

            revaluate_kpi_signals_for_fixture(db, int(row.id))
        except Exception:
            logger.exception("KPI signals revaluate skipped fixture_id=%s", row.id)
        try:
            from app.services.cecchino.cecchino_purchasability_validation import (
                evaluate_purchasability_validation_for_fixture,
            )

            with db.begin_nested():
                evaluate_purchasability_validation_for_fixture(db, int(row.id))
        except Exception:
            logger.exception(
                "purchasability validation evaluate skipped fixture_id=%s", row.id
            )
        try:
            from app.services.cecchino.cecchino_balance_v5_empirical import (
                settle_balance_empirical_record,
            )

            with db.begin_nested():
                settle_balance_empirical_record(db, fixture=row, commit=False)
        except Exception:
            logger.exception(
                "balance empirical settle skipped fixture_id=%s", row.id
            )

    try:
        from app.services.cecchino.cecchino_balance_v5_readiness import (
            BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING,
            safe_upsert_balance_readiness_daily_snapshot,
        )

        readiness_out = safe_upsert_balance_readiness_daily_snapshot(
            phase="after_update_results",
            scan_date=resolved,
        )
        if readiness_out.get("status") == "skipped":
            code = str(
                readiness_out.get("warning_code")
                or BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING
            )
            if code not in warnings:
                warnings.append(code)
    except Exception:
        logger.exception("balance readiness snapshot skipped after update-results")

    try:
        from app.services.cecchino.cecchino_goal_intensity_v5 import attach_results_for_rows

        attach_results_for_rows(db, rows, commit=False)
    except Exception:
        logger.exception("goal intensity v5 attach skipped after update-results")

    db.commit()
    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "date": resolved.isoformat(),
        "fixtures_checked": len(rows),
        "results_updated": results_updated,
        "still_upcoming": still_upcoming,
        "live": live,
        "failed": failed,
        "warnings": warnings,
        "api_calls": api_calls,
        "signals_evaluated": signals_evaluated,
        "signals_pending": signals_pending,
    }


def _kpi_panel_needs_rebuild(kpi_panel: dict[str, Any] | None) -> bool:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return True
    if kpi_panel.get("version") != KPI_V2_VERSION:
        return True
    rows = kpi_panel.get("rows") or []
    if not rows:
        return True
    data_rows = [r for r in rows if isinstance(r, dict)]
    if not data_rows:
        return True
    if all(r.get("quota_book") is None for r in data_rows):
        return True
    if any(not (r.get("segno") or r.get("label")) for r in data_rows):
        return True
    return False


def _resolve_kpi_panel_for_detail(
    row: CecchinoTodayFixture,
    db: Session,
    *,
    snapshot_only: bool = False,
) -> dict[str, Any] | None:
    """Normalizza o ricostruisce KPI v2 da snapshot/DB per il dettaglio API.

    Con snapshot_only=True (dettaglio storico): solo kpi_panel_json / odds_snapshot_json,
    mai load_betfair_odds_payload dal DB.
    """
    kpi = row.kpi_panel_json
    if not _kpi_panel_needs_rebuild(kpi):
        return normalize_kpi_panel_rows(kpi)

    output = row.cecchino_output_json or {}
    final_odds = (output.get("final") or {}) if isinstance(output, dict) else {}

    betfair_payload = build_betfair_payload_from_snapshot(
        row.odds_snapshot_json,
        source="cached_betfair_odds",
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
    )
    if (
        not snapshot_only
        and betfair_payload.get("status") == "not_available"
        and row.competition_id
        and row.local_fixture_id
    ):
        betfair_payload = load_betfair_odds_payload(
            db,
            competition_id=int(row.competition_id),
            fixture_id=int(row.local_fixture_id),
        )

    if betfair_payload.get("status") == "not_available" and kpi:
        return normalize_kpi_panel_rows(kpi)

    goal_markets = output.get("goal_markets") if isinstance(output, dict) else None
    panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=final_odds,
        betfair_payload=betfair_payload,
        goal_markets=goal_markets,
    )
    meta = read_odds_meta(row.odds_snapshot_json)
    if meta:
        panel["odds_meta"] = meta
    return panel


def get_today_fixture_detail(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
            "eligibility_status": row.eligibility_status,
        }

    output = row.cecchino_output_json or {}
    balance_mode = resolve_balance_detail_mode(row.scan_date, rome_today())
    snapshot_only = balance_mode == MODE_HISTORICAL
    kpi_panel = _resolve_kpi_panel_for_detail(row, db, snapshot_only=snapshot_only)
    picchetti_debug_summary = None
    if isinstance(output, dict) and output:
        full_debug = build_cecchino_picchetti_debug(
            cecchino_output=output,
            kpi_panel=kpi_panel,
        )
        picchetti_debug_summary = build_picchetti_debug_summary(full_debug)
    balance_analysis = build_balance_analysis_from_final(
        output.get("final") if isinstance(output, dict) else {},
    )
    goal_intensity_analysis = build_goal_intensity_for_today_row(db, row)
    expected_goal_engine_diagnostics = build_expected_goal_engine_diagnostics_for_today_row(db, row)
    goal_intensity_v5 = None
    try:
        from app.services.cecchino.cecchino_goal_intensity_v5 import build_today_payload

        goal_intensity_v5 = build_today_payload(db, int(row.id))
    except Exception as exc:
        goal_intensity_v5 = {
            "status": "error",
            "error": "goal_intensity_v5_detail_failed",
            "message": str(exc)[:200],
            "operational_status": "preview_monitored",
            "operational_status_label_it": "Preview monitorata",
            "signals_integration_status": "blocked",
            "no_betting_signals": True,
        }
    # Alias deprecated: stesso payload, una sola computazione
    goal_intensity_v5_preview = {
        **(goal_intensity_v5 or {}),
        "deprecated": True,
        "replacement": "goal_intensity_v5",
    }

    local_fixture: Fixture | None = None
    local_home_name: str | None = None
    local_away_name: str | None = None
    if row.local_fixture_id:
        local_fixture = db.get(Fixture, int(row.local_fixture_id))
        if local_fixture is not None:
            home_team = db.get(Team, int(local_fixture.home_team_id)) if local_fixture.home_team_id else None
            away_team = db.get(Team, int(local_fixture.away_team_id)) if local_fixture.away_team_id else None
            local_home_name = home_team.name if home_team else None
            local_away_name = away_team.name if away_team else None

    fixture_identity_consistency = build_balance_identity_for_detail(
        mode=balance_mode,
        today_row=row,
        local_fixture=local_fixture,
        cecchino_output=output if isinstance(output, dict) else None,
        expected_goal_diagnostics=expected_goal_engine_diagnostics
        if isinstance(expected_goal_engine_diagnostics, dict)
        else None,
        local_home_team_name=local_home_name,
        local_away_team_name=local_away_name,
    )

    kickoff_dt = None
    if row.kickoff:
        try:
            kickoff_dt = ensure_datetime_utc(row.kickoff, field_name="today.kickoff")
        except Exception:
            kickoff_dt = None
    odds_meta = read_odds_meta(row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None)
    book_status, book_warnings = classify_book_snapshot_status(
        kickoff=kickoff_dt,
        odds_meta=odds_meta,
        has_book_odds=_kpi_has_book_odds(kpi_panel if isinstance(kpi_panel, dict) else None),
    )

    balance_v5_snapshot_meta = evaluate_balance_v5_snapshot_meta(
        mode=balance_mode,
        today_row=row,
        identity=fixture_identity_consistency,
        cecchino_output=output if isinstance(output, dict) else None,
        kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
        book_status=book_status,
        book_warnings=book_warnings,
    )

    kpi_for_balance = kpi_panel if isinstance(kpi_panel, dict) else None
    if balance_mode == MODE_HISTORICAL:
        kpi_for_balance = prepare_kpi_for_historical_balance(
            kpi_for_balance,
            book_status=book_status,
        )

    identity_for_balance = identity_for_balance_build(
        fixture_identity_consistency,
        balance_v5_snapshot_meta,
    )

    balance_v5 = build_cecchino_balance_v5(
        cecchino_final=output.get("final") if isinstance(output, dict) else None,
        goal_markets=output.get("goal_markets") if isinstance(output, dict) else None,
        kpi_panel=kpi_for_balance,
        identity_consistency=identity_for_balance,
    )
    if balance_mode == MODE_HISTORICAL:
        balance_v5 = apply_market_deviation_book_gate(
            balance_v5,
            book_status=book_status,
            book_warnings=book_warnings,
        )
    icm_analysis = build_cecchino_icm_analysis(
        balance_analysis=balance_analysis,
        kpi_panel=kpi_panel,
    )
    sync_cecchino_signal_activations(db, int(row.id))
    today_id = int(row.id)
    provider_fid = int(row.provider_fixture_id)
    local_fid = int(row.local_fixture_id) if row.local_fixture_id else None
    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "id": today_id,
        "today_fixture_id": today_id,
        "scan_date": row.scan_date.isoformat(),
        "provider_source": PROVIDER_API_FOOTBALL,
        "provider_fixture_id": provider_fid,
        "local_fixture_id": local_fid,
        "fixture_ids": {
            "today_fixture_id": today_id,
            "local_fixture_id": local_fid,
            "provider_fixture_id": provider_fid,
        },
        "competition_id": int(row.competition_id) if row.competition_id else None,
        "country_name": row.country_name,
        "league_name": row.league_name,
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "fixture_status": row.fixture_status,
        "odds_snapshot": row.odds_snapshot_json,
        "stats_snapshot": row.stats_snapshot_json,
        "cecchino_output": output,
        "signals_matrix": output.get("signals_matrix"),
        "kpi_panel": kpi_panel,
        "kpi_panel_v2": kpi_panel,
        "picchetti_debug_summary": picchetti_debug_summary,
        "icm_analysis": icm_analysis,
        "balance_analysis": balance_analysis,
        "balance_v5": balance_v5,
        "balance_v5_snapshot_meta": balance_v5_snapshot_meta,
        "fixture_identity_consistency": fixture_identity_consistency,
        "goal_intensity_analysis": goal_intensity_analysis,
        "goal_intensity_v5": goal_intensity_v5,
        "goal_intensity_v5_preview": goal_intensity_v5_preview,
        "expected_goal_engine_diagnostics": expected_goal_engine_diagnostics,
        "purchasability_preview": resolve_purchasability_preview_for_detail(
            row=row,
            kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
        ),
        "bookmaker_odds_detail": build_bookmaker_odds_detail(kpi_panel),
        "cecchino_link": (
            f"/cecchino?competition_id={row.competition_id}&fixture_id={row.local_fixture_id}"
            if row.competition_id and row.local_fixture_id
            else None
        ),
        "warnings": list(row.warnings_json or []),
    }


def list_excluded_today(
    db: Session,
    *,
    scan_date: date | None = None,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
) -> dict[str, Any]:
    """Lista escluse con diagnostica arricchita."""
    return list_excluded_today_enriched(db, scan_date=scan_date, timezone=timezone)


def _sample_from_stats_snapshot(stats_snapshot: dict[str, Any] | None, key: str) -> int:
    if not stats_snapshot:
        return 0
    block = (stats_snapshot.get("input_snapshot") or stats_snapshot).get(key) or {}
    if isinstance(block, dict):
        return int(block.get("sample_count") or 0)
    return 0


def build_bookmaker_debug(row: CecchinoTodayFixture) -> dict[str, str]:
    odds = row.odds_snapshot_json or {}
    books = odds.get("bookmakers") or {}
    missing_list = list(odds.get("missing") or [])
    out: dict[str, str] = {}
    for name in _BOOKMAKER_NAMES:
        if name in books:
            vals = books[name]
            if isinstance(vals, dict) and all(vals.get(k) is not None for k in ("HOME", "DRAW", "AWAY")):
                out[name] = "available"
            else:
                out[name] = "missing_1x2"
        elif name in missing_list:
            out[name] = "missing_1x2" if books else "missing"
        else:
            out[name] = "missing"
    if row.eligibility_status == ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER:
        for name in _BOOKMAKER_NAMES:
            if out.get(name) != "available":
                out[name] = "missing"
    elif row.eligibility_status == ELIGIBILITY_EXCLUDED_MISSING_1X2:
        for name in _BOOKMAKER_NAMES:
            if out.get(name) != "available":
                out[name] = "missing_1x2"
    return out


def build_stats_debug(row: CecchinoTodayFixture) -> dict[str, Any]:
    snap = row.stats_snapshot_json or {}
    status = "available"
    if row.eligibility_status == ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS:
        status = "insufficient"
    elif row.stats_status == "insufficient":
        status = "insufficient"
    elif not snap and row.eligibility_status not in (ELIGIBILITY_ELIGIBLE,):
        status = "insufficient"
    return {
        "status": status,
        "home_context_sample": _sample_from_stats_snapshot(snap, KEY_HOME_CONTEXT),
        "away_context_sample": _sample_from_stats_snapshot(snap, KEY_AWAY_CONTEXT),
        "home_total_sample": _sample_from_stats_snapshot(snap, KEY_HOME_TOTAL),
        "away_total_sample": _sample_from_stats_snapshot(snap, KEY_AWAY_TOTAL),
    }


def build_competition_filter_debug(row: CecchinoTodayFixture) -> dict[str, Any]:
    if row.eligibility_status in _COMPETITION_EXCLUDED_STATUSES:
        return {"allowed": False, "reason": row.eligibility_status}
    return {"allowed": True, "reason": None}


def build_fixture_status_debug(row: CecchinoTodayFixture) -> dict[str, Any]:
    raw = row.raw_fixture_json or {}
    fx = raw.get("fixture") or {}
    status_block = fx.get("status") or {}
    short = row.fixture_status or status_block.get("short") or "unknown"
    message = None
    if row.eligibility_status == ELIGIBILITY_EXCLUDED_STARTED:
        message = "Esclusa perché partita già iniziata o conclusa al momento dello scan"
    return {
        "fixture_status_at_scan": short,
        "elapsed_at_scan": status_block.get("elapsed"),
        "message": message,
    }


def build_exclusion_reason_message(row: CecchinoTodayFixture) -> str | None:
    if row.eligibility_status == ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER:
        bm = build_bookmaker_debug(row)
        missing = [n for n in _BOOKMAKER_NAMES if bm.get(n) != "available"]
        if missing:
            return f"Esclusa perché manca {' / '.join(missing)}"
    labels = {
        ELIGIBILITY_EXCLUDED_MISSING_1X2: "Esclusa perché manca mercato 1X2 completo su Betfair",
        ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS: "Esclusa perché statistiche insufficienti",
        ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO: "Esclusa perché un picchetto Cecchino obbligatorio non è calcolabile",
        ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY: "Esclusa per probabilità zero su 1/X/2",
        ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE: "Esclusa perché le quote finali Cecchino non sono calcolabili",
        ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE: "Esclusa perché il KPI 1X2 non è calcolabile",
        ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED: "Esclusa perché il leakage check non è superato",
    }
    if row.eligibility_status in labels:
        return labels[row.eligibility_status]
    if row.eligibility_status in _COMPETITION_EXCLUDED_STATUSES:
        return f"Esclusa per filtro competizione ({row.eligibility_status})"
    if row.eligibility_status == ELIGIBILITY_EXCLUDED_STARTED:
        return "Esclusa perché partita già iniziata al momento dello scan"
    return row.eligibility_reason


def _excluded_fixture_payload(row: CecchinoTodayFixture, db: Session | None = None) -> dict[str, Any]:
    reason_msg = build_exclusion_reason_message(row)
    stats_snap = row.stats_snapshot_json or {}
    payload = {
        "id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "league_name": row.league_name,
        "country_name": row.country_name,
        "kickoff": safe_isoformat(row.kickoff, field_name="kickoff"),
        "eligibility_status": row.eligibility_status,
        "eligibility_reason": reason_msg or row.eligibility_reason,
        "blocking_reasons": list(row.blocking_reasons_json or []),
        "bookmaker_debug": build_bookmaker_debug(row),
        "stats_debug": build_stats_debug(row),
        "cecchino_debug": build_cecchino_debug(row.cecchino_output_json),
        "kpi_debug": build_kpi_debug(
            row.kpi_panel_json,
            eligibility_status=row.eligibility_status,
            eligibility_reason=row.eligibility_reason,
            blocking_reasons=list(row.blocking_reasons_json or []),
        ),
        "datetime_debug": build_datetime_debug(row.kickoff, raw_fixture=row.raw_fixture_json),
        "import_info": list(stats_snap.get("import_info") or []),
        "competition_filter_debug": build_competition_filter_debug(row),
        "fixture_status_debug": build_fixture_status_debug(row),
        "warnings": list(row.warnings_json or []),
    }
    if db is not None:
        payload["api_usage_debug"] = build_api_usage_debug_for_fixture(
            db,
            provider_fixture_id=int(row.provider_fixture_id),
            scan_date=row.scan_date,
        )
    return payload


def list_excluded_today_enriched(
    db: Session,
    *,
    scan_date: date | None = None,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
) -> dict[str, Any]:
    resolved = resolve_scan_date(scan_date, timezone)
    rows = list(
        db.scalars(
            select(CecchinoTodayFixture)
            .where(
                CecchinoTodayFixture.scan_date == resolved,
                CecchinoTodayFixture.eligibility_status != ELIGIBILITY_ELIGIBLE,
            )
            .order_by(CecchinoTodayFixture.eligibility_status, CecchinoTodayFixture.kickoff.asc()),
        ).all(),
    )
    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "scan_date": resolved.isoformat(),
        "total": len(rows),
        "fixtures": [_excluded_fixture_payload(r, db) for r in rows],
        "scan_meta": get_day_scan_meta(db, resolved, timezone=timezone),
    }


def _aggregate_scan_dates(db: Session) -> dict[date, dict[str, Any]]:
    rows = db.execute(
        select(
            CecchinoTodayFixture.scan_date,
            func.count().filter(CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE).label(
                "eligible_count",
            ),
            func.count().filter(CecchinoTodayFixture.eligibility_status != ELIGIBILITY_ELIGIBLE).label(
                "excluded_count",
            ),
            func.count().filter(
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
                or_(
                    CecchinoTodayFixture.match_display_status == MATCH_UPCOMING,
                    CecchinoTodayFixture.match_display_status.is_(None),
                ),
            ).label("upcoming_count"),
            func.count().filter(
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
                CecchinoTodayFixture.match_display_status == MATCH_LIVE,
            ).label("live_count"),
            func.count().filter(
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
                CecchinoTodayFixture.match_display_status == MATCH_FINISHED,
            ).label("finished_count"),
            func.max(CecchinoTodayFixture.updated_at).label("last_scan_at"),
        ).group_by(CecchinoTodayFixture.scan_date),
    ).all()
    out: dict[date, dict[str, Any]] = {}
    for scan_date, eligible, excluded, upcoming, live, finished, last_at in rows:
        out[scan_date] = {
            "eligible_count": int(eligible or 0),
            "excluded_count": int(excluded or 0),
            "upcoming_count": int(upcoming or 0),
            "live_count": int(live or 0),
            "finished_count": int(finished or 0),
            "last_scan_at": last_at.isoformat() if last_at else None,
            "has_scan": True,
        }
    return out


def get_day_scan_meta(
    db: Session,
    scan_date: date,
    *,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
) -> dict[str, Any]:
    agg = _aggregate_scan_dates(db).get(scan_date)
    if agg is None:
        return {
            "has_scan": False,
            "is_scanned": False,
            "eligible_count": 0,
            "excluded_count": 0,
            "upcoming_count": 0,
            "live_count": 0,
            "finished_count": 0,
            "last_scan_at": None,
            "day_status": "pending",
            "scan_state": "not_scanned",
        }
    return {
        **agg,
        "is_scanned": True,
        "day_status": "available",
        "scan_state": "scanned",
    }


_WEEKDAY_IT = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")


def _timeline_day_label(d: date, today: date, tomorrow: date) -> str:
    if d == today:
        return "Oggi"
    if d == tomorrow:
        return "Domani"
    return _WEEKDAY_IT[d.weekday()]


def list_available_days(
    db: Session,
    *,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    window_days: int = CECCHINO_TODAY_TIMELINE_WINDOW_DAYS,
) -> dict[str, Any]:
    from app.services.cecchino.cecchino_today_scan_job_service import (
        get_active_jobs_by_dates,
        get_latest_jobs_by_dates,
        recover_stale_scan_jobs,
    )

    recover_stale_scan_jobs(db)
    today = rome_today(timezone)
    tomorrow = rome_tomorrow(timezone)
    agg = _aggregate_scan_dates(db)

    day_dates: list[date] = [today + timedelta(days=offset) for offset in range(-window_days, window_days + 1)]
    active_jobs = get_active_jobs_by_dates(db, day_dates)
    latest_jobs = get_latest_jobs_by_dates(db, day_dates)

    day_entries: list[dict[str, Any]] = []
    for d in day_dates:
        meta = agg.get(d)
        has_scan = meta is not None
        active_job = active_jobs.get(d)
        latest_job = latest_jobs.get(d)
        scan_job_status = active_job.status if active_job else None
        scan_job_id = active_job.job_id if active_job else None

        if active_job is not None:
            scan_status = active_job.status
            active_job_id = active_job.job_id
            scan_state = "scanning"
        elif latest_job is not None and latest_job.status in ("failed", "completed", "cancelled"):
            scan_status = latest_job.status
            active_job_id = latest_job.job_id
            scan_state = "error" if latest_job.status == "failed" else "scanned"
        elif has_scan:
            scan_status = "completed"
            active_job_id = latest_job.job_id if latest_job else None
            scan_state = "scanned"
        else:
            scan_status = "not_scanned"
            active_job_id = None
            scan_state = "not_scanned"

        day_entries.append(
            {
                "date": d.isoformat(),
                "label": _timeline_day_label(d, today, tomorrow),
                "is_today": d == today,
                "is_future": d > today,
                "is_scanned": has_scan,
                "eligible_count": int(meta["eligible_count"]) if meta else 0,
                "excluded_count": int(meta["excluded_count"]) if meta else 0,
                "upcoming_count": int(meta["upcoming_count"]) if meta else 0,
                "live_count": int(meta["live_count"]) if meta else 0,
                "finished_count": int(meta["finished_count"]) if meta else 0,
                "last_scan_at": meta.get("last_scan_at") if meta else None,
                "scan_state": scan_state,
                "status": "available" if has_scan else "pending",
                "scan_status": scan_status,
                "active_job_id": active_job_id,
                "scan_job_status": scan_job_status,
                "scan_job_id": scan_job_id or active_job_id,
            },
        )

    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "timezone": timezone,
        "today": today.isoformat(),
        "tomorrow": tomorrow.isoformat(),
        "selected_default": today.isoformat(),
        "days": day_entries,
    }


def cleanup_cecchino_today_snapshots(
    db: Session,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    dry_run: bool = True,
    confirm: str | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Cleanup manuale/admin — mai invocare da scan automatici.

    ATTENZIONE: DELETE su cecchino_today_fixtures cascada su cecchino_signal_activations
    (FK ondelete=CASCADE). Richiede dry_run=false, CECCHINO_ALLOW_DESTRUCTIVE_CLEANUP=true
    e confirm=DELETE_CECCHINO_HISTORY.
    """
    from app.core.config import get_settings

    today = rome_today(timezone)
    cutoff = today - timedelta(days=retention_days)
    base = {
        "cutoff_date": cutoff.isoformat(),
        "retention_days": retention_days,
        "protected_from": today.isoformat(),
        "dry_run": dry_run,
    }

    count_stmt = (
        select(func.count())
        .select_from(CecchinoTodayFixture)
        .where(CecchinoTodayFixture.scan_date < cutoff)
    )
    would_delete = int(db.scalar(count_stmt) or 0)

    if dry_run:
        return {
            **base,
            "status": "ok",
            "deleted": 0,
            "would_delete": would_delete,
            "message": "Dry run only — no rows deleted",
        }

    if not get_settings().cecchino_allow_destructive_cleanup:
        logger.warning(
            "Cecchino destructive cleanup blocked: CECCHINO_ALLOW_DESTRUCTIVE_CLEANUP is false",
        )
        return {
            **base,
            "status": "blocked",
            "reason": "env_flag_disabled",
            "deleted": 0,
            "would_delete": would_delete,
        }

    if confirm != CECCHINO_CLEANUP_CONFIRM_TOKEN:
        logger.warning("Cecchino destructive cleanup blocked: confirm token required")
        return {
            **base,
            "status": "blocked",
            "reason": "confirm_required",
            "deleted": 0,
            "would_delete": would_delete,
        }

    result = db.execute(
        delete(CecchinoTodayFixture).where(CecchinoTodayFixture.scan_date < cutoff),
    )
    deleted = int(result.rowcount or 0)
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        **base,
        "status": "ok",
        "deleted": deleted,
        "would_delete": would_delete,
    }


def debug_search(
    db: Session,
    *,
    scan_date: date | None = None,
    q: str,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
) -> dict[str, Any]:
    resolved = resolve_scan_date(scan_date, timezone)
    term = (q or "").strip()
    if not term:
        return {
            "status": "error",
            "message": "Parametro q obbligatorio",
            "scan_date": resolved.isoformat(),
            "results": [],
        }

    pattern = f"%{term}%"
    rows = list(
        db.scalars(
            select(CecchinoTodayFixture)
            .where(
                CecchinoTodayFixture.scan_date == resolved,
                or_(
                    CecchinoTodayFixture.home_team_name.ilike(pattern),
                    CecchinoTodayFixture.away_team_name.ilike(pattern),
                    CecchinoTodayFixture.league_name.ilike(pattern),
                    CecchinoTodayFixture.country_name.ilike(pattern),
                ),
            )
            .order_by(CecchinoTodayFixture.kickoff.asc()),
        ).all(),
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        if row.eligibility_status == ELIGIBILITY_ELIGIBLE:
            results.append(
                {
                    "match_type": "eligible",
                    "fixture": _row_list_item(row),
                    "message": "Partita eleggibile",
                },
            )
        else:
            results.append(
                {
                    "match_type": "excluded",
                    "fixture": _excluded_fixture_payload(row, db),
                    "message": f"Esclusa: {row.eligibility_status}",
                },
            )

    if not results:
        return {
            "status": "ok",
            "scan_date": resolved.isoformat(),
            "query": term,
            "match_type": "not_found",
            "message": (
                "Partita non trovata nello scan persistito per questa data. "
                "Potrebbe non essere stata restituita da API-Football o non ancora scansionata."
            ),
            "results": [],
        }

    return {
        "status": "ok",
        "scan_date": resolved.isoformat(),
        "query": term,
        "results": results,
    }
