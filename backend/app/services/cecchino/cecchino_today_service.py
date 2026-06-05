"""Orchestrazione Cecchino Today — discovery manuale giornaliera."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Competition, Fixture
from app.models.cecchino_today_fixture import (
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
from app.services.bookmakers.fixture_bookmaker_odds_repository import upsert_selection_odds
from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_sync_service import SLEEP_BETWEEN_CALLS_S
from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOKMAKERS,
    KEY_AWAY_CONTEXT,
    KEY_AWAY_TOTAL,
    KEY_HOME_CONTEXT,
    KEY_HOME_TOTAL,
    PROVIDER_API_FOOTBALL as BM_PROVIDER,
)
from app.services.cecchino.cecchino_fixture_history import build_fixture_contexts
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, MARKET_DC, MARKET_OU
from app.services.cecchino.cecchino_service import (
    build_calculation_input_for_fixture,
    calculate_and_persist_for_fixture,
)
from app.services.cecchino.cecchino_today_bookmaker_gate import verify_complete_1x2_odds
from app.services.cecchino.cecchino_today_bootstrap import ensure_competition_and_history
from app.services.cecchino.cecchino_today_competition_filter import is_cecchino_allowed_competition
from app.services.cecchino.cecchino_today_constants import (
    CECCHINO_TODAY_VERSION,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_TODAY_TIMEZONE,
    TIMELINE_WINDOW_DAYS,
)
from app.services.cecchino.cecchino_today_display import (
    apply_display_from_api,
    extract_display_assets,
    map_fixture_display_status,
    recommended_prediction_placeholder,
    row_score_payload,
    status_label_for_row,
)
from app.services.cecchino.cecchino_today_fixture_filter import is_fixture_not_started
from app.services.cecchino.league_ingest_helpers import recover_session_if_inactive
from app.services.cecchino.cecchino_today_final_eligibility import (
    build_cecchino_debug,
    build_kpi_debug,
    partition_scan_warnings,
    validate_cecchino_today_final_eligibility,
)
from app.services.cecchino.cecchino_today_stats_gate import check_cecchino_today_stats_eligible

logger = logging.getLogger(__name__)

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

_BOOKMAKER_NAMES = ("Bet365", "Betfair", "Pinnacle")


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
        eligibility_reason = str(calc.get("message") or calc.get("code") or "calculation_error")[:500]
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
    return row, eligibility_status


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
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


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
    """Fetch quote 1X2 per tutti i book Cecchino con throttle."""
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for idx, bm in enumerate(CECCHINO_BOOKMAKERS):
        if idx > 0:
            time.sleep(SLEEP_BETWEEN_CALLS_S)
        bid = int(bm["provider_bookmaker_id"])
        try:
            odds_by_book[bid] = client.get_fixture_odds(api_fixture_id, bid)
        except ApiFootballError as exc:
            warnings.append(f"fixture {api_fixture_id} {bm['name']}: {exc}")
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
    now = datetime.now(timezone.utc)
    wanted = [MARKET_1X2, MARKET_DC, MARKET_OU]
    for bm in CECCHINO_BOOKMAKERS:
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
    row.warnings_json = warnings or []
    row.blocking_reasons_json = blocking_reasons or []
    apply_display_from_api(row, api_item)
    if eligibility_status == ELIGIBILITY_ELIGIBLE and row.match_display_status not in (
        MATCH_LIVE,
        MATCH_FINISHED,
    ):
        row.match_display_status = MATCH_UPCOMING
    db.flush()
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


def run_scan(
    db: Session,
    *,
    scan_date: date | None = None,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    """Pipeline completa discovery Cecchino Today."""
    resolved_date = resolve_scan_date(scan_date, timezone)
    now_rome = datetime.now(ZoneInfo(timezone))
    af_client = client or ApiFootballClient()
    warnings: list[str] = []
    by_status: dict[str, int] = defaultdict(int)

    try:
        raw_items = af_client.get_fixtures_by_date(resolved_date.isoformat(), timezone=timezone)
    except ApiFootballError as exc:
        return {
            "status": "error",
            "version": CECCHINO_TODAY_VERSION,
            "scan_date": resolved_date.isoformat(),
            "message": str(exc),
            "total_discovered": 0,
            "eligible": 0,
            "excluded": {},
            "warnings": [str(exc)],
        }

    for item in raw_items:
        brief = _item_brief(item)
        api_fid = brief["provider_fixture_id"]
        row_warnings: list[str] = []

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

        odds_by_book, odds_warnings = fetch_today_bookmaker_odds(af_client, api_fid)
        row_warnings.extend(odds_warnings)
        bm_ok, odds_snapshot, bm_reason = verify_complete_1x2_odds(odds_by_book)
        if not bm_ok:
            status = _BOOK_REASON_TO_STATUS.get(bm_reason or "", ELIGIBILITY_EXCLUDED_MISSING_1X2)
            _upsert_today_snapshot(
                db,
                scan_date=resolved_date,
                api_item=item,
                eligibility_status=status,
                eligibility_reason=bm_reason,
                bookmaker_status="missing",
                odds_snapshot=odds_snapshot,
                warnings=row_warnings,
            )
            by_status[status] += 1
            continue

        local_fx = db.scalar(select(Fixture).where(Fixture.api_fixture_id == api_fid))
        comp: Competition | None = None
        if local_fx is not None and local_fx.competition_id:
            comp = db.get(Competition, int(local_fx.competition_id))

        if local_fx is None or comp is None:
            try:
                with db.begin_nested():
                    comp, local_fx, boot_warnings = ensure_competition_and_history(
                        db,
                        api_item=item,
                        client=af_client,
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

        bundle = build_calculation_input_for_fixture(db, local_fx)
        leakage_check = bundle.data_quality.get("leakage_check") or {}
        if isinstance(leakage_check, dict):
            leakage_status = str(leakage_check.get("status") or "undefined")
        else:
            leakage_status = str(leakage_check)

        ctx = build_fixture_contexts(db, local_fx)
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

        try:
            sync_today_bookmaker_odds(
                db,
                competition_id=int(comp.id),
                fixture_id=int(local_fx.id),
                api_fixture_id=api_fid,
                odds_by_bookmaker=odds_by_book,
            )
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
            continue

        cecchino_output = calc.get("output")
        kpi_panel = calc.get("kpi_panel")
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

    db.commit()
    cleanup_result = cleanup_cecchino_today_snapshots(
        db,
        retention_days=DEFAULT_RETENTION_DAYS,
        timezone=timezone,
        commit=True,
    )
    warnings.extend([w for w in warnings if w])
    report = build_cecchino_today_report(
        scan_date=resolved_date,
        total=len(raw_items),
        by_status=dict(by_status),
        warnings=warnings,
    )
    report["fixtures_processed"] = len(raw_items)
    report["cleanup"] = cleanup_result
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
    report = run_scan(db, scan_date=scan_date, timezone=timezone, client=client)
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
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
            ),
        ).all(),
    )
    warnings: list[str] = []
    failed: list[dict[str, Any]] = []
    results_updated = 0
    still_upcoming = 0
    live = 0

    for idx, row in enumerate(rows):
        if idx > 0:
            time.sleep(SLEEP_BETWEEN_CALLS_S)
        try:
            api_item = af_client.get_fixture_by_id(int(row.provider_fixture_id))
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
    }


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
    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "id": int(row.id),
        "scan_date": row.scan_date.isoformat(),
        "provider_fixture_id": int(row.provider_fixture_id),
        "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
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
        "kpi_panel": row.kpi_panel_json,
        "cecchino_link": (
            f"/cecchino?competition_id={row.competition_id}&fixture_id={row.local_fixture_id}"
            if row.competition_id and row.local_fixture_id
            else None
        ),
        "warnings": row.warnings_json or [],
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
        ELIGIBILITY_EXCLUDED_MISSING_1X2: "Esclusa perché manca mercato 1X2 completo su uno o più bookmaker",
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


def _excluded_fixture_payload(row: CecchinoTodayFixture) -> dict[str, Any]:
    reason_msg = build_exclusion_reason_message(row)
    stats_snap = row.stats_snapshot_json or {}
    return {
        "id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "league_name": row.league_name,
        "country_name": row.country_name,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "eligibility_status": row.eligibility_status,
        "eligibility_reason": reason_msg or row.eligibility_reason,
        "blocking_reasons": list(row.blocking_reasons_json or []),
        "bookmaker_debug": build_bookmaker_debug(row),
        "stats_debug": build_stats_debug(row),
        "cecchino_debug": build_cecchino_debug(row.cecchino_output_json),
        "kpi_debug": build_kpi_debug(row.kpi_panel_json),
        "import_info": list(stats_snap.get("import_info") or []),
        "competition_filter_debug": build_competition_filter_debug(row),
        "fixture_status_debug": build_fixture_status_debug(row),
        "warnings": list(row.warnings_json or []),
    }


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
        "fixtures": [_excluded_fixture_payload(r) for r in rows],
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
    window_days: int = TIMELINE_WINDOW_DAYS,
) -> dict[str, Any]:
    today = rome_today(timezone)
    tomorrow = rome_tomorrow(timezone)
    agg = _aggregate_scan_dates(db)

    day_entries: list[dict[str, Any]] = []
    for offset in range(-window_days, window_days + 1):
        d = today + timedelta(days=offset)
        meta = agg.get(d)
        has_scan = meta is not None
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
                "scan_state": "scanned" if has_scan else "not_scanned",
                "status": "available" if has_scan else "pending",
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
    commit: bool = False,
) -> dict[str, Any]:
    today = rome_today(timezone)
    cutoff = today - timedelta(days=retention_days)
    result = db.execute(
        delete(CecchinoTodayFixture).where(CecchinoTodayFixture.scan_date < cutoff),
    )
    deleted = int(result.rowcount or 0)
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        "status": "ok",
        "deleted": deleted,
        "cutoff_date": cutoff.isoformat(),
        "retention_days": retention_days,
        "protected_from": today.isoformat(),
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
                    "fixture": _excluded_fixture_payload(row),
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
