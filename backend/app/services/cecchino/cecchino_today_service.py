"""Orchestrazione Cecchino Today — discovery manuale giornaliera."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Competition, Fixture
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_ERROR,
    ELIGIBILITY_EXCLUDED_CUP,
    ELIGIBILITY_EXCLUDED_FRIENDLY,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_MAPPING,
    ELIGIBILITY_EXCLUDED_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_STARTED,
    ELIGIBILITY_EXCLUDED_WOMEN,
    ELIGIBILITY_EXCLUDED_YOUTH,
    PROVIDER_API_FOOTBALL,
)
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.bookmakers.fixture_bookmaker_odds_repository import upsert_selection_odds
from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_sync_service import SLEEP_BETWEEN_CALLS_S
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS, PROVIDER_API_FOOTBALL as BM_PROVIDER
from app.services.cecchino.cecchino_fixture_history import build_fixture_contexts
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2
from app.services.cecchino.cecchino_service import (
    build_calculation_input_for_fixture,
    calculate_and_persist_for_fixture,
)
from app.services.cecchino.cecchino_today_bookmaker_gate import verify_complete_1x2_odds
from app.services.cecchino.cecchino_today_bootstrap import ensure_competition_and_history
from app.services.cecchino.cecchino_today_competition_filter import is_cecchino_allowed_competition
from app.services.cecchino.cecchino_today_constants import (
    CECCHINO_TODAY_VERSION,
    DEFAULT_TODAY_TIMEZONE,
)
from app.services.cecchino.cecchino_today_fixture_filter import is_fixture_not_started
from app.services.cecchino.cecchino_today_stats_gate import check_cecchino_today_stats_eligible

logger = logging.getLogger(__name__)

_BOOK_REASON_TO_STATUS = {
    "missing_bookmaker": ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    "missing_1x2_market": ELIGIBILITY_EXCLUDED_MISSING_1X2,
}


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
    """Persiste quote 1X2 parsed in fixture_bookmaker_odds."""
    saved = 0
    now = datetime.now(timezone.utc)
    for bm in CECCHINO_BOOKMAKERS:
        bid = int(bm["provider_bookmaker_id"])
        raw = odds_by_bookmaker.get(bid) or []
        parsed, _ = parse_api_football_odds_response(raw, requested_markets=[MARKET_1X2])
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
    db.flush()
    return row


def build_cecchino_today_report(
    *,
    scan_date: date,
    total: int,
    by_status: dict[str, int],
    warnings: list[str],
) -> dict[str, Any]:
    eligible = by_status.get(ELIGIBILITY_ELIGIBLE, 0)
    excluded = {k: v for k, v in by_status.items() if k != ELIGIBILITY_ELIGIBLE}
    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "scan_date": scan_date.isoformat(),
        "total_discovered": total,
        "eligible": eligible,
        "excluded": excluded,
        "excluded_total": sum(excluded.values()),
        "warnings": warnings,
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
                comp, local_fx, boot_warnings = ensure_competition_and_history(
                    db,
                    api_item=item,
                    client=af_client,
                )
                row_warnings.extend(boot_warnings)
            except Exception as exc:
                logger.exception("Bootstrap Cecchino Today failed fixture=%s", api_fid)
                _upsert_today_snapshot(
                    db,
                    scan_date=resolved_date,
                    api_item=item,
                    eligibility_status=ELIGIBILITY_EXCLUDED_MAPPING,
                    eligibility_reason=str(exc)[:500],
                    bookmaker_status="ok",
                    odds_snapshot=odds_snapshot,
                    warnings=row_warnings + [f"bootstrap_error:{exc!s}"[:200]],
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
        cec_status = calc.get("calculation_status") or calc.get("status")
        is_eligible = calc.get("status") == "ok" and cec_status not in ("error",)

        if is_eligible:
            _upsert_today_snapshot(
                db,
                scan_date=resolved_date,
                api_item=item,
                eligibility_status=ELIGIBILITY_ELIGIBLE,
                local_fixture_id=int(local_fx.id),
                competition_id=int(comp.id),
                bookmaker_status="ok",
                stats_status="ok",
                cecchino_status=str(cec_status),
                odds_snapshot=odds_snapshot,
                stats_snapshot=stats_snapshot,
                cecchino_output=cecchino_output,
                kpi_panel=kpi_panel,
                warnings=row_warnings + list(calc.get("warnings") or []),
            )
            by_status[ELIGIBILITY_ELIGIBLE] += 1
        else:
            _upsert_today_snapshot(
                db,
                scan_date=resolved_date,
                api_item=item,
                eligibility_status=ELIGIBILITY_ERROR,
                eligibility_reason=calc.get("message") or calc.get("code"),
                local_fixture_id=int(local_fx.id),
                competition_id=int(comp.id),
                bookmaker_status="ok",
                stats_status="ok",
                cecchino_status=str(cec_status),
                odds_snapshot=odds_snapshot,
                stats_snapshot=stats_snapshot,
                cecchino_output=cecchino_output,
                kpi_panel=kpi_panel,
                warnings=row_warnings + list(calc.get("warnings") or []),
            )
            by_status[ELIGIBILITY_ERROR] += 1

    db.commit()
    warnings.extend([w for w in warnings if w])
    report = build_cecchino_today_report(
        scan_date=resolved_date,
        total=len(raw_items),
        by_status=dict(by_status),
        warnings=warnings,
    )
    report["fixtures_processed"] = len(raw_items)
    return report


def list_eligible_today(
    db: Session,
    *,
    scan_date: date | None = None,
    country: str | None = None,
    league: str | None = None,
    timezone: str = DEFAULT_TODAY_TIMEZONE,
) -> dict[str, Any]:
    resolved = resolve_scan_date(scan_date, timezone)
    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date == resolved,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    rows = list(db.scalars(q.order_by(CecchinoTodayFixture.kickoff.asc())).all())

    if country:
        c_low = country.strip().lower()
        rows = [r for r in rows if (r.country_name or "").lower().find(c_low) >= 0]
    if league:
        l_low = league.strip().lower()
        rows = [r for r in rows if (r.league_name or "").lower().find(l_low) >= 0]

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        cname = r.country_name or "Unknown"
        lname = r.league_name or "Unknown"
        grouped[cname][lname].append(_row_list_item(r))

    countries = []
    for cname in sorted(grouped.keys()):
        leagues = []
        for lname in sorted(grouped[cname].keys()):
            leagues.append({"league_name": lname, "fixtures": grouped[cname][lname]})
        countries.append({"country_name": cname, "leagues": leagues})

    return {
        "status": "ok",
        "version": CECCHINO_TODAY_VERSION,
        "scan_date": resolved.isoformat(),
        "total": len(rows),
        "countries": countries,
    }


def _row_list_item(row: CecchinoTodayFixture) -> dict[str, Any]:
    odds = row.odds_snapshot_json or {}
    bm = odds.get("bookmakers") or {}
    return {
        "id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
        "competition_id": int(row.competition_id) if row.competition_id else None,
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "bookmaker_status": row.bookmaker_status,
        "stats_status": row.stats_status,
        "cecchino_status": row.cecchino_status,
        "bookmakers": {
            name: "OK" if name in bm else "MISSING"
            for name in ("Bet365", "Betfair", "Pinnacle")
        },
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
        "fixtures": [
            {
                "id": int(r.id),
                "provider_fixture_id": int(r.provider_fixture_id),
                "home_team_name": r.home_team_name,
                "away_team_name": r.away_team_name,
                "league_name": r.league_name,
                "country_name": r.country_name,
                "kickoff": r.kickoff.isoformat() if r.kickoff else None,
                "eligibility_status": r.eligibility_status,
                "eligibility_reason": r.eligibility_reason,
            }
            for r in rows
        ],
    }
