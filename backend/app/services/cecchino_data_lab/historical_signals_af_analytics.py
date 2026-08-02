"""Analytics autonoma Segnali A–F (STEP 4B) — resource-safe, read-only.

Non modifica formule A–F. Non carica tutti gli snapshot ORM del run senza filtri.
Riusa helper puri da historical_signal_export.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.cecchino_lab_historical_market_result import (
    CecchinoLabHistoricalMarketResult,
)
from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino.cecchino_constants import CECCHINO_WEIGHT_MODEL_KEYS
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_scan_service import run_to_dict
from app.services.cecchino_data_lab.historical_signal_export import (
    CURRENT_MODEL_KEY,
    SIGNAL_EXPORT_SCHEMA_VERSION,
    build_signal_models_summary,
    collect_all_opportunities,
    public_opportunity_row,
)

HISTORICAL_SIGNALS_AF_ANALYTICS_VERSION = "cecchino_lab_historical_signals_af_v1"
ANALYTICS_CACHE_TTL_S = 300
CACHE_MAX_ENTRIES = 64
CACHE_KIND_SUMMARY = "summary"

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def clear_historical_signals_af_cache() -> None:
    """Solo per test."""
    with _cache_lock:
        _cache.clear()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _cache_get(key: str) -> Any | None:
    now = time.monotonic()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        expires, value = item
        if expires < now:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any, ttl: float = ANALYTICS_CACHE_TTL_S) -> None:
    now = time.monotonic()
    with _cache_lock:
        if len(_cache) >= CACHE_MAX_ENTRIES:
            expired = [k for k, (exp, _) in _cache.items() if exp < now]
            for k in expired:
                _cache.pop(k, None)
            while len(_cache) >= CACHE_MAX_ENTRIES:
                oldest = next(iter(_cache))
                _cache.pop(oldest, None)
        _cache[key] = (now + ttl, value)


def _cache_key(*, run_id: int, kind: str, completed_at: Any, filters: dict[str, Any]) -> str:
    return "|".join(
        [
            str(int(run_id)),
            kind,
            HISTORICAL_SIGNALS_AF_ANALYTICS_VERSION,
            _iso(completed_at) or "",
            json.dumps(filters, sort_keys=True, default=str),
        ]
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_signals_af_filters(**kwargs: Any) -> dict[str, Any]:
    quote_type = str(kwargs.get("quote_type") or "real").strip().lower()
    if quote_type not in ("real", "derived", "all"):
        quote_type = "real"

    model_key_raw = kwargs.get("model_key")
    model_key: str | None = None
    if model_key_raw not in (None, "", "all", "tutti", "ALL", "TUTTI"):
        mk = str(model_key_raw).strip().upper()
        if mk not in CECCHINO_WEIGHT_MODEL_KEYS:
            raise CecchinoLabImportError(
                "invalid_model_key",
                "model_key deve essere A–F oppure tutti.",
                status_code=400,
                details={"value": model_key_raw},
            )
        model_key = mk

    min_consensus = kwargs.get("minimum_consensus_models")
    minimum_consensus_models: int | None = None
    if min_consensus not in (None, ""):
        try:
            minimum_consensus_models = int(min_consensus)
        except (TypeError, ValueError) as exc:
            raise CecchinoLabImportError(
                "invalid_minimum_consensus_models",
                "minimum_consensus_models deve essere un intero >= 1.",
                status_code=400,
                details={"value": min_consensus},
            ) from exc
        if minimum_consensus_models < 1:
            raise CecchinoLabImportError(
                "invalid_minimum_consensus_models",
                "minimum_consensus_models deve essere >= 1.",
                status_code=400,
                details={"value": minimum_consensus_models},
            )

    only_f_raw = kwargs.get("only_current_model_F")
    only_current_model_F = False
    if only_f_raw in (True, "true", "1", "yes", "on"):
        only_current_model_F = True
    elif only_f_raw in (False, None, "", "false", "0", "no", "off"):
        only_current_model_F = False
    else:
        only_current_model_F = bool(only_f_raw)

    return {
        "competition": (kwargs.get("competition") or None),
        "date_from": (kwargs.get("date_from") or None),
        "date_to": (kwargs.get("date_to") or None),
        "model_key": model_key,
        "market_key": (kwargs.get("market_key") or None),
        "quote_type": quote_type,
        "minimum_consensus_models": minimum_consensus_models,
        "only_current_model_F": only_current_model_F,
    }


def _get_run(db: Session, run_id: int) -> CecchinoLabHistoricalScanRun:
    run = db.get(CecchinoLabHistoricalScanRun, int(run_id))
    if run is None:
        raise CecchinoLabImportError(
            "run_not_found",
            f"Run storico non trovato: {run_id}",
            status_code=404,
        )
    return run


def _run_block(run: CecchinoLabHistoricalScanRun | Any) -> dict[str, Any]:
    base: dict[str, Any] = {}
    try:
        base = run_to_dict(run)  # type: ignore[arg-type]
    except Exception:
        base = {
            "run_scope": getattr(run, "run_scope", None),
            "is_partial_run": getattr(run, "is_partial_run", None),
        }
    return {
        "run_id": int(getattr(run, "id")),
        "season_label": getattr(run, "season_label", None),
        "status": getattr(run, "status", None),
        "scope": base.get("run_scope") or "full",
        "is_partial_run": bool(base.get("is_partial_run"))
        if base.get("is_partial_run") is not None
        else None,
    }


def _load_filtered_snapshots(
    db: Session, run_id: int, filters: dict[str, Any]
) -> tuple[list[CecchinoLabHistoricalMatchSnapshot], int]:
    S = CecchinoLabHistoricalMatchSnapshot
    stmt = (
        select(S)
        .options(
            load_only(
                S.id,
                S.run_id,
                S.dataset_id,
                S.lab_match_id,
                S.competition_name,
                S.season_label,
                S.kickoff_at,
                S.home_team,
                S.away_team,
                S.chronological_order,
                S.historical_eligibility_status,
                S.signals_json,
                S.settlement_summary_json,
                S.result_json,
            )
        )
        .where(
            S.run_id == int(run_id),
            S.historical_eligibility_status == ELIGIBLE_CORE,
        )
        .order_by(S.kickoff_at.asc().nulls_last(), S.lab_match_id.asc())
    )
    if filters.get("competition"):
        stmt = stmt.where(S.competition_name == filters["competition"])
    rows = list(db.scalars(stmt).all())
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    if date_from is not None or date_to is not None:
        filtered: list[CecchinoLabHistoricalMatchSnapshot] = []
        for s in rows:
            if s.kickoff_at is None:
                continue
            d = s.kickoff_at.date() if isinstance(s.kickoff_at, datetime) else None
            if d is None:
                continue
            if date_from is not None and d < date_from:
                continue
            if date_to is not None and d > date_to:
                continue
            filtered.append(s)
        rows = filtered
    return rows, 1


def _load_markets_for_snapshots(
    db: Session, run_id: int, snapshot_ids: list[int]
) -> tuple[list[CecchinoLabHistoricalMarketResult], int]:
    if not snapshot_ids:
        return [], 0
    M = CecchinoLabHistoricalMarketResult
    # Chunk to avoid oversized IN clauses
    out: list[CecchinoLabHistoricalMarketResult] = []
    query_count = 0
    chunk_size = 500
    for i in range(0, len(snapshot_ids), chunk_size):
        chunk = snapshot_ids[i : i + chunk_size]
        rows = list(
            db.scalars(
                select(M)
                .options(
                    load_only(
                        M.id,
                        M.run_id,
                        M.match_snapshot_id,
                        M.lab_match_id,
                        M.market_key,
                        M.market_label,
                        M.rating,
                        M.is_real_book_quote,
                        M.is_derived_quote,
                        M.quota_book,
                        M.won,
                        M.profit_1u_real,
                        M.profit_1u_synthetic,
                        M.evaluation_status,
                        M.prob_cecchino,
                        M.quota_cecchino,
                        M.signal_active,
                    )
                )
                .where(
                    M.run_id == int(run_id),
                    M.match_snapshot_id.in_(chunk),
                )
            ).all()
        )
        out.extend(rows)
        query_count += 1
    return out, query_count


def _opp_passes_quote_type(opp: dict[str, Any], quote_type: str) -> bool:
    if quote_type == "all":
        return True
    if quote_type == "real":
        return bool(opp.get("is_real_book_quote"))
    if quote_type == "derived":
        return bool(opp.get("is_derived_quote"))
    return True


def filter_opportunities(
    opportunities: list[dict[str, Any]], filters: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    model_key = filters.get("model_key")
    market_key = filters.get("market_key")
    quote_type = filters.get("quote_type") or "real"
    min_consensus = filters.get("minimum_consensus_models")
    only_f = bool(filters.get("only_current_model_F"))

    for opp in opportunities:
        if only_f and str(opp.get("model_key") or "").upper() != CURRENT_MODEL_KEY:
            continue
        if model_key and str(opp.get("model_key") or "").upper() != model_key:
            continue
        if market_key and str(opp.get("market_key") or "") != str(market_key):
            continue
        if not _opp_passes_quote_type(opp, quote_type):
            continue
        if min_consensus is not None:
            consensus_n = int(opp.get("consensus_model_count") or len(opp.get("consensus_models") or []) or 0)
            if consensus_n < int(min_consensus):
                continue
        out.append(opp)
    return out


def _enrich_models_with_best_market(
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    models_out: list[dict[str, Any]] = []
    for m in summary.get("models") or []:
        mk_stats = [
            (row["market_key"], row)
            for row in summary.get("model_x_market") or []
            if row.get("model_key") == m["model_key"]
        ]
        mk_roi = [
            (mk, v)
            for mk, v in mk_stats
            if v.get("real_roi_pct") is not None
            and int(v.get("real_quote_count") or 0) >= 1
        ]
        market_best = (
            max(mk_roi, key=lambda x: float(x[1]["real_roi_pct"]))[0] if mk_roi else None
        )
        models_out.append({**m, "market_best": market_best, "market_worst": None})
    return models_out


def _by_market_payload(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return list(summary.get("model_x_market") or [])


def _collect_universe(
    db: Session, run_id: int, filters: dict[str, Any]
) -> tuple[list[dict[str, Any]], int, int]:
    """Ritorna (opportunities dopo filtri snapshot, query_count, snapshots_loaded)."""
    snaps, qc1 = _load_filtered_snapshots(db, int(run_id), filters)
    snap_ids = [int(s.id) for s in snaps]
    markets, qc2 = _load_markets_for_snapshots(db, int(run_id), snap_ids)
    opportunities = collect_all_opportunities(
        run_id=int(run_id),
        snapshots=snaps,
        markets=markets,
    )
    return opportunities, qc1 + qc2, len(snaps)


def get_signals_af_summary(
    db: Session, run_id: int, filters: dict[str, Any]
) -> dict[str, Any]:
    run = _get_run(db, int(run_id))
    cache_key = _cache_key(
        run_id=int(run_id),
        kind=CACHE_KIND_SUMMARY,
        completed_at=getattr(run, "completed_at", None),
        filters=filters,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    raw_opps, query_count, snaps_n = _collect_universe(db, int(run_id), filters)

    # Summary A–F: competition/date + quote/market/consensus (tutti i modelli)
    summary_filters = {
        **filters,
        "model_key": None,
        "only_current_model_F": False,
    }
    summary_opps = filter_opportunities(raw_opps, summary_filters)
    display_opps = filter_opportunities(raw_opps, filters)

    summary = build_signal_models_summary(summary_opps)
    models_out = _enrich_models_with_best_market(summary)

    unique_opp_count = len(summary_opps)
    active_cells = sum(int(o.get("active_cell_count") or 0) for o in summary_opps)

    concurrent_counts: dict[int, int] = defaultdict(int)
    for o in summary_opps:
        concurrent_counts[int(o.get("active_cell_count") or 0)] += 1

    real_n = sum(1 for o in summary_opps if o.get("is_real_book_quote"))
    derived_n = sum(1 for o in summary_opps if o.get("is_derived_quote"))

    payload = {
        "schema_version": HISTORICAL_SIGNALS_AF_ANALYTICS_VERSION,
        "signal_export_schema_version": SIGNAL_EXPORT_SCHEMA_VERSION,
        "generated_at": _utcnow().isoformat(),
        "run": _run_block(run),
        "filters": dict(filters),
        "current_model_key": CURRENT_MODEL_KEY,
        "performance_granularity": "signal_opportunity",
        "models": models_out,
        "by_market": _by_market_payload(summary),
        "model_overlap_matrix": summary.get("model_overlap_matrix") or [],
        "consensus_distribution": summary.get("consensus_distribution") or [],
        "signal_export_reconciliation": summary.get("signal_export_reconciliation"),
        "current_model_F_diagnostics": summary.get("current_model_F_diagnostics"),
        "unique_opportunities": unique_opp_count,
        "active_cells": active_cells,
        "filtered_opportunity_count": len(display_opps),
        "quote_buckets": {
            "real": real_n,
            "derived": derived_n,
            "note": "Real e synthetic restano separati; non sommati.",
        },
        "concurrent_active_signals": dict(sorted(concurrent_counts.items())),
        "note": (
            "Prestazioni su opportunità uniche (run+snapshot+modello+mercato). "
            "Le celle attive non sono scommesse indipendenti. "
            f"F = modello corrente ({CURRENT_MODEL_KEY}), non automaticamente il migliore."
        ),
        "resource_profile": {
            "strategy": "filtered_snapshot_load",
            "query_count": query_count,
            "snapshots_loaded": snaps_n,
            "opportunities_materialized": unique_opp_count,
            "full_orm_entities_loaded": False,
            "full_signals_json_returned": False,
        },
    }
    safe = _json_safe(payload)
    _cache_set(cache_key, safe)
    return safe


def _activation_public(opp: dict[str, Any]) -> dict[str, Any]:
    pub = public_opportunity_row(opp)
    cells = pub.get("active_cells") or pub.get("cells") or []
    return {
        "opportunity_id": pub.get("opportunity_id"),
        "snapshot_id": pub.get("snapshot_id") or pub.get("match_snapshot_id"),
        "lab_match_id": pub.get("lab_match_id"),
        "competition_name": pub.get("competition_name"),
        "kickoff_at": pub.get("kickoff_at"),
        "home_team": pub.get("home_team"),
        "away_team": pub.get("away_team"),
        "model_key": pub.get("model_key"),
        "market_key": pub.get("market_key"),
        "market_label": pub.get("market_label"),
        "active_cell_count": pub.get("active_cell_count"),
        "active_cells": cells if isinstance(cells, list) else [],
        "consensus_model_count": pub.get("consensus_model_count"),
        "consensus_models": pub.get("consensus_models"),
        "quota_book": pub.get("quota_book"),
        "is_real_book_quote": pub.get("is_real_book_quote"),
        "is_derived_quote": pub.get("is_derived_quote"),
        "quote_type": (
            "real"
            if pub.get("is_real_book_quote")
            else ("derived" if pub.get("is_derived_quote") else None)
        ),
        "won": pub.get("won"),
        "profit_1u_real": pub.get("profit_1u_real"),
        "profit_1u_synthetic": pub.get("profit_1u_synthetic"),
        "evaluation_status": pub.get("evaluation_status")
        or pub.get("performance_evaluation_status"),
        "rating": pub.get("rating"),
    }


def get_signals_af_activations(
    db: Session,
    run_id: int,
    filters: dict[str, Any],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    _get_run(db, int(run_id))
    lim = max(1, min(int(limit or 50), 100))
    off = max(0, int(offset or 0))

    raw_opps, query_count, snaps_n = _collect_universe(db, int(run_id), filters)
    opportunities = filter_opportunities(raw_opps, filters)

    def _sort_key(o: dict[str, Any]) -> tuple[Any, ...]:
        ko = o.get("kickoff_at") or ""
        return (
            str(ko),
            -int(o.get("snapshot_id") or 0),
            str(o.get("model_key") or ""),
            str(o.get("market_key") or ""),
        )

    sorted_opps = sorted(opportunities, key=_sort_key, reverse=True)
    total = len(sorted_opps)
    page = sorted_opps[off : off + lim]
    items = [_activation_public(o) for o in page]

    return _json_safe(
        {
            "items": items,
            "total": total,
            "limit": lim,
            "offset": off,
            "filters": dict(filters),
            "performance_granularity": "signal_opportunity",
            "note": (
                "Una riga per opportunità unica; "
                "le celle attive non sono scommesse indipendenti."
            ),
            "resource_profile": {
                "strategy": "filtered_snapshot_load",
                "query_count": query_count,
                "snapshots_loaded": snaps_n,
                "opportunities_materialized": total,
                "full_orm_entities_loaded": False,
                "full_signals_json_returned": False,
                "activations_page_size": lim,
            },
        }
    )
