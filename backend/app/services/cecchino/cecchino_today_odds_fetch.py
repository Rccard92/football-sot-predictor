"""Fetch e cache quote bookmaker Cecchino Today."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CecchinoTodayFixture
from app.models.cecchino_today_fixture import PROVIDER_API_FOOTBALL
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_sync_service import SLEEP_BETWEEN_CALLS_S
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, SEL_AWAY, SEL_DRAW, SEL_HOME
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics

_WANTED_BOOK_IDS = {int(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _book_ids_complete(raw_by_book: dict[int, list[dict[str, Any]]]) -> bool:
    for bid in _WANTED_BOOK_IDS:
        raw = raw_by_book.get(bid)
        if not raw:
            return False
        rows, _ = parse_api_football_odds_response(raw, requested_markets=[MARKET_1X2])
        home = draw = away = None
        for r in rows:
            if r["normalized_market"] != MARKET_1X2:
                continue
            if r["selection_key"] == SEL_HOME:
                home = r["odds_value"]
            elif r["selection_key"] == SEL_DRAW:
                draw = r["odds_value"]
            elif r["selection_key"] == SEL_AWAY:
                away = r["odds_value"]
        if home is None or draw is None or away is None:
            return False
    return True


def load_cached_odds_for_fixture(
    db: Session,
    *,
    scan_date: date,
    provider_fixture_id: int,
) -> dict[int, list[dict[str, Any]]] | None:
    """Riusa odds_snapshot_json.raw_by_bookmaker_id se completo per la scan_date."""
    row = db.scalar(
        select(CecchinoTodayFixture).where(
            CecchinoTodayFixture.scan_date == scan_date,
            CecchinoTodayFixture.provider_source == PROVIDER_API_FOOTBALL,
            CecchinoTodayFixture.provider_fixture_id == int(provider_fixture_id),
        ),
    )
    if row is None or not row.odds_snapshot_json:
        return None
    raw_map = (row.odds_snapshot_json or {}).get("raw_by_bookmaker_id") or {}
    if not raw_map:
        return None
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    for bid in _WANTED_BOOK_IDS:
        raw = raw_map.get(str(bid)) or raw_map.get(bid)
        if raw:
            odds_by_book[bid] = list(raw) if isinstance(raw, list) else []
    if not _book_ids_complete(odds_by_book):
        return None
    return odds_by_book


def check_negative_odds_cache(
    db: Session,
    *,
    scan_date: date,
    provider_fixture_id: int,
    force_rescan: bool = False,
) -> tuple[bool, CecchinoTodayFixture | None, str | None]:
    if force_rescan:
        return False, None, None
    row = db.scalar(
        select(CecchinoTodayFixture).where(
            CecchinoTodayFixture.scan_date == scan_date,
            CecchinoTodayFixture.provider_source == PROVIDER_API_FOOTBALL,
            CecchinoTodayFixture.provider_fixture_id == int(provider_fixture_id),
        ),
    )
    if row is None or row.negative_cache_until is None:
        return False, row, None
    until = row.negative_cache_until
    if not isinstance(until, datetime):
        return False, row, None
    if until > _utcnow():
        return True, row, row.odds_check_status
    return False, row, None


def write_negative_odds_cache(
    db: Session,
    row: CecchinoTodayFixture | None,
    *,
    scan_date: date,
    provider_fixture_id: int,
    odds_check_status: str,
) -> None:
    settings = get_settings()
    until = _utcnow() + timedelta(hours=int(settings.cecchino_odds_negative_cache_hours))
    if row is None:
        row = db.scalar(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date == scan_date,
                CecchinoTodayFixture.provider_source == PROVIDER_API_FOOTBALL,
                CecchinoTodayFixture.provider_fixture_id == int(provider_fixture_id),
            ),
        )
    if row is None:
        return
    row.odds_check_status = odds_check_status
    row.odds_checked_at = _utcnow()
    row.negative_cache_until = until
    db.flush()


def clear_negative_odds_cache(row: CecchinoTodayFixture | None) -> None:
    if row is None:
        return
    row.odds_check_status = "complete"
    row.odds_checked_at = _utcnow()
    row.negative_cache_until = None


def _extract_odds_by_book_from_response(
    raw_items: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """Estrae payload per-book da response API odds?fixture=X."""
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    for item in raw_items:
        for bm in item.get("bookmakers") or []:
            if not isinstance(bm, dict):
                continue
            bid_raw = bm.get("id")
            if bid_raw is None:
                continue
            bid = int(bid_raw)
            if bid not in _WANTED_BOOK_IDS:
                continue
            odds_by_book[bid] = [{"bookmakers": [bm]}]
    return odds_by_book


def _fetch_per_bookmaker(
    client: ApiFootballClient,
    api_fixture_id: int,
    *,
    metrics: ScanRunMetrics | None,
    only_bids: set[int] | None = None,
) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    targets = [int(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS]
    if only_bids is not None:
        targets = [bid for bid in targets if bid in only_bids]
    for idx, bid in enumerate(targets):
        if idx > 0:
            time.sleep(SLEEP_BETWEEN_CALLS_S)
        name = next((b["name"] for b in CECCHINO_BOOKMAKERS if int(b["provider_bookmaker_id"]) == bid), str(bid))
        try:
            odds_by_book[bid] = client.get_fixture_odds(api_fixture_id, bid)
            if metrics is not None:
                metrics.api_calls["odds"] = metrics.api_calls.get("odds", 0) + 1
                metrics.sync_api_calls_total()
        except ApiFootballError as exc:
            warnings.append(f"fixture {api_fixture_id} {name}: {exc}")
            odds_by_book[bid] = []
    return odds_by_book, warnings


def fetch_fixture_odds_for_cecchino_bookmakers(
    client: ApiFootballClient,
    api_fixture_id: int,
    *,
    db: Session | None = None,
    scan_date: date | None = None,
    force_rescan: bool = False,
    metrics: ScanRunMetrics | None = None,
) -> tuple[dict[int, list[dict[str, Any]]], list[str], str, bool]:
    """
    Fetch odds Bet365/Betfair/Pinnacle con cache e single-call API quando possibile.
    Ritorna (odds_by_book, warnings, strategy, negative_cache_hit).
    """
    settings = get_settings()

    if not force_rescan and db is not None and scan_date is not None:
        neg_hit, neg_row, neg_status = check_negative_odds_cache(
            db,
            scan_date=scan_date,
            provider_fixture_id=api_fixture_id,
            force_rescan=force_rescan,
        )
        if neg_hit:
            if metrics is not None:
                metrics.record_odds_strategy("negative_cache")
            return {}, [f"negative_cache:{neg_status or 'odds_incomplete'}"], "negative_cache", True

        cached = load_cached_odds_for_fixture(db, scan_date=scan_date, provider_fixture_id=api_fixture_id)
        if cached is not None:
            if metrics is not None:
                metrics.record_odds_strategy("cached")
            if neg_row is not None:
                clear_negative_odds_cache(neg_row)
            return cached, [], "cached", False

    warnings: list[str] = []
    try:
        raw_items = client.get_fixture_odds_by_fixture(api_fixture_id)
        if metrics is not None:
            metrics.api_calls["odds"] = metrics.api_calls.get("odds", 0) + 1
            metrics.sync_api_calls_total()
    except ApiFootballError as exc:
        warnings.append(f"fixture {api_fixture_id} odds single-call: {exc}")
        raw_items = []

    odds_by_book = _extract_odds_by_book_from_response(raw_items) if raw_items else {}

    if _book_ids_complete(odds_by_book):
        if metrics is not None:
            metrics.record_odds_strategy("fixture_single_call")
        if db is not None and scan_date is not None:
            _, neg_row, _ = check_negative_odds_cache(
                db,
                scan_date=scan_date,
                provider_fixture_id=api_fixture_id,
                force_rescan=True,
            )
            clear_negative_odds_cache(neg_row)
        return odds_by_book, warnings, "fixture_single_call", False

    missing = _WANTED_BOOK_IDS - set(odds_by_book.keys())
    incomplete = not _book_ids_complete(odds_by_book) if odds_by_book else True

    if not settings.cecchino_odds_bookmaker_fallback:
        if db is not None and scan_date is not None:
            write_negative_odds_cache(
                db,
                None,
                scan_date=scan_date,
                provider_fixture_id=api_fixture_id,
                odds_check_status="odds_incomplete_single_call",
            )
        return odds_by_book, warnings + ["odds_incomplete_single_call"], "odds_incomplete_single_call", False

    if raw_items and (missing or incomplete):
        fallback_bids = missing if missing else _WANTED_BOOK_IDS
        fb_odds, fb_warn = _fetch_per_bookmaker(
            client,
            api_fixture_id,
            metrics=metrics,
            only_bids=fallback_bids if missing else _WANTED_BOOK_IDS,
        )
        warnings.extend(fb_warn)
        for bid, payload in fb_odds.items():
            if payload:
                odds_by_book[bid] = payload
        strategy = "fixture_single_call_with_bookmaker_fallback"
        if metrics is not None:
            metrics.record_odds_strategy(strategy)
        return odds_by_book, warnings, strategy, False

    if not raw_items or not odds_by_book:
        odds_by_book, fb_warn = _fetch_per_bookmaker(client, api_fixture_id, metrics=metrics)
        warnings.extend(fb_warn)
        if metrics is not None:
            metrics.record_odds_strategy("bookmaker_per_fixture")
        return odds_by_book, warnings, "bookmaker_per_fixture", False

    if metrics is not None:
        metrics.record_odds_strategy("fixture_single_call_with_bookmaker_fallback")
    return odds_by_book, warnings, "fixture_single_call_with_bookmaker_fallback", False
