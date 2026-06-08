"""Refresh quote Betfair singola fixture Cecchino Today."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.api_football_client import ApiFootballClient
from app.services.api_usage_context import ApiUsageContext, BudgetGuardStop
from app.services.api_usage_service import check_api_budget_before_scan
from app.services.cecchino.cecchino_betfair_markets_export import (
    _MANUAL_NOTE,
    parse_all_betfair_markets,
)
from app.services.cecchino.cecchino_betfair_odds_payload import build_betfair_payload_from_raw
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import build_cecchino_kpi_panel_v2_betfair
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME
from app.services.cecchino.cecchino_today_bookmaker_gate import verify_complete_1x2_odds
from app.services.cecchino.cecchino_today_odds_fetch import (
    _BETFAIR_ID,
    _fetch_betfair_only,
    clear_negative_odds_cache,
)
from app.services.cecchino.cecchino_today_odds_meta import (
    attach_refresh_odds_meta,
    attach_scan_odds_meta,
    bookmaker_meta_block,
    extract_1x2_from_snapshot,
    read_odds_meta,
)
from app.services.cecchino.cecchino_today_service import sync_today_bookmaker_odds

_MANUAL_COMPARISON = {
    "message": _MANUAL_NOTE,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compare_1x2(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, list[str]]:
    changed_markets: list[str] = []
    for key in ("HOME", "DRAW", "AWAY"):
        b = before.get(key)
        a = after.get(key)
        if b is not None and a is not None and float(b) != float(a):
            changed_markets.append(key)
        elif (b is None) != (a is None):
            changed_markets.append(key)
    return bool(changed_markets), changed_markets


def _fetch_betfair_raw(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    client: ApiFootballClient | None = None,
) -> tuple[dict[int, list], list[str], int]:
    """Fetch live Betfair-only con API usage tracking."""
    af_client = client or ApiFootballClient()
    af_client.set_usage_db(db)
    usage_ctx = ApiUsageContext(
        job_id=f"refresh_single_fixture_betfair:{row.id}",
        scan_date=row.scan_date,
        record_events=True,
    )
    af_client.set_usage_context(usage_ctx.with_fixture(int(row.provider_fixture_id)))
    odds_by_book, warnings = _fetch_betfair_only(
        af_client,
        int(row.provider_fixture_id),
        metrics=None,
    )
    api_calls = 1 if odds_by_book.get(_BETFAIR_ID) else 0
    return odds_by_book, warnings, api_calls


def refresh_betfair_odds_for_fixture(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    force: bool = True,
    rebuild_kpi: bool = True,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
        }

    try:
        check_api_budget_before_scan(db, usage_date=row.scan_date)
    except BudgetGuardStop as bg:
        return {
            "status": "budget_blocked",
            "message": bg.message,
            "details": bg.details,
        }

    before = extract_1x2_from_snapshot(row.odds_snapshot_json)
    warnings: list[str] = []
    api_calls_used = 0

    if force:
        odds_by_book, fetch_warnings, api_calls_used = _fetch_betfair_raw(db, row, client=client)
        warnings.extend(fetch_warnings)
        ok, new_snapshot, reason, blocking = verify_complete_1x2_odds(odds_by_book)
        if not ok:
            return {
                "status": "error",
                "code": reason or "odds_unavailable",
                "message": "Quote Betfair 1X2 non disponibili dopo refresh",
                "blocking_reasons": blocking,
                "warnings": warnings,
                "before": before,
            }
        new_snapshot = attach_refresh_odds_meta(new_snapshot)
        row.odds_snapshot_json = new_snapshot
        clear_negative_odds_cache(row)
        row.odds_checked_at = _utcnow()

        if row.local_fixture_id and row.competition_id:
            sync_today_bookmaker_odds(
                db,
                competition_id=int(row.competition_id),
                fixture_id=int(row.local_fixture_id),
                api_fixture_id=int(row.provider_fixture_id),
                odds_by_bookmaker=odds_by_book,
            )
            db.flush()

        if rebuild_kpi:
            output = row.cecchino_output_json or {}
            betfair_payload = build_betfair_payload_from_raw(
                odds_by_book,
                source="api_live_refresh",
                home_team_name=row.home_team_name,
                away_team_name=row.away_team_name,
            )
            kpi_panel = build_cecchino_kpi_panel_v2_betfair(
                final_odds=(output.get("final") or {}) if isinstance(output, dict) else {},
                betfair_payload=betfair_payload,
                goal_markets=output.get("goal_markets") if isinstance(output, dict) else None,
            )
            meta = read_odds_meta(row.odds_snapshot_json)
            kpi_panel["odds_meta"] = meta
            row.kpi_panel_json = kpi_panel
    else:
        snap = row.odds_snapshot_json or {}
        if not read_odds_meta(snap):
            row.odds_snapshot_json = attach_scan_odds_meta(snap, from_cache=True)

    db.commit()
    db.refresh(row)

    after = extract_1x2_from_snapshot(row.odds_snapshot_json)
    changed, changed_markets = _compare_1x2(before, after)
    meta = read_odds_meta(row.odds_snapshot_json)

    if force and not changed:
        warnings.append(
            "Il feed API-Football Betfair restituisce ancora quote identiche al valore precedente. "
            "Confrontare con app Betfair: possibile ritardo feed o snapshot diverso.",
        )

    kpi_panel = row.kpi_panel_json if rebuild_kpi else None

    return {
        "status": "ok",
        "today_fixture_id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "bookmaker": bookmaker_meta_block(
            meta,
            provider_bookmaker_id=_BETFAIR_ID,
            name=CECCHINO_BOOKMAKER["name"],
            provider_source=PROVIDER_API_FOOTBALL,
        ),
        "before": before,
        "after": after,
        "changed": changed,
        "changed_markets": changed_markets,
        "kpi_panel": kpi_panel,
        "api_calls_used": api_calls_used,
        "manual_comparison_note": _MANUAL_COMPARISON,
        "warnings": warnings,
    }


def build_betfair_markets_json(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    force: bool = False,
    client: ApiFootballClient | None = None,
    persist_snapshot: bool = False,
) -> dict[str, Any]:
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
        }

    warnings: list[str] = []
    raw_items: list[dict[str, Any]] = []
    api_calls_used = 0

    if force:
        try:
            check_api_budget_before_scan(db, usage_date=row.scan_date)
        except BudgetGuardStop as bg:
            return {
                "status": "budget_blocked",
                "message": bg.message,
                "details": bg.details,
            }
        odds_by_book, fetch_warnings, api_calls_used = _fetch_betfair_raw(db, row, client=client)
        warnings.extend(fetch_warnings)
        raw_items = odds_by_book.get(_BETFAIR_ID) or []
        if persist_snapshot and raw_items:
            ok, new_snapshot, reason, blocking = verify_complete_1x2_odds(odds_by_book)
            if ok:
                row.odds_snapshot_json = attach_refresh_odds_meta(new_snapshot)
                clear_negative_odds_cache(row)
                row.odds_checked_at = _utcnow()
                db.commit()
                db.refresh(row)
            else:
                warnings.append(reason or "snapshot_not_persisted")
                warnings.extend(blocking)
    else:
        snap = row.odds_snapshot_json or {}
        raw_map = snap.get("raw_by_bookmaker_id") or {}
        raw_items = raw_map.get(str(_BETFAIR_ID)) or raw_map.get(_BETFAIR_ID) or []
        if not raw_items:
            warnings.append("snapshot_betfair_raw_mancante_usa_force_true")

    markets, raw_payload = parse_all_betfair_markets(
        list(raw_items) if isinstance(raw_items, list) else [],
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
    )

    meta = read_odds_meta(row.odds_snapshot_json)

    return {
        "status": "ok",
        "fixture": {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": int(row.provider_fixture_id),
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        },
        "bookmaker": bookmaker_meta_block(
            meta,
            provider_bookmaker_id=_BETFAIR_ID,
            name=CECCHINO_BOOKMAKER["name"],
        ),
        "odds_fetched_at": meta.get("odds_fetched_at"),
        "last_betfair_refresh_at": meta.get("last_betfair_refresh_at"),
        "is_cached": meta.get("is_cached"),
        "api_calls_used": api_calls_used,
        "markets": markets,
        "raw_payload": raw_payload,
        "manual_comparison_note": _MANUAL_COMPARISON,
        "warnings": warnings,
    }


def refresh_betfair_odds_by_id(
    db: Session,
    today_fixture_id: int,
    *,
    force: bool = True,
    rebuild_kpi: bool = True,
) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    return refresh_betfair_odds_for_fixture(
        db,
        row,
        force=force,
        rebuild_kpi=rebuild_kpi,
    )


def get_betfair_markets_json_by_id(
    db: Session,
    today_fixture_id: int,
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    return build_betfair_markets_json(db, row, force=force)
