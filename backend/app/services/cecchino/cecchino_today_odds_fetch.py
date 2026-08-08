"""Fetch e cache quote Book canonico Cecchino Today (Betfair primary → Bet365 fallback)."""

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
from app.services.cecchino.cecchino_canonical_book_payload import build_single_bookmaker_payload
from app.services.cecchino.cecchino_canonical_book_resolver import (
    CANONICAL_BOOK_SELECTION_KEYS,
    GATE_1X2_KEYS,
    resolve_canonical_markets,
    selection_odd_from_markets,
)
from app.services.cecchino.cecchino_bookmaker_sync_service import SLEEP_BETWEEN_CALLS_S
from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOK_POLICY_VERSION,
    CECCHINO_CANONICAL_BOOKMAKER_IDS,
    CECCHINO_FALLBACK_BOOKMAKER,
    CECCHINO_PRIMARY_BOOKMAKER,
)
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics

_WANTED_BOOK_IDS = set(CECCHINO_CANONICAL_BOOKMAKER_IDS)
_BETFAIR_ID = int(CECCHINO_PRIMARY_BOOKMAKER["provider_bookmaker_id"])
_BETFAIR_NAME = str(CECCHINO_PRIMARY_BOOKMAKER["name"])
_BET365_ID = int(CECCHINO_FALLBACK_BOOKMAKER["provider_bookmaker_id"])
_BET365_NAME = str(CECCHINO_FALLBACK_BOOKMAKER["name"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_resolved(
    odds_by_book: dict[int, list[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    primary = build_single_bookmaker_payload(
        odds_by_book.get(_BETFAIR_ID) or [],
        CECCHINO_PRIMARY_BOOKMAKER,
    )
    fallback = build_single_bookmaker_payload(
        odds_by_book.get(_BET365_ID) or [],
        CECCHINO_FALLBACK_BOOKMAKER,
    )
    markets, provenance, stats = resolve_canonical_markets(
        primary_markets=primary.get("markets"),
        primary_provenance=primary.get("provenance_by_selection"),
        fallback_markets=fallback.get("markets"),
        fallback_provenance=fallback.get("provenance_by_selection"),
    )
    return markets, provenance, stats


def _canonical_1x2_complete(odds_by_book: dict[int, list[dict[str, Any]]]) -> bool:
    markets, _, _ = _build_resolved(odds_by_book)
    return all(selection_odd_from_markets(markets, sk) is not None for sk in GATE_1X2_KEYS)


def _betfair_markets(
    odds_by_book: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    primary = build_single_bookmaker_payload(
        odds_by_book.get(_BETFAIR_ID) or [],
        CECCHINO_PRIMARY_BOOKMAKER,
    )
    return primary.get("markets") or {}


def _missing_betfair_1x2_selections(
    odds_by_book: dict[int, list[dict[str, Any]]],
) -> list[str]:
    """HOME/DRAW/AWAY mancanti sul solo raw Betfair (Phase A gate)."""
    markets = _betfair_markets(odds_by_book)
    return [
        sk
        for sk in GATE_1X2_KEYS
        if selection_odd_from_markets(markets, sk) is None
    ]


def _betfair_1x2_complete(odds_by_book: dict[int, list[dict[str, Any]]]) -> bool:
    return not _missing_betfair_1x2_selections(odds_by_book)


def _missing_betfair_canonical_selections(
    odds_by_book: dict[int, list[dict[str, Any]]],
) -> list[str]:
    """Selection canoniche mancanti sul solo raw Betfair (prima di Bet365)."""
    markets = _betfair_markets(odds_by_book)
    return [
        sk
        for sk in CANONICAL_BOOK_SELECTION_KEYS
        if selection_odd_from_markets(markets, sk) is None
    ]


def _betfair_covers_all_targets(odds_by_book: dict[int, list[dict[str, Any]]]) -> bool:
    """True se Betfair da solo copre tutte le selection KPI target (nessun bisogno Bet365)."""
    return not _missing_betfair_canonical_selections(odds_by_book)


def _missing_selections_after_resolve(
    odds_by_book: dict[int, list[dict[str, Any]]],
) -> list[str]:
    markets, _, _ = _build_resolved(odds_by_book)
    return [
        sk
        for sk in CANONICAL_BOOK_SELECTION_KEYS
        if selection_odd_from_markets(markets, sk) is None
    ]


def _book_ids_complete(raw_by_book: dict[int, list[dict[str, Any]]]) -> bool:
    """Compat: completo se 1X2 canonico risolvibile (Betfair → Bet365)."""
    return _canonical_1x2_complete(raw_by_book)


def load_cached_odds_for_fixture(
    db: Session,
    *,
    scan_date: date,
    provider_fixture_id: int,
) -> dict[int, list[dict[str, Any]]] | None:
    """
    Riusa odds_snapshot_json.raw_by_bookmaker_id solo se:
    - book_policy_version corrente
    - 1X2 canonico ricostruibile
    Snapshot legacy Betfair-only senza policy version NON bloccano il refetch.
    """
    row = db.scalar(
        select(CecchinoTodayFixture).where(
            CecchinoTodayFixture.scan_date == scan_date,
            CecchinoTodayFixture.provider_source == PROVIDER_API_FOOTBALL,
            CecchinoTodayFixture.provider_fixture_id == int(provider_fixture_id),
        ),
    )
    if row is None or not row.odds_snapshot_json:
        return None
    snap = row.odds_snapshot_json or {}
    meta = read_odds_meta(snap)
    policy = snap.get("book_policy_version") or meta.get("book_policy_version")
    if policy != CECCHINO_BOOK_POLICY_VERSION:
        return None

    raw_map = snap.get("raw_by_bookmaker_id") or {}
    if not raw_map:
        return None
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    for bid in _WANTED_BOOK_IDS:
        raw = raw_map.get(str(bid)) or raw_map.get(bid)
        if raw:
            odds_by_book[bid] = list(raw) if isinstance(raw, list) else []
    if not _canonical_1x2_complete(odds_by_book):
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
    """Estrae payload Betfair + Bet365 da response API odds?fixture=X."""
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


def _fetch_bookmaker_only(
    client: ApiFootballClient,
    api_fixture_id: int,
    bookmaker_id: int,
    bookmaker_name: str,
    *,
    metrics: ScanRunMetrics | None,
) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    try:
        odds_by_book[bookmaker_id] = client.get_fixture_odds(api_fixture_id, bookmaker_id)
        if metrics is not None:
            metrics.api_calls["odds"] = metrics.api_calls.get("odds", 0) + 1
            metrics.sync_api_calls_total()
    except ApiFootballError as exc:
        warnings.append(f"fixture {api_fixture_id} {bookmaker_name}: {exc}")
        odds_by_book[bookmaker_id] = []
    return odds_by_book, warnings


def _fetch_betfair_only(
    client: ApiFootballClient,
    api_fixture_id: int,
    *,
    metrics: ScanRunMetrics | None,
) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
    """Legacy alias: fetch Betfair bookmaker-specific."""
    return _fetch_bookmaker_only(
        client,
        api_fixture_id,
        _BETFAIR_ID,
        _BETFAIR_NAME,
        metrics=metrics,
    )


def _fetch_bet365_only(
    client: ApiFootballClient,
    api_fixture_id: int,
    *,
    metrics: ScanRunMetrics | None,
) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
    return _fetch_bookmaker_only(
        client,
        api_fixture_id,
        _BET365_ID,
        _BET365_NAME,
        metrics=metrics,
    )


def _record_resolution_metrics(
    metrics: ScanRunMetrics | None,
    odds_by_book: dict[int, list[dict[str, Any]]],
    *,
    count_fixture: bool = False,
) -> None:
    """Accumula il RISULTATO FINALE della risoluzione Book di una fixture.

    Conta solo selection canoniche finali (non tentativi/recovery intermedi).
    Per il path Today scan: chiamare UNA sola volta in Phase B (post-stats).
    """
    if metrics is None:
        return
    _, _, stats = _build_resolved(odds_by_book)
    metrics.betfair_primary_selection_count += int(
        stats.get("betfair_primary_selection_count") or 0,
    )
    metrics.bet365_fallback_selection_count += int(
        stats.get("bet365_fallback_selection_count") or 0,
    )
    metrics.book_still_missing_after_fallback += int(
        stats.get("book_still_missing_after_fallback") or 0,
    )
    if stats.get("betfair_primary_used"):
        metrics.betfair_primary_used += 1
    if stats.get("bet365_fallback_used"):
        metrics.bet365_fallback_used += 1
        metrics.bet365_fallback_fixture_count += 1
    if count_fixture:
        metrics.book_coverage_fixture_count += 1


def fetch_fixture_odds_for_cecchino_1x2_gate(
    client: ApiFootballClient,
    api_fixture_id: int,
    *,
    db: Session | None = None,
    scan_date: date | None = None,
    force_rescan: bool = False,
    metrics: ScanRunMetrics | None = None,
) -> tuple[dict[int, list[dict[str, Any]]], list[str], str, bool]:
    """Phase A — gate Book 1X2 economico per Cecchino Today scan.

    Preferisce UNA call Betfair bookmaker-specific; Bet365 solo se 1X2 BF incompleto.
    Non registra book coverage (fase intermedia): le metriche full Book vanno in Phase B.
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
    odds_by_book: dict[int, list[dict[str, Any]]] = {}
    did_bet365 = False

    # Primary Today path: Betfair bookmaker-specific (no fixture-wide).
    bf_odds, bf_warn = _fetch_betfair_only(client, api_fixture_id, metrics=metrics)
    warnings.extend(bf_warn)
    for bid, payload in bf_odds.items():
        if payload:
            odds_by_book[bid] = payload

    if settings.cecchino_odds_bookmaker_fallback and _missing_betfair_1x2_selections(odds_by_book):
        time.sleep(SLEEP_BETWEEN_CALLS_S)
        b365_odds, b365_warn = _fetch_bet365_only(client, api_fixture_id, metrics=metrics)
        warnings.extend(b365_warn)
        for bid, payload in b365_odds.items():
            if payload:
                odds_by_book[bid] = payload
                did_bet365 = True

    if _canonical_1x2_complete(odds_by_book):
        if db is not None and scan_date is not None:
            _, neg_row, _ = check_negative_odds_cache(
                db,
                scan_date=scan_date,
                provider_fixture_id=api_fixture_id,
                force_rescan=True,
            )
            clear_negative_odds_cache(neg_row)

        if did_bet365:
            strategy = "betfair_1x2_with_bet365_fallback"
        else:
            strategy = "betfair_1x2"
        if metrics is not None:
            metrics.record_odds_strategy(strategy)
        return odds_by_book, warnings, strategy, False

    if not settings.cecchino_odds_bookmaker_fallback:
        if db is not None and scan_date is not None:
            write_negative_odds_cache(
                db,
                None,
                scan_date=scan_date,
                provider_fixture_id=api_fixture_id,
                odds_check_status="odds_incomplete_1x2_gate",
            )
        if metrics is not None:
            metrics.record_odds_strategy("odds_incomplete_1x2_gate")
        return odds_by_book, warnings + ["odds_incomplete_1x2_gate"], "odds_incomplete_1x2_gate", False

    strategy = "betfair_1x2_with_bet365_fallback" if did_bet365 else "betfair_1x2"
    if metrics is not None:
        metrics.record_odds_strategy(strategy)
    return odds_by_book, warnings, strategy, False


def enrich_fixture_odds_full_canonical(
    client: ApiFootballClient,
    api_fixture_id: int,
    odds_by_book: dict[int, list[dict[str, Any]]],
    *,
    metrics: ScanRunMetrics | None = None,
) -> tuple[dict[int, list[dict[str, Any]]], list[str], bool]:
    """Phase B — full Book enrichment SOLO post stats gate.

    Riusa raw Betfair (e Bet365 se già presente da Phase A).
    Al massimo UNA call Bet365 se mancano selection canoniche su Betfair
    e Bet365 non è già stato caricato. Non richiama Betfair.
    Registra book coverage una sola volta (fixture stats-qualified).
    Ritorna (odds_by_book, warnings, did_bet365_call).
    """
    settings = get_settings()
    warnings: list[str] = []
    did_bet365_call = False

    missing_bf = _missing_betfair_canonical_selections(odds_by_book)
    if missing_bf and settings.cecchino_odds_bookmaker_fallback:
        has_b365 = bool(odds_by_book.get(_BET365_ID))
        if not has_b365:
            time.sleep(SLEEP_BETWEEN_CALLS_S)
            b365_odds, b365_warn = _fetch_bet365_only(client, api_fixture_id, metrics=metrics)
            warnings.extend(b365_warn)
            for bid, payload in b365_odds.items():
                if payload:
                    odds_by_book[bid] = payload
                    did_bet365_call = True
        # Se B365 già presente da Phase A: riuso, nessuna seconda call.
        # Resolve selection-by-selection avviene a valle (sync/KPI/payload).

    if metrics is not None:
        _record_resolution_metrics(metrics, odds_by_book, count_fixture=True)

    return odds_by_book, warnings, did_bet365_call


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
    Fetch odds Book canonico (Betfair + Bet365) con cache e single-call API.
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
                _record_resolution_metrics(metrics, cached)
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

    # Recovery Betfair-specific se manca QUALSIASI selection canonica su Betfair
    # (non solo 1X2): al massimo UNA call bookmaker-specific per fixture.
    did_betfair_recovery = False
    did_bet365_specific = False

    if (
        settings.cecchino_odds_bookmaker_fallback
        and _missing_betfair_canonical_selections(odds_by_book)
        and not did_betfair_recovery
    ):
        time.sleep(SLEEP_BETWEEN_CALLS_S)
        fb_odds, fb_warn = _fetch_betfair_only(client, api_fixture_id, metrics=metrics)
        warnings.extend(fb_warn)
        for bid, payload in fb_odds.items():
            if payload:
                odds_by_book[bid] = payload
        did_betfair_recovery = True

    # Resolve in-memory con Bet365 già presente nel fixture-wide; solo dopo,
    # se restano selection mancanti, al massimo UNA call Bet365-specific.
    if (
        settings.cecchino_odds_bookmaker_fallback
        and not _betfair_covers_all_targets(odds_by_book)
        and _missing_selections_after_resolve(odds_by_book)
        and not did_bet365_specific
    ):
        time.sleep(SLEEP_BETWEEN_CALLS_S)
        b365_odds, b365_warn = _fetch_bet365_only(client, api_fixture_id, metrics=metrics)
        warnings.extend(b365_warn)
        for bid, payload in b365_odds.items():
            if payload:
                odds_by_book[bid] = payload
                did_bet365_specific = True

    if _canonical_1x2_complete(odds_by_book):
        if db is not None and scan_date is not None:
            _, neg_row, _ = check_negative_odds_cache(
                db,
                scan_date=scan_date,
                provider_fixture_id=api_fixture_id,
                force_rescan=True,
            )
            clear_negative_odds_cache(neg_row)

        if did_bet365_specific:
            strategy = "fixture_single_call_with_bet365_fallback"
        elif did_betfair_recovery:
            strategy = "fixture_single_call_with_bookmaker_fallback"
        elif raw_items:
            strategy = "fixture_single_call"
        else:
            strategy = "bookmaker_per_fixture"

        if metrics is not None:
            metrics.record_odds_strategy(strategy)
            _record_resolution_metrics(metrics, odds_by_book)
        return odds_by_book, warnings, strategy, False

    # Canonical 1X2 ancora incompleto
    if not settings.cecchino_odds_bookmaker_fallback:
        if db is not None and scan_date is not None:
            write_negative_odds_cache(
                db,
                None,
                scan_date=scan_date,
                provider_fixture_id=api_fixture_id,
                odds_check_status="odds_incomplete_single_call",
            )
        if metrics is not None:
            metrics.record_odds_strategy("odds_incomplete_single_call")
            _record_resolution_metrics(metrics, odds_by_book)
        return odds_by_book, warnings + ["odds_incomplete_single_call"], "odds_incomplete_single_call", False

    # Ultimo tentativo: response vuota e recovery non ancora eseguita
    if not odds_by_book and not did_betfair_recovery:
        odds_by_book, fb_warn = _fetch_betfair_only(client, api_fixture_id, metrics=metrics)
        warnings.extend(fb_warn)
        did_betfair_recovery = True
        if _missing_selections_after_resolve(odds_by_book) and not did_bet365_specific:
            time.sleep(SLEEP_BETWEEN_CALLS_S)
            b365_odds, b365_warn = _fetch_bet365_only(client, api_fixture_id, metrics=metrics)
            warnings.extend(b365_warn)
            for bid, payload in b365_odds.items():
                if payload:
                    odds_by_book[bid] = payload
                    did_bet365_specific = True
        strategy = "bookmaker_per_fixture"
        if metrics is not None:
            metrics.record_odds_strategy(strategy)
            _record_resolution_metrics(metrics, odds_by_book)
        return odds_by_book, warnings, strategy, False

    strategy = (
        "fixture_single_call_with_bet365_fallback"
        if did_bet365_specific
        else "fixture_single_call_with_bookmaker_fallback"
    )
    if metrics is not None:
        metrics.record_odds_strategy(strategy)
        _record_resolution_metrics(metrics, odds_by_book)
    return odds_by_book, warnings, strategy, False
