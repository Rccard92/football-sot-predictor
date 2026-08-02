"""Analytics read-only sui segnali KPI storici Cecchino Lab (STEP 4A/4B).

Nessuna scrittura DB, nessun ricalcolo Rating/KPI, nessun full ORM load.
Filtro analitico Acquistabilità V3: join su replay ufficiale, nessuna formula V3.
"""

from __future__ import annotations

import json
import statistics
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_market_result import (
    CecchinoLabHistoricalMarketResult,
)
from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
from app.services.cecchino.cecchino_purchasability_v3_opposition import (
    SUPPORTED_V3_MARKETS,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics import (
    classify_calc_bucket,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_resolver import (
    resolve_official_purchasability_v3_replay,
)
from app.services.cecchino_data_lab.historical_scan_service import run_to_dict

HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION = "cecchino_lab_historical_kpi_signals_v2"
REASON_V3_MARKET_NOT_SUPPORTED = "purchasability_v3_market_not_supported"
ANALYTICS_CACHE_TTL_S = 300
CACHE_MAX_ENTRIES = 64
CACHE_KIND_SUMMARY = "summary"
CACHE_KIND_TIMELINE = "timeline"

RATING_BUCKETS: tuple[str, ...] = (
    "50-59",
    "60-69",
    "70-79",
    "80-89",
    "90-99",
    "100",
)

MARKET_ORDER: tuple[str, ...] = tuple(k for k, _ in KPI_V2_ROW_DEFS)
MARKET_LABELS: dict[str, str] = {k: lab for k, lab in KPI_V2_ROW_DEFS}

LEAN_ROW_KEYS: tuple[str, ...] = (
    "source_snapshot_id",
    "lab_match_id",
    "competition_name",
    "kickoff_at",
    "home_team",
    "away_team",
    "chronological_order",
    "historical_eligibility_status",
    "market_key",
    "market_label",
    "rating",
    "is_real_book_quote",
    "is_derived_quote",
    "quota_book",
    "won",
    "profit_1u_real",
    "profit_1u_synthetic",
    "evaluation_status",
    "result_reason",
)

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _f(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


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


def clear_historical_kpi_signals_cache() -> None:
    """Solo per test."""
    with _cache_lock:
        _cache.clear()


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


def _cache_key(
    *,
    run_id: int,
    kind: str,
    completed_at: Any,
    filters: dict[str, Any],
    group_by: str | None = None,
    purchasability_cache_meta: dict[str, Any] | None = None,
) -> str:
    payload = json.dumps(filters, sort_keys=True, default=str)
    parts = [
        str(int(run_id)),
        kind,
        HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION,
        _iso(completed_at) or "",
        payload,
    ]
    if purchasability_cache_meta:
        parts.append(json.dumps(purchasability_cache_meta, sort_keys=True, default=str))
    if group_by is not None:
        parts.append(str(group_by))
    return "|".join(parts)


def rating_bucket_for(rating: Any) -> str | None:
    r = _i(rating)
    if r is None or r < 50:
        return None
    if r >= 100:
        return "100"
    if r >= 90:
        return "90-99"
    if r >= 80:
        return "80-89"
    if r >= 70:
        return "70-79"
    if r >= 60:
        return "60-69"
    return "50-59"


def sample_class(n: int) -> str:
    if n < 10:
        return "very_small"
    if n < 30:
        return "small"
    if n < 100:
        return "medium"
    return "large"


def sort_markets(keys: list[str] | set[str]) -> list[str]:
    order_index = {k: i for i, k in enumerate(MARKET_ORDER)}

    def _sort_key(k: str) -> tuple[int, str]:
        return (order_index.get(k, 9999), k)

    return sorted(set(keys), key=_sort_key)


def _parse_purchasability_min_score(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise CecchinoLabImportError(
            "invalid_purchasability_min_score",
            "purchasability_min_score deve essere un intero 0–100 oppure null.",
            status_code=400,
            details={"value": raw},
        ) from exc
    if value < 0 or value > 100:
        raise CecchinoLabImportError(
            "invalid_purchasability_min_score",
            "purchasability_min_score deve essere compreso tra 0 e 100.",
            status_code=400,
            details={"value": value},
        )
    return value


def parse_kpi_signals_filters(**kwargs: Any) -> dict[str, Any]:
    quote_type = str(kwargs.get("quote_type") or "real").strip().lower()
    if quote_type not in ("real", "derived", "all"):
        quote_type = "real"
    return {
        "competition": (kwargs.get("competition") or None),
        "date_from": (kwargs.get("date_from") or None),
        "date_to": (kwargs.get("date_to") or None),
        "rating_bucket": (kwargs.get("rating_bucket") or None),
        "selection_key": (kwargs.get("selection_key") or None),
        "evaluation_status": (kwargs.get("evaluation_status") or None),
        "quote_type": quote_type,
        "purchasability_min_score": _parse_purchasability_min_score(
            kwargs.get("purchasability_min_score")
        ),
    }


def load_v3_result_index(
    db: Session, replay_run_id: int
) -> dict[tuple[int, str], dict[str, Any]]:
    """Indice (source_snapshot_id, market_key) → campi V3 scalari."""
    R = CecchinoLabPurchasabilityV3ReplayResult
    rows = db.execute(
        select(
            R.source_snapshot_id,
            R.market_key,
            R.score,
            R.score_class,
            R.gate_status,
            R.calculation_status,
        ).where(R.replay_run_id == int(replay_run_id))
    ).all()
    out: dict[tuple[int, str], dict[str, Any]] = {}
    for snap_id, market_key, score, score_class, gate_status, calculation_status in rows:
        out[(int(snap_id), str(market_key))] = {
            "score": _i(score),
            "score_class": score_class,
            "gate_status": gate_status,
            "calculation_status": calculation_status,
        }
    return out


def _v3_row_is_scored(v3: dict[str, Any] | None) -> bool:
    if not v3:
        return False
    return (
        v3.get("score") is not None
        and str(v3.get("gate_status") or "") == "passed"
        and str(v3.get("calculation_status") or "") != "error"
    )


def _empty_purchasability_filter(
    *,
    enabled: bool,
    min_score: int | None,
    official_replay_id: int | None = None,
    formula_version: str | None = None,
    base_signals: int = 0,
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "min_score": min_score,
        "official_replay_id": official_replay_id,
        "formula_version": formula_version,
        "base_signals_before_filter": base_signals,
        "v3_supported_and_joined": 0,
        "v3_scored": 0,
        "matched_threshold": 0,
        "excluded_unsupported_market": 0,
        "excluded_missing_join": 0,
        "excluded_gate_failed": 0,
        "excluded_unavailable": 0,
        "coverage_pct": 0.0,
    }


def apply_purchasability_min_score_filter(
    rows: list[dict[str, Any]],
    *,
    min_score: int,
    v3_index: dict[tuple[int, str], dict[str, Any]],
    official_replay_id: int,
    formula_version: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filtra lean rows per soglia V3 inclusiva; restituisce (matched, funnel)."""
    base = len(rows)
    funnel = _empty_purchasability_filter(
        enabled=True,
        min_score=min_score,
        official_replay_id=official_replay_id,
        formula_version=formula_version,
        base_signals=base,
    )
    matched: list[dict[str, Any]] = []
    for row in rows:
        mk = str(row.get("market_key") or "")
        snap_id = int(row.get("source_snapshot_id") or 0)
        if mk not in SUPPORTED_V3_MARKETS:
            funnel["excluded_unsupported_market"] += 1
            continue
        v3 = v3_index.get((snap_id, mk))
        if v3 is None:
            funnel["excluded_missing_join"] += 1
            continue
        funnel["v3_supported_and_joined"] += 1
        bucket = classify_calc_bucket(v3)
        if bucket == "gate_failed":
            funnel["excluded_gate_failed"] += 1
            continue
        if not _v3_row_is_scored(v3):
            funnel["excluded_unavailable"] += 1
            continue
        funnel["v3_scored"] += 1
        score = int(v3["score"])
        if score < min_score:
            continue
        enriched = dict(row)
        enriched["_purchasability_v3"] = {
            "score": score,
            "score_class": v3.get("score_class"),
            "gate_status": v3.get("gate_status"),
            "formula_version": formula_version,
            "supported": True,
            "exclusion_reason": None,
        }
        matched.append(enriched)
        funnel["matched_threshold"] += 1

    if base > 0:
        funnel["coverage_pct"] = round(
            funnel["matched_threshold"] / base * 100.0, 2
        )
    else:
        funnel["coverage_pct"] = 0.0
    return matched, funnel


def _selection_unsupported_by_v3(filters: dict[str, Any]) -> bool:
    sel = filters.get("selection_key")
    if not sel:
        return False
    return str(sel) not in SUPPORTED_V3_MARKETS


def _apply_resolved_purchasability(
    rows: list[dict[str, Any]],
    ctx: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    replay = ctx["_replay"]
    return apply_purchasability_min_score_filter(
        rows,
        min_score=int(ctx["_min_score"]),
        v3_index=ctx["_v3_index"],
        official_replay_id=int(replay.id),
        formula_version=getattr(replay, "formula_version", None),
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _rating_bucket_sql_expr(rating_col: Any) -> Any:
    return case(
        (rating_col.is_(None), None),
        (rating_col < 50, None),
        (rating_col >= 100, "100"),
        (rating_col >= 90, "90-99"),
        (rating_col >= 80, "80-89"),
        (rating_col >= 70, "70-79"),
        (rating_col >= 60, "60-69"),
        (rating_col >= 50, "50-59"),
        else_=None,
    )


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
            "not_full_season_report": getattr(run, "not_full_season_report", None),
            "pilot_strategy": getattr(run, "pilot_strategy", None),
            "max_matches": getattr(run, "max_matches", None),
        }
    block: dict[str, Any] = {
        "run_id": int(getattr(run, "id")),
        "season_label": getattr(run, "season_label", None),
        "status": getattr(run, "status", None),
        "scope": base.get("run_scope") or "full",
    }
    if base.get("is_partial_run") is not None:
        block["is_partial_run"] = bool(base.get("is_partial_run"))
    if base.get("not_full_season_report") is not None:
        block["not_full_season_report"] = bool(base.get("not_full_season_report"))
    if base.get("pilot_strategy"):
        block["pilot_strategy"] = base.get("pilot_strategy")
    if base.get("max_matches") is not None:
        block["max_matches"] = base.get("max_matches")
    return block


def _base_join_stmt():
    M = CecchinoLabHistoricalMarketResult
    S = CecchinoLabHistoricalMatchSnapshot
    return (
        select(
            S.id.label("source_snapshot_id"),
            M.lab_match_id,
            S.competition_name,
            S.kickoff_at,
            S.home_team,
            S.away_team,
            S.chronological_order,
            S.historical_eligibility_status,
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
            M.result_reason,
        )
        .select_from(M)
        .join(S, M.match_snapshot_id == S.id)
    )


def _apply_common_filters(
    stmt: Any,
    *,
    run_id: int,
    filters: dict[str, Any],
    apply_rating_universe: bool,
    apply_rating_bucket: bool,
    apply_selection_key: bool,
    apply_quote_type: bool,
    apply_evaluation_status: bool,
) -> Any:
    M = CecchinoLabHistoricalMarketResult
    S = CecchinoLabHistoricalMatchSnapshot

    stmt = stmt.where(
        M.run_id == int(run_id),
        S.historical_eligibility_status == ELIGIBLE_CORE,
    )

    competition = filters.get("competition")
    if competition:
        stmt = stmt.where(S.competition_name == str(competition))

    d_from = _parse_date(filters.get("date_from"))
    d_to = _parse_date(filters.get("date_to"))
    if d_from:
        stmt = stmt.where(func.date(S.kickoff_at) >= d_from)
    if d_to:
        stmt = stmt.where(func.date(S.kickoff_at) <= d_to)

    if apply_rating_universe:
        stmt = stmt.where(M.rating.is_not(None), M.rating >= 50)

    if apply_rating_bucket and filters.get("rating_bucket"):
        bucket_expr = _rating_bucket_sql_expr(M.rating)
        stmt = stmt.where(bucket_expr == str(filters["rating_bucket"]))

    if apply_selection_key and filters.get("selection_key"):
        stmt = stmt.where(M.market_key == str(filters["selection_key"]))

    if apply_evaluation_status and filters.get("evaluation_status"):
        stmt = stmt.where(M.evaluation_status == str(filters["evaluation_status"]))

    if apply_quote_type:
        qt = filters.get("quote_type") or "real"
        if qt == "real":
            stmt = stmt.where(M.is_real_book_quote.is_(True))
        elif qt == "derived":
            stmt = stmt.where(M.is_derived_quote.is_(True))

    return stmt


def _row_from_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        raw = dict(row._mapping)
    elif isinstance(row, dict):
        raw = row
    else:
        raw = {k: getattr(row, k, None) for k in LEAN_ROW_KEYS}
    return {k: raw.get(k) for k in LEAN_ROW_KEYS}


def _fetch_lean_rows(
    db: Session,
    run_id: int,
    filters: dict[str, Any],
    *,
    for_universe_only: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """SELECT colonne scalari; nessun JSONB, nessun ORM entity."""
    stmt = _base_join_stmt()
    stmt = _apply_common_filters(
        stmt,
        run_id=run_id,
        filters=filters,
        apply_rating_universe=True,
        apply_rating_bucket=not for_universe_only,
        apply_selection_key=not for_universe_only,
        apply_quote_type=not for_universe_only,
        apply_evaluation_status=not for_universe_only,
    )
    rows = [_row_from_mapping(r) for r in db.execute(stmt).mappings().all()]
    return rows, 1


def _fetch_diagnostics(
    db: Session,
    run_id: int,
    filters: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    M = CecchinoLabHistoricalMarketResult
    S = CecchinoLabHistoricalMatchSnapshot

    base = (
        select(
            func.count().label("rows_scanned"),
            func.sum(case((M.rating.is_(None), 1), else_=0)).label("rating_null"),
            func.sum(
                case(
                    (and_(M.rating.is_not(None), M.rating < 50), 1),
                    else_=0,
                )
            ).label("rating_below_50"),
            func.sum(
                case(
                    (and_(M.rating.is_not(None), M.rating >= 50), 1),
                    else_=0,
                )
            ).label("eligible_rows"),
            func.sum(
                case(
                    (
                        and_(
                            M.is_real_book_quote.is_(True),
                            M.profit_1u_real.is_not(None),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("performance_real_ready"),
            func.sum(
                case(
                    (
                        and_(
                            M.is_derived_quote.is_(True),
                            M.profit_1u_synthetic.is_not(None),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("performance_synthetic_ready"),
        )
        .select_from(M)
        .join(S, M.match_snapshot_id == S.id)
    )
    base = _apply_common_filters(
        base,
        run_id=run_id,
        filters=filters,
        apply_rating_universe=False,
        apply_rating_bucket=False,
        apply_selection_key=False,
        apply_quote_type=False,
        apply_evaluation_status=False,
    )
    row = db.execute(base).one()
    query_count = 1
    return {
        "rows_scanned": int(row.rows_scanned or 0),
        "rating_null": int(row.rating_null or 0),
        "rating_below_50": int(row.rating_below_50 or 0),
        "eligible_rows": int(row.eligible_rows or 0),
        "performance_real_ready": int(row.performance_real_ready or 0),
        "performance_synthetic_ready": int(row.performance_synthetic_ready or 0),
    }, query_count


def _available_filters_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    competitions = sorted(
        {str(r["competition_name"]) for r in rows if r.get("competition_name")}
    )
    selection_keys = sort_markets(
        [str(r["market_key"]) for r in rows if r.get("market_key")]
    )
    dates: list[date] = []
    for r in rows:
        ko = r.get("kickoff_at")
        if isinstance(ko, datetime):
            dates.append(ko.date())
        elif isinstance(ko, date):
            dates.append(ko)
    return {
        "competitions": competitions,
        "selection_keys": selection_keys,
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
    }


def compute_metrics_for_rows(rows: list[dict[str, Any]], quote_type: str) -> dict[str, Any]:
    if quote_type == "real":
        filtered = [r for r in rows if bool(r.get("is_real_book_quote"))]
        profit_field = "profit_1u_real"
    elif quote_type in ("derived", "synthetic"):
        filtered = [r for r in rows if bool(r.get("is_derived_quote"))]
        profit_field = "profit_1u_synthetic"
    else:
        raise ValueError(f"quote_type non supportato: {quote_type}")

    signals_count = len(filtered)
    wins = losses = pending_or_unsettled = void_or_zero_profit = 0
    profits: list[float] = []
    odds_played: list[float] = []
    odds_won: list[float] = []

    for r in filtered:
        won = r.get("won")
        if won is True:
            wins += 1
        elif won is False:
            losses += 1
        else:
            pending_or_unsettled += 1

        pf = _f(r.get(profit_field))
        if pf is not None:
            profits.append(pf)
            if abs(pf) < 1e-12:
                void_or_zero_profit += 1

        if won is not None:
            od = _f(r.get("quota_book"))
            if od is not None:
                odds_played.append(od)
                if won is True:
                    odds_won.append(od)

    evaluated_count = wins + losses
    stake_count = len(profits)

    win_rate_pct: float | None
    if evaluated_count > 0:
        win_rate_pct = round(wins / evaluated_count * 100.0, 1)
    else:
        win_rate_pct = None

    win_rate_decimal = (wins / evaluated_count) if evaluated_count > 0 else None
    average_odds_void: float | None
    if win_rate_decimal and win_rate_decimal > 0:
        average_odds_void = round(1.0 / win_rate_decimal, 2)
    else:
        average_odds_void = None

    if stake_count > 0:
        profit_units = round(sum(profits), 2)
        roi_pct = round(profit_units / stake_count * 100.0, 2)
        average_odds_played = (
            round(statistics.fmean(odds_played), 2) if odds_played else None
        )
        average_odds_won = round(statistics.fmean(odds_won), 2) if odds_won else None
    else:
        profit_units = None
        roi_pct = None
        average_odds_played = None
        average_odds_won = None
        average_odds_void = None

    return {
        "signals_count": signals_count,
        "evaluated_count": evaluated_count,
        "wins": wins,
        "losses": losses,
        "pending_or_unsettled": pending_or_unsettled,
        "void_or_zero_profit": void_or_zero_profit,
        "win_rate_pct": win_rate_pct,
        "average_odds_played": average_odds_played,
        "average_odds_won": average_odds_won,
        "average_odds_void": average_odds_void,
        "stake_count": stake_count,
        "profit_units": profit_units,
        "roi_pct": roi_pct,
    }


def _metrics_with_average_odds_alias(metrics: dict[str, Any]) -> dict[str, Any]:
    out = dict(metrics)
    out["average_odds"] = metrics.get("average_odds_played")
    return out


def _overall_metrics(rows: list[dict[str, Any]], quote_type: str) -> dict[str, Any]:
    if quote_type == "all":
        return {
            "real": compute_metrics_for_rows(rows, "real"),
            "synthetic": compute_metrics_for_rows(rows, "derived"),
        }
    if quote_type == "real":
        return {
            "real": compute_metrics_for_rows(rows, "real"),
            "synthetic": None,
        }
    return {
        "real": None,
        "synthetic": compute_metrics_for_rows(rows, "derived"),
    }


def _active_quote_types(quote_type: str) -> list[str]:
    if quote_type == "all":
        return ["real", "derived"]
    if quote_type == "derived":
        return ["derived"]
    return ["real"]


def _by_rating_bucket_rows(
    rows: list[dict[str, Any]], filters: dict[str, Any]
) -> list[dict[str, Any]]:
    quote_type = filters.get("quote_type") or "real"
    out: list[dict[str, Any]] = []
    for qt in _active_quote_types(quote_type):
        for bucket in RATING_BUCKETS:
            bucket_rows = [
                r
                for r in rows
                if rating_bucket_for(r.get("rating")) == bucket
            ]
            metrics = compute_metrics_for_rows(bucket_rows, qt)
            out.append(
                {
                    "rating_bucket": bucket,
                    "quote_type": "real" if qt == "real" else "derived",
                    "status": "ready" if metrics["evaluated_count"] > 0 else "empty",
                    **metrics,
                }
            )
    return out


def _heatmap_payload(rows: list[dict[str, Any]], filters: dict[str, Any]) -> dict[str, Any]:
    quote_type = filters.get("quote_type") or "real"
    selection_keys = sort_markets([str(r["market_key"]) for r in rows if r.get("market_key")])
    cells: list[dict[str, Any]] = []
    for qt in _active_quote_types(quote_type):
        for bucket in RATING_BUCKETS:
            for mk in selection_keys:
                cell_rows = [
                    r
                    for r in rows
                    if rating_bucket_for(r.get("rating")) == bucket
                    and str(r.get("market_key") or "") == mk
                ]
                metrics = compute_metrics_for_rows(cell_rows, qt)
                sample_n = (
                    metrics["evaluated_count"]
                    if metrics["evaluated_count"] > 0
                    else metrics["signals_count"]
                )
                cells.append(
                    {
                        "rating_bucket": bucket,
                        "selection_key": mk,
                        "quote_type": "real" if qt == "real" else "derived",
                        "sample_class": sample_class(int(sample_n)),
                        **_metrics_with_average_odds_alias(metrics),
                    }
                )
    return {
        "rating_buckets": list(RATING_BUCKETS),
        "selection_keys": selection_keys,
        "cells": cells,
    }


def compute_summary_from_lean_rows(
    run: CecchinoLabHistoricalScanRun | Any,
    rows: list[dict[str, Any]],
    filters: dict[str, Any],
    *,
    query_count: int = 0,
    diagnostics: dict[str, Any] | None = None,
    available_filters: dict[str, Any] | None = None,
    purchasability_filter: dict[str, Any] | None = None,
    empty_reason: str | None = None,
) -> dict[str, Any]:
    quote_type = filters.get("quote_type") or "real"
    if available_filters is None:
        available_filters = _available_filters_from_rows(rows)
    if diagnostics is None:
        diagnostics = {
            "rows_scanned": 0,
            "rating_null": 0,
            "rating_below_50": 0,
            "eligible_rows": len(rows),
            "performance_real_ready": 0,
            "performance_synthetic_ready": 0,
        }

    payload: dict[str, Any] = {
        "schema_version": HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION,
        "generated_at": _utcnow().isoformat(),
        "run": _run_block(run),
        "filters": dict(filters),
        "available_filters": available_filters,
        "overall": _overall_metrics(rows, quote_type),
        "by_rating_bucket": _by_rating_bucket_rows(rows, filters),
        "heatmap": _heatmap_payload(rows, filters),
        "diagnostics": diagnostics,
        "resource_profile": {
            "strategy": "sql_aggregates",
            "query_count": int(query_count),
            "rows_materialized": len(rows),
            "full_orm_entities_loaded": False,
            "jsonb_payloads_loaded": False,
        },
    }
    if purchasability_filter is not None:
        payload["purchasability_filter"] = purchasability_filter
    if empty_reason:
        payload["reason"] = empty_reason
        payload["message"] = (
            "Il mercato selezionato non è supportato dalla formula Acquistabilità V3."
            if empty_reason == REASON_V3_MARKET_NOT_SUPPORTED
            else empty_reason
        )
    return _json_safe(payload)


def _group_key_for_row(row: dict[str, Any], group_by: str) -> tuple[str, str, date | None, date | None]:
    ko = row.get("kickoff_at")
    if isinstance(ko, datetime):
        d = ko.date()
    elif isinstance(ko, date):
        d = ko
    else:
        d = None

    if group_by == "week" and d is not None:
        iso = d.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        label = f"Settimana {iso.week} {iso.year}"
        week_start = date.fromisocalendar(iso.year, iso.week, 1)
        week_end = date.fromisocalendar(iso.year, iso.week, 7)
        return key, label, week_start, week_end

    if d is not None:
        key = d.isoformat()
        label = d.isoformat()
        return key, label, d, d

    return "unknown", "Data sconosciuta", None, None


def _timeline_point_metrics(
    rows: list[dict[str, Any]], quote_type: str
) -> dict[str, Any]:
    if quote_type == "all":
        return {
            "real": compute_metrics_for_rows(rows, "real"),
            "synthetic": compute_metrics_for_rows(rows, "derived"),
        }
    if quote_type == "real":
        return compute_metrics_for_rows(rows, "real")
    return compute_metrics_for_rows(rows, "derived")


def compute_timeline_from_lean_rows(
    run: CecchinoLabHistoricalScanRun | Any,
    rows: list[dict[str, Any]],
    filters: dict[str, Any],
    group_by: str = "date",
    *,
    query_count: int = 0,
) -> dict[str, Any]:
    quote_type = filters.get("quote_type") or "real"
    grouping_fallback: str | None = None
    effective_group_by = group_by
    if group_by == "matchday":
        effective_group_by = "date"
        grouping_fallback = "date"

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    meta: dict[str, tuple[str, date | None, date | None]] = {}
    for r in rows:
        key, label, d_from, d_to = _group_key_for_row(r, effective_group_by)
        grouped[key].append(r)
        meta[key] = (label, d_from, d_to)

    ordered_keys = sorted(
        grouped.keys(),
        key=lambda k: (
            meta[k][1] or date.min,
            meta[k][2] or date.min,
            k,
        ),
    )

    cum_profit_real = 0.0
    cum_stake_real = 0
    cum_profit_synth = 0.0
    cum_stake_synth = 0
    points: list[dict[str, Any]] = []

    for key in ordered_keys:
        group_rows = grouped[key]
        label, d_from, d_to = meta[key]
        metrics = _timeline_point_metrics(group_rows, quote_type)

        point: dict[str, Any] = {
            "group_key": key,
            "group_label": label,
            "date_from": d_from.isoformat() if d_from else None,
            "date_to": d_to.isoformat() if d_to else None,
        }

        if quote_type == "all":
            real_m = metrics["real"]
            synth_m = metrics["synthetic"]
            if real_m.get("profit_units") is not None:
                cum_profit_real += float(real_m["profit_units"])
            cum_stake_real += int(real_m.get("stake_count") or 0)
            if synth_m.get("profit_units") is not None:
                cum_profit_synth += float(synth_m["profit_units"])
            cum_stake_synth += int(synth_m.get("stake_count") or 0)
            point["real"] = real_m
            point["synthetic"] = synth_m
            point["cumulative_profit_units"] = {
                "real": round(cum_profit_real, 2) if cum_stake_real > 0 else None,
                "synthetic": round(cum_profit_synth, 2) if cum_stake_synth > 0 else None,
            }
            point["cumulative_roi_pct"] = {
                "real": (
                    round(cum_profit_real / cum_stake_real * 100.0, 2)
                    if cum_stake_real > 0
                    else None
                ),
                "synthetic": (
                    round(cum_profit_synth / cum_stake_synth * 100.0, 2)
                    if cum_stake_synth > 0
                    else None
                ),
            }
        else:
            point.update(metrics)
            pf = metrics.get("profit_units")
            sc = int(metrics.get("stake_count") or 0)
            if quote_type == "real":
                if pf is not None:
                    cum_profit_real += float(pf)
                cum_stake_real += sc
                point["cumulative_profit_units"] = (
                    round(cum_profit_real, 2) if cum_stake_real > 0 else None
                )
                point["cumulative_roi_pct"] = (
                    round(cum_profit_real / cum_stake_real * 100.0, 2)
                    if cum_stake_real > 0
                    else None
                )
            else:
                if pf is not None:
                    cum_profit_synth += float(pf)
                cum_stake_synth += sc
                point["cumulative_profit_units"] = (
                    round(cum_profit_synth, 2) if cum_stake_synth > 0 else None
                )
                point["cumulative_roi_pct"] = (
                    round(cum_profit_synth / cum_stake_synth * 100.0, 2)
                    if cum_stake_synth > 0
                    else None
                )

        bucket_breakdown: list[dict[str, Any]] = []
        for qt in _active_quote_types(quote_type):
            for bucket in RATING_BUCKETS:
                bucket_rows = [
                    r
                    for r in group_rows
                    if rating_bucket_for(r.get("rating")) == bucket
                ]
                bm = compute_metrics_for_rows(bucket_rows, qt)
                bucket_breakdown.append(
                    {
                        "rating_bucket": bucket,
                        "quote_type": "real" if qt == "real" else "derived",
                        **bm,
                    }
                )
        point["by_rating_bucket"] = bucket_breakdown
        points.append(point)

    payload = {
        "schema_version": HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION,
        "generated_at": _utcnow().isoformat(),
        "run": _run_block(run),
        "filters": dict(filters),
        "group_by": group_by,
        "effective_group_by": effective_group_by,
        "grouping_fallback": grouping_fallback,
        "points": points,
        "resource_profile": {
            "strategy": "sql_aggregates",
            "query_count": int(query_count),
            "rows_materialized": len(rows),
            "full_orm_entities_loaded": False,
            "jsonb_payloads_loaded": False,
        },
    }
    return _json_safe(payload)


def _market_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    mk = str(row.get("market_key") or "")
    try:
        order = MARKET_ORDER.index(mk)
    except ValueError:
        order = 9999
    ko = row.get("kickoff_at")
    if isinstance(ko, datetime):
        kickoff_key = -ko.timestamp()
    else:
        kickoff_key = float("inf")
    return (
        kickoff_key,
        -int(row.get("source_snapshot_id") or 0),
        order,
        mk,
    )


def _activation_item(row: dict[str, Any], quote_type_filter: str) -> dict[str, Any]:
    is_real = bool(row.get("is_real_book_quote"))
    is_derived = bool(row.get("is_derived_quote"))
    if is_real and (quote_type_filter in ("real", "all")):
        qt_label = "real"
        profit_units = _f(row.get("profit_1u_real"))
    elif is_derived and (quote_type_filter in ("derived", "all")):
        qt_label = "derived"
        profit_units = _f(row.get("profit_1u_synthetic"))
    elif quote_type_filter == "real" and is_real:
        qt_label = "real"
        profit_units = _f(row.get("profit_1u_real"))
    elif quote_type_filter == "derived" and is_derived:
        qt_label = "derived"
        profit_units = _f(row.get("profit_1u_synthetic"))
    else:
        qt_label = "real" if is_real else ("derived" if is_derived else "real")
        profit_units = _f(row.get("profit_1u_real") if is_real else row.get("profit_1u_synthetic"))

    mk = str(row.get("market_key") or "")
    item: dict[str, Any] = {
        "source_snapshot_id": int(row.get("source_snapshot_id") or 0),
        "lab_match_id": int(row.get("lab_match_id") or 0),
        "competition_name": row.get("competition_name"),
        "kickoff_at": _iso(row.get("kickoff_at")),
        "matchday_label": None,
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "market_key": mk,
        "market_label": row.get("market_label") or MARKET_LABELS.get(mk, mk),
        "rating": _i(row.get("rating")),
        "rating_bucket": rating_bucket_for(row.get("rating")),
        "quote_type": qt_label,
        "quota_book": _f(row.get("quota_book")),
        "won": row.get("won"),
        "profit_units": profit_units,
        "evaluation_status": row.get("evaluation_status"),
        "result_reason": row.get("result_reason"),
    }
    v3 = row.get("_purchasability_v3")
    if isinstance(v3, dict):
        item["purchasability_score"] = v3.get("score")
        item["purchasability_class"] = v3.get("score_class")
        item["purchasability_gate_status"] = v3.get("gate_status")
        item["purchasability_formula_version"] = v3.get("formula_version")
        item["purchasability_supported"] = bool(v3.get("supported"))
        item["purchasability_exclusion_reason"] = v3.get("exclusion_reason")
    return item


def get_kpi_signals_summary(
    db: Session, run_id: int, filters: dict[str, Any]
) -> dict[str, Any]:
    run = _get_run(db, int(run_id))
    min_score = filters.get("purchasability_min_score")

    if min_score is not None and _selection_unsupported_by_v3(filters):
        funnel = _empty_purchasability_filter(
            enabled=True, min_score=int(min_score), base_signals=0
        )
        funnel["reason"] = REASON_V3_MARKET_NOT_SUPPORTED
        return compute_summary_from_lean_rows(
            run,
            [],
            filters,
            purchasability_filter=funnel,
            empty_reason=REASON_V3_MARKET_NOT_SUPPORTED,
        )

    purch_ctx: dict[str, Any] | None = None
    cache_meta: dict[str, Any] | None = None
    if min_score is not None:
        replay = resolve_official_purchasability_v3_replay(db, int(run_id))
        cache_meta = {
            "purchasability_min_score": int(min_score),
            "official_replay_id": int(replay.id),
            "formula_version": getattr(replay, "formula_version", None),
            "replay_completed_at": _iso(getattr(replay, "completed_at", None)),
        }
        purch_ctx = {
            "_v3_index": load_v3_result_index(db, int(replay.id)),
            "_replay": replay,
            "_min_score": int(min_score),
        }

    cache_key = _cache_key(
        run_id=int(run_id),
        kind=CACHE_KIND_SUMMARY,
        completed_at=getattr(run, "completed_at", None),
        filters=filters,
        purchasability_cache_meta=cache_meta,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    query_count = 0
    universe_rows, qc = _fetch_lean_rows(
        db, int(run_id), filters, for_universe_only=True
    )
    query_count += qc
    available_filters = _available_filters_from_rows(universe_rows)

    rows, qc = _fetch_lean_rows(db, int(run_id), filters, for_universe_only=False)
    query_count += qc
    diagnostics, qc = _fetch_diagnostics(db, int(run_id), filters)
    query_count += qc

    purchasability_filter = None
    if purch_ctx is not None:
        rows, purchasability_filter = _apply_resolved_purchasability(rows, purch_ctx)
        query_count += 1

    payload = compute_summary_from_lean_rows(
        run,
        rows,
        filters,
        query_count=query_count,
        diagnostics=diagnostics,
        available_filters=available_filters,
        purchasability_filter=purchasability_filter,
    )
    _cache_set(cache_key, payload)
    return payload


def get_kpi_signals_timeline(
    db: Session,
    run_id: int,
    filters: dict[str, Any],
    group_by: str = "date",
) -> dict[str, Any]:
    run = _get_run(db, int(run_id))
    normalized_group = str(group_by or "date").strip().lower()
    if normalized_group not in ("date", "week", "matchday"):
        normalized_group = "date"

    min_score = filters.get("purchasability_min_score")
    if min_score is not None and _selection_unsupported_by_v3(filters):
        return _json_safe(
            {
                "schema_version": HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION,
                "generated_at": _utcnow().isoformat(),
                "run": _run_block(run),
                "filters": dict(filters),
                "group_by": normalized_group,
                "points": [],
                "reason": REASON_V3_MARKET_NOT_SUPPORTED,
                "message": (
                    "Il mercato selezionato non è supportato dalla formula "
                    "Acquistabilità V3."
                ),
                "purchasability_filter": _empty_purchasability_filter(
                    enabled=True, min_score=int(min_score), base_signals=0
                ),
                "resource_profile": {
                    "strategy": "sql_aggregates",
                    "query_count": 0,
                    "rows_materialized": 0,
                    "full_orm_entities_loaded": False,
                    "jsonb_payloads_loaded": False,
                },
            }
        )

    purch_ctx: dict[str, Any] | None = None
    cache_meta: dict[str, Any] | None = None
    if min_score is not None:
        replay = resolve_official_purchasability_v3_replay(db, int(run_id))
        cache_meta = {
            "purchasability_min_score": int(min_score),
            "official_replay_id": int(replay.id),
            "formula_version": getattr(replay, "formula_version", None),
            "replay_completed_at": _iso(getattr(replay, "completed_at", None)),
        }
        purch_ctx = {
            "_v3_index": load_v3_result_index(db, int(replay.id)),
            "_replay": replay,
            "_min_score": int(min_score),
        }

    cache_key = _cache_key(
        run_id=int(run_id),
        kind=CACHE_KIND_TIMELINE,
        completed_at=getattr(run, "completed_at", None),
        filters=filters,
        group_by=normalized_group,
        purchasability_cache_meta=cache_meta,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    rows, query_count = _fetch_lean_rows(db, int(run_id), filters, for_universe_only=False)
    purchasability_filter = None
    if purch_ctx is not None:
        rows, purchasability_filter = _apply_resolved_purchasability(rows, purch_ctx)
        query_count += 1

    payload = compute_timeline_from_lean_rows(
        run,
        rows,
        filters,
        group_by=normalized_group,
        query_count=query_count,
    )
    if purchasability_filter is not None:
        payload["purchasability_filter"] = purchasability_filter
    _cache_set(cache_key, payload)
    return payload


def get_kpi_signal_activations(
    db: Session,
    run_id: int,
    filters: dict[str, Any],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    _get_run(db, int(run_id))
    lim = max(1, min(int(limit or 50), 100))
    off = max(0, int(offset or 0))

    min_score = filters.get("purchasability_min_score")
    if min_score is not None and _selection_unsupported_by_v3(filters):
        return _json_safe(
            {
                "items": [],
                "total": 0,
                "limit": lim,
                "offset": off,
                "filters": dict(filters),
                "reason": REASON_V3_MARKET_NOT_SUPPORTED,
                "message": (
                    "Il mercato selezionato non è supportato dalla formula "
                    "Acquistabilità V3."
                ),
                "purchasability_filter": _empty_purchasability_filter(
                    enabled=True, min_score=int(min_score), base_signals=0
                ),
                "resource_profile": {
                    "strategy": "sql_aggregates",
                    "query_count": 0,
                    "rows_materialized": 0,
                    "full_orm_entities_loaded": False,
                    "jsonb_payloads_loaded": False,
                    "activations_page_size": lim,
                },
            }
        )

    query_count = 0
    rows, qc = _fetch_lean_rows(db, int(run_id), filters, for_universe_only=False)
    query_count += qc

    purchasability_filter = None
    if min_score is not None:
        replay = resolve_official_purchasability_v3_replay(db, int(run_id))
        v3_index = load_v3_result_index(db, int(replay.id))
        query_count += 1
        rows, purchasability_filter = apply_purchasability_min_score_filter(
            rows,
            min_score=int(min_score),
            v3_index=v3_index,
            official_replay_id=int(replay.id),
            formula_version=getattr(replay, "formula_version", None),
        )

    quote_type = filters.get("quote_type") or "real"
    sorted_rows = sorted(rows, key=_market_sort_key)
    total = len(sorted_rows)
    page_rows = sorted_rows[off : off + lim]
    items = [_activation_item(r, quote_type) for r in page_rows]

    payload: dict[str, Any] = {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": off,
        "filters": dict(filters),
        "resource_profile": {
            "strategy": "sql_aggregates",
            "query_count": query_count,
            "rows_materialized": len(rows),
            "full_orm_entities_loaded": False,
            "jsonb_payloads_loaded": False,
            "activations_page_size": lim,
        },
    }
    if purchasability_filter is not None:
        payload["purchasability_filter"] = purchasability_filter
    return _json_safe(payload)
