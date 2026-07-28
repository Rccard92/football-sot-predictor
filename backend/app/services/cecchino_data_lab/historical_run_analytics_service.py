"""Analytics read-only per dashboard run storico Cecchino Lab.

Nessuna scrittura su run/snapshot/settlement. Nessun ZIP. Nessun ricalcolo formule.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.models.cecchino_lab_historical_scan_run import (
    ACTIVE_STATUSES,
    CecchinoLabHistoricalScanRun,
)
from app.services.cecchino.cecchino_constants import (
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    CECCHINO_WEIGHT_MODEL_KEYS,
    get_cecchino_weight_model,
    model_meta_for_key,
    model_weights_json,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_analytics_agg import (
    ANALYTICS_AGGREGATION_VERSION,
    BALANCE_CANONICAL_PILLARS,
    BALANCE_COMBINATIONS,
    BALANCE_PILLAR_LABELS,
    GI_PILLAR_LABELS,
    GI_PILLARS,
    MIN_COMBO_SAMPLE,
    PURCH_BANDS_DASHBOARD,
    RATING_BANDS_DASHBOARD,
    agg_bucket,
    as_dict,
    as_list,
    balance_pillars,
    brier_score,
    build_combined_patterns,
    bump_bucket_from_market,
    confidence_status,
    finalize_bucket,
    group_patterns_for_dashboard,
    max_losing_streak,
    purchasability_band_dashboard,
    quote_count_reconciliation,
    quote_quality_of_market,
    rating_band_dashboard,
    signal_meta,
    structural_class,
)
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_scan_service import run_to_dict

logger = logging.getLogger(__name__)

MARKET_ORDER: tuple[str, ...] = tuple(k for k, _ in KPI_V2_ROW_DEFS)
MARKET_LABELS: dict[str, str] = {k: lab for k, lab in KPI_V2_ROW_DEFS}

CACHE_TTL_ACTIVE_S = 15
CACHE_TTL_COMPLETED_S = 180
CACHE_MAX_ENTRIES = 256

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _cache_set(key: str, value: Any, ttl: float) -> None:
    now = time.monotonic()
    with _cache_lock:
        if len(_cache) >= CACHE_MAX_ENTRIES:
            # Eviction: rimuovi scaduti, poi i più vecchi
            expired = [k for k, (exp, _) in _cache.items() if exp < now]
            for k in expired:
                _cache.pop(k, None)
            while len(_cache) >= CACHE_MAX_ENTRIES:
                oldest = next(iter(_cache))
                _cache.pop(oldest, None)
        _cache[key] = (now + ttl, value)


def clear_dashboard_cache() -> None:
    """Solo per test."""
    with _cache_lock:
        _cache.clear()


def parse_dashboard_filters(
    *,
    competition: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    market_key: str | None = None,
    rating_band: str | None = None,
    purchasability_band: str | None = None,
    quote_quality: str | None = None,
    signal_model: str | None = None,
    signal_active: str | bool | None = None,
    balance_class: str | None = None,
    goal_intensity_status: str | None = None,
    purchasability_status: str | None = None,
    eligibility_status: str | None = None,
) -> dict[str, Any]:
    sig_active: bool | None = None
    if signal_active is True or (
        isinstance(signal_active, str) and signal_active.lower() in ("1", "true", "yes")
    ):
        sig_active = True
    elif signal_active is False or (
        isinstance(signal_active, str) and signal_active.lower() in ("0", "false", "no")
    ):
        sig_active = False

    return {
        "competition": competition or None,
        "date_from": date_from or None,
        "date_to": date_to or None,
        "market_key": market_key or None,
        "rating_band": rating_band or None,
        "purchasability_band": purchasability_band or None,
        "quote_quality": quote_quality or None,
        "signal_model": (signal_model or None),
        "signal_active": sig_active,
        "balance_class": balance_class or None,
        "goal_intensity_status": goal_intensity_status or None,
        "purchasability_status": purchasability_status or None,
        # Default performance universe
        "eligibility_status": eligibility_status or ELIGIBLE_CORE,
    }


def _filters_cache_key(filters: dict[str, Any]) -> str:
    payload = json.dumps(filters, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _get_run(db: Session, run_id: int) -> CecchinoLabHistoricalScanRun:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    return run


def _is_provisional(run: CecchinoLabHistoricalScanRun) -> bool:
    return run.status in ACTIVE_STATUSES


def _ttl_for_run(run: CecchinoLabHistoricalScanRun) -> float:
    return CACHE_TTL_ACTIVE_S if _is_provisional(run) else CACHE_TTL_COMPLETED_S


def _run_meta(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
    base = run_to_dict(run)
    return {
        "run_id": int(run.id),
        "season_label": run.season_label,
        "scope": base.get("run_scope"),
        "status": run.status,
        "scan_version": run.scan_version,
        "source_git_commit": run.source_git_commit,
        "source_git_commit_source": getattr(run, "source_git_commit_source", None),
        "source_revision_status": getattr(run, "source_revision_status", None),
        "started_at": base.get("started_at"),
        "completed_at": base.get("completed_at"),
        "bookmaker_storico": "Bet365",
        "bookmaker_today_operativo": "Betfair",
        "is_partial_run": base.get("is_partial_run"),
        "not_full_season_report": base.get("not_full_season_report"),
        "run_scope": base.get("run_scope"),
        "pilot_strategy": base.get("pilot_strategy"),
        "max_matches": base.get("max_matches"),
        "eligible_per_competition": base.get("eligible_per_competition"),
    }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _snap_in_date_range(s: CecchinoLabHistoricalMatchSnapshot, filters: dict[str, Any]) -> bool:
    d_from = _parse_date(filters.get("date_from"))
    d_to = _parse_date(filters.get("date_to"))
    if not d_from and not d_to:
        return True
    if not s.kickoff_at:
        return False
    kd = s.kickoff_at.date() if hasattr(s.kickoff_at, "date") else s.kickoff_at
    if d_from and kd < d_from:
        return False
    if d_to and kd > d_to:
        return False
    return True


def _purch_score_for_market(snap: CecchinoLabHistoricalMatchSnapshot, market_key: str) -> Any:
    purch = as_dict(snap.purchasability_compatibility_json)
    for mk_row in purch.get("markets") or []:
        if isinstance(mk_row, dict) and mk_row.get("market_key") == market_key:
            return mk_row.get("score")
    return None


def _module_obs_status(payload: dict[str, Any] | None, *, status_keys: tuple[str, ...]) -> str:
    data = as_dict(payload)
    if not data:
        return "unavailable"
    for key in status_keys:
        val = data.get(key)
        if val in ("complete", "computed"):
            return "complete"
        if val in ("partial", "insufficient_sample", "insufficient_ecdf_train"):
            return "partial"
        if val in ("unavailable",):
            return "unavailable"
    if data.get("observation_status") in ("complete", "partial", "unavailable"):
        return str(data["observation_status"])
    return "partial" if data else "unavailable"


def _load_snapshots_lean(db: Session, run_id: int) -> list[CecchinoLabHistoricalMatchSnapshot]:
    return list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot)
            .options(
                load_only(
                    CecchinoLabHistoricalMatchSnapshot.id,
                    CecchinoLabHistoricalMatchSnapshot.run_id,
                    CecchinoLabHistoricalMatchSnapshot.lab_match_id,
                    CecchinoLabHistoricalMatchSnapshot.competition_name,
                    CecchinoLabHistoricalMatchSnapshot.season_label,
                    CecchinoLabHistoricalMatchSnapshot.kickoff_at,
                    CecchinoLabHistoricalMatchSnapshot.home_team,
                    CecchinoLabHistoricalMatchSnapshot.away_team,
                    CecchinoLabHistoricalMatchSnapshot.chronological_order,
                    CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status,
                    CecchinoLabHistoricalMatchSnapshot.historical_eligibility_reason,
                    CecchinoLabHistoricalMatchSnapshot.blocking_reasons_json,
                    CecchinoLabHistoricalMatchSnapshot.module_availability_json,
                    CecchinoLabHistoricalMatchSnapshot.signals_json,
                    CecchinoLabHistoricalMatchSnapshot.balance_v5_json,
                    CecchinoLabHistoricalMatchSnapshot.goal_intensity_compatibility_json,
                    CecchinoLabHistoricalMatchSnapshot.purchasability_compatibility_json,
                    CecchinoLabHistoricalMatchSnapshot.quote_sources_json,
                    CecchinoLabHistoricalMatchSnapshot.result_json,
                    CecchinoLabHistoricalMatchSnapshot.settlement_summary_json,
                    CecchinoLabHistoricalMatchSnapshot.settlement_status,
                    CecchinoLabHistoricalMatchSnapshot.warnings_json,
                    CecchinoLabHistoricalMatchSnapshot.error_json,
                    CecchinoLabHistoricalMatchSnapshot.pre_match_payload_sha256,
                    CecchinoLabHistoricalMatchSnapshot.pre_match_locked_at,
                    CecchinoLabHistoricalMatchSnapshot.cecchino_output_json,
                    CecchinoLabHistoricalMatchSnapshot.historical_kpi_json,
                )
            )
            .where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
            .order_by(
                CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc().nulls_last(),
                CecchinoLabHistoricalMatchSnapshot.lab_match_id.asc(),
            )
        ).all()
    )


def _load_markets(db: Session, run_id: int) -> list[CecchinoLabHistoricalMarketResult]:
    return list(
        db.scalars(
            select(CecchinoLabHistoricalMarketResult)
            .where(CecchinoLabHistoricalMarketResult.run_id == run_id)
            .order_by(
                CecchinoLabHistoricalMarketResult.match_snapshot_id.asc(),
                CecchinoLabHistoricalMarketResult.market_key.asc(),
            )
        ).all()
    )


def _snap_passes_module_filters(
    s: CecchinoLabHistoricalMatchSnapshot, filters: dict[str, Any]
) -> bool:
    if filters.get("competition") and s.competition_name != filters["competition"]:
        return False
    if not _snap_in_date_range(s, filters):
        return False
    if filters.get("balance_class"):
        bal = as_dict(s.balance_v5_json)
        bal_class, _ = structural_class(bal.get("structural_summary") if bal else None)
        if bal_class != filters["balance_class"]:
            return False
    if filters.get("goal_intensity_status"):
        gi = as_dict(s.goal_intensity_compatibility_json)
        st = gi.get("execution_status") or gi.get("observation_status") or "unavailable"
        if st != filters["goal_intensity_status"]:
            return False
    if filters.get("purchasability_status"):
        purch = as_dict(s.purchasability_compatibility_json)
        st = purch.get("execution_status") or purch.get("observation_status") or "unavailable"
        if st != filters["purchasability_status"]:
            return False
    return True


def _market_passes_filters(
    m: CecchinoLabHistoricalMarketResult,
    s: CecchinoLabHistoricalMatchSnapshot | None,
    filters: dict[str, Any],
) -> bool:
    if filters.get("market_key") and m.market_key != filters["market_key"]:
        return False
    if filters.get("rating_band"):
        if rating_band_dashboard(m.rating) != filters["rating_band"]:
            return False
    if filters.get("quote_quality"):
        if quote_quality_of_market(m) != filters["quote_quality"]:
            return False
    if filters.get("signal_active") is not None:
        if bool(m.signal_active) != bool(filters["signal_active"]):
            return False
    if filters.get("purchasability_band") and s is not None:
        score = _purch_score_for_market(s, m.market_key)
        if purchasability_band_dashboard(score) != filters["purchasability_band"]:
            return False
    if filters.get("signal_model") and s is not None:
        sigs = as_dict(s.signals_json)
        models = as_dict(sigs.get("models"))
        mk = str(filters["signal_model"]).upper()
        model = as_dict(models.get(mk))
        active = as_list(model.get("active_signals"))
        # Filtra solo se il modello ha almeno un segnale sulla partita
        # (per matrici mercato: se market_key matcha un active signal)
        if not active:
            return False
        # Se filtriamo anche per market, verifica cella
        market_hit = False
        for cell in active:
            if not isinstance(cell, dict):
                continue
            if cell.get("market_key") == m.market_key or cell.get("selection") == m.market_key:
                market_hit = True
                break
            # fallback: segnale attivo generico sulla partita
            market_hit = True
            break
        if not market_hit:
            return False
    return True


def _partition_universe(
    snaps: list[CecchinoLabHistoricalMatchSnapshot],
    markets: list[CecchinoLabHistoricalMarketResult],
    filters: dict[str, Any],
    *,
    for_performance: bool = True,
) -> tuple[
    list[CecchinoLabHistoricalMatchSnapshot],
    list[CecchinoLabHistoricalMarketResult],
    dict[int, CecchinoLabHistoricalMatchSnapshot],
]:
    elig = filters.get("eligibility_status") or ELIGIBLE_CORE
    snap_by_id = {int(s.id): s for s in snaps}
    filtered_snaps: list[CecchinoLabHistoricalMatchSnapshot] = []
    for s in snaps:
        if for_performance and s.historical_eligibility_status != elig:
            continue
        if not for_performance and filters.get("eligibility_status"):
            if s.historical_eligibility_status != filters["eligibility_status"]:
                # For exclusions we may want all non-eligible — handled separately
                pass
        if not _snap_passes_module_filters(s, filters):
            continue
        if for_performance or True:
            filtered_snaps.append(s)

    if for_performance:
        filtered_snaps = [
            s for s in filtered_snaps if s.historical_eligibility_status == elig
        ]

    allowed_ids = {int(s.id) for s in filtered_snaps}
    filtered_markets: list[CecchinoLabHistoricalMarketResult] = []
    for m in markets:
        sid = int(m.match_snapshot_id)
        if sid not in allowed_ids:
            continue
        s = snap_by_id.get(sid)
        if not _market_passes_filters(m, s, filters):
            continue
        filtered_markets.append(m)
    return filtered_snaps, filtered_markets, snap_by_id


def _cached_or_compute(
    db: Session,
    run_id: int,
    endpoint: str,
    filters: dict[str, Any],
    compute_fn,
) -> Any:
    run = _get_run(db, run_id)
    ttl = _ttl_for_run(run)
    cache_key = (
        f"{run_id}|{endpoint}|{_filters_cache_key(filters)}|"
        f"{run.matches_processed}|{run.status}|{run.updated_at.isoformat() if getattr(run, 'updated_at', None) else ''}"
    )
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit
    value = compute_fn(run)
    _cache_set(cache_key, value, ttl)
    return value


def dashboard_overview(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        perf_snaps, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )

        real_n = sum(1 for m in perf_markets if m.is_real_book_quote)
        der_n = sum(1 for m in perf_markets if m.is_derived_quote)
        unavail_n = sum(
            1 for m in perf_markets if not m.is_real_book_quote and not m.is_derived_quote
        )
        signals_activated = sum(1 for m in perf_markets if m.signal_active)
        comps = sorted({s.competition_name for s in perf_snaps if s.competition_name})

        # Module coverage
        module_coverage = _compute_module_coverage(snaps)

        # Calibration by market
        cal_by_market: dict[str, dict[str, Any]] = {}
        for mk in MARKET_ORDER:
            b = agg_bucket()
            for m in perf_markets:
                if m.market_key == mk:
                    bump_bucket_from_market(b, m, snap_by_id.get(int(m.match_snapshot_id), None) and snap_by_id[int(m.match_snapshot_id)].competition_name)
            cal_by_market[mk] = finalize_bucket(b)

        best_cal = None
        worst_cal = None
        cal_candidates = [
            (mk, v)
            for mk, v in cal_by_market.items()
            if v.get("calibration_gap") is not None and int(v.get("sample_size") or 0) >= 30
        ]
        if cal_candidates:
            best_cal = min(cal_candidates, key=lambda x: abs(float(x[1]["calibration_gap"])))[0]
            worst_cal = max(cal_candidates, key=lambda x: abs(float(x[1]["calibration_gap"])))[0]

        roi_candidates = [
            (mk, v)
            for mk, v in cal_by_market.items()
            if v.get("real_roi_pct") is not None and int(v.get("real_quote_count") or 0) >= 30
        ]
        best_roi = None
        worst_roi = None
        if roi_candidates:
            best_roi = max(roi_candidates, key=lambda x: float(x[1]["real_roi_pct"]))[0]
            worst_roi = min(roi_candidates, key=lambda x: float(x[1]["real_roi_pct"]))[0]

        progress_detail = {}
        if isinstance(run.summary_json, dict):
            progress_detail = as_dict(run.summary_json.get("progress_detail"))

        last_snap = None
        for s in reversed(snaps):
            if s.kickoff_at:
                last_snap = s
                break
        if last_snap is None and snaps:
            last_snap = snaps[-1]

        coverage_pct = None
        if run.matches_total:
            coverage_pct = round(
                100.0 * int(run.matches_eligible_core or 0) / max(int(run.matches_total), 1), 2
            )

        warnings: list[str] = []
        if _is_provisional(run):
            warnings.append("dati_provvisori_scansione_in_corso")
        if run.status == "completed_with_warnings":
            warnings.append("completed_with_warnings")
        if run.status == "failed":
            warnings.append("run_failed")
        if run.status == "cancelled":
            warnings.append("run_cancelled")

        market_summary = {
            mk: {
                "market_key": mk,
                "label": MARKET_LABELS.get(mk, mk),
                "sample_size": cal_by_market[mk]["sample_size"],
                "hit_rate": cal_by_market[mk]["hit_rate"],
                "real_roi_pct": cal_by_market[mk]["real_roi_pct"],
                "calibration_gap": cal_by_market[mk]["calibration_gap"],
                "warnings": cal_by_market[mk]["warnings"],
            }
            for mk in MARKET_ORDER
        }

        return {
            "run": _run_meta(run),
            "is_provisional": _is_provisional(run),
            "data_as_of": _utcnow().isoformat(),
            "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
            "filters": filters,
            "kpis": {
                "matches_processed": int(run.matches_processed or 0),
                "matches_eligible": len(perf_snaps),
                "coverage_pct": coverage_pct,
                "market_evaluations": len(perf_markets),
                "markets_with_real_quote": real_n,
                "markets_with_derived_quote": der_n,
                "markets_without_quote": unavail_n,
                "unavailable_quote_count": unavail_n,
                "quote_reconciliation": quote_count_reconciliation(
                    {
                        "sample_size": len(perf_markets),
                        "real_quote_count": real_n,
                        "derived_quote_count": der_n,
                        "unavailable_quote_count": unavail_n,
                    }
                ),
                "with_cecchino_probability": sum(
                    1 for m in perf_markets if m.prob_cecchino is not None
                ),
                "with_cecchino_fair_quote": sum(
                    1 for m in perf_markets if m.quota_cecchino is not None
                ),
                "with_rating": sum(1 for m in perf_markets if m.rating is not None),
                "signals_activated": signals_activated,
                "competitions_represented": len(comps),
                "best_calibrated_market": best_cal,
                "worst_calibrated_market": worst_cal,
                "best_market_by_real_roi": best_roi,
                "worst_market_by_real_roi": worst_roi,
                "note": (
                    "Prestazioni osservate su mercati indipendenti. "
                    "Nessun profitto complessivo aggregato. "
                    "Medie quote null se assenti."
                ),
            },
            "progress": {
                "matches_total": int(run.matches_total or 0),
                "matches_processed": int(run.matches_processed or 0),
                "matches_eligible_core": int(run.matches_eligible_core or 0),
                "matches_excluded": int(run.matches_excluded or 0),
                "matches_error": int(run.matches_error or 0),
                "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
                "competitions_total": progress_detail.get("competitions_total"),
                "competitions_completed": progress_detail.get("competitions_completed"),
                "current_competition": run.current_competition,
                "last_processed_match": (
                    f"{last_snap.home_team} vs {last_snap.away_team}" if last_snap else None
                ),
                "last_processed_kickoff": (
                    last_snap.kickoff_at.isoformat() if last_snap and last_snap.kickoff_at else None
                ),
                "historical_date_reached": (
                    last_snap.kickoff_at.date().isoformat()
                    if last_snap and last_snap.kickoff_at
                    else None
                ),
            },
            "module_coverage": module_coverage,
            "market_summary": market_summary,
            "warnings": warnings,
            "active_eligible_sample": len(perf_snaps),
        }

    return _cached_or_compute(db, run_id, "overview", filters, compute)


def _compute_module_coverage(
    snaps: list[CecchinoLabHistoricalMatchSnapshot],
) -> dict[str, Any]:
    total = len(snaps) or 1

    def cov(predicate) -> dict[str, Any]:
        complete = partial = unavailable = 0
        warnings: list[str] = []
        for s in snaps:
            st = predicate(s)
            if st == "complete":
                complete += 1
            elif st == "partial":
                partial += 1
            else:
                unavailable += 1
        coverage_pct = round(100.0 * complete / total, 2)
        obs = (
            "complete"
            if complete == len(snaps) and snaps
            else ("partial" if complete or partial else "unavailable")
        )
        return {
            "complete": complete,
            "partial": partial,
            "unavailable": unavailable,
            "coverage_pct": coverage_pct,
            "warnings": warnings,
            "observation_status": obs,
        }

    return {
        "historical_kpi": cov(
            lambda s: "complete"
            if as_dict(s.historical_kpi_json).get("rows")
            else ("unavailable" if not s.historical_kpi_json else "partial")
        ),
        "signals_a_f": cov(
            lambda s: _module_obs_status(
                as_dict(s.signals_json), status_keys=("observation_status",)
            )
            if s.signals_json
            else "unavailable"
        ),
        "balance": cov(
            lambda s: _module_obs_status(
                as_dict(s.balance_v5_json), status_keys=("observation_status",)
            )
            if s.balance_v5_json
            else "unavailable"
        ),
        "goal_intensity": cov(
            lambda s: (
                "complete"
                if as_dict(s.goal_intensity_compatibility_json).get("execution_status")
                == "computed"
                else (
                    "partial"
                    if as_dict(s.goal_intensity_compatibility_json).get("execution_status")
                    in ("insufficient_sample", "insufficient_ecdf_train")
                    else "unavailable"
                )
            )
        ),
        "purchasability": cov(
            lambda s: (
                "complete"
                if as_dict(s.purchasability_compatibility_json).get("execution_status")
                == "computed"
                or as_dict(s.purchasability_compatibility_json).get("markets")
                else (
                    "partial"
                    if s.purchasability_compatibility_json
                    else "unavailable"
                )
            )
        ),
    }


def dashboard_markets(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        _, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )

        rows: list[dict[str, Any]] = []
        for mk, label in KPI_V2_ROW_DEFS:
            b = agg_bucket()
            won_flags: list[bool | None] = []
            probs: list[float] = []
            outcomes: list[int] = []
            comps: set[str] = set()
            for m in perf_markets:
                if m.market_key != mk:
                    continue
                s = snap_by_id.get(int(m.match_snapshot_id))
                comp = s.competition_name if s else None
                bump_bucket_from_market(b, m, comp)
                won_flags.append(m.won)
                if m.prob_cecchino is not None and m.won is not None:
                    probs.append(float(m.prob_cecchino))
                    outcomes.append(1 if m.won else 0)
                if comp:
                    comps.add(comp)
            finalized = finalize_bucket(b)
            period = None
            line = None
            sample_m = next((m for m in perf_markets if m.market_key == mk), None)
            if sample_m:
                period = sample_m.period
                line = sample_m.line
            rows.append(
                {
                    "market_key": mk,
                    "label": label,
                    "period": period,
                    "line": line,
                    "sample_size": finalized["sample_size"],
                    "wins": finalized["won"],
                    "losses": finalized["lost"],
                    "hit_rate": finalized["hit_rate"],
                    "outcome_base_rate": finalized["hit_rate"],
                    "average_cecchino_probability": finalized["average_cecchino_probability"],
                    "median_cecchino_probability": finalized["median_cecchino_probability"],
                    "with_cecchino_probability": finalized["with_cecchino_probability"],
                    "with_cecchino_fair_quote": finalized["with_cecchino_fair_quote"],
                    "with_cecchino_quote": finalized["with_cecchino_fair_quote"],
                    "calibration_gap": finalized["calibration_gap"],
                    "brier_score": brier_score(probs, outcomes),
                    "average_rating": finalized["average_rating"],
                    "rating_available_count": finalized["with_rating"],
                    "with_rating": finalized["with_rating"],
                    "signal_active_count": finalized["with_signal_active"],
                    "matches_with_signal": finalized["with_signal_active"],
                    "real_quote_count": finalized["real_quote_count"],
                    "derived_quote_count": finalized["derived_quote_count"],
                    "unavailable_quote_count": finalized["unavailable_quote_count"],
                    "quote_count_reconciliation_ok": finalized["quote_count_reconciliation_ok"],
                    "average_real_odds": finalized["average_real_odds"],
                    "average_derived_odds": finalized["average_derived_odds"],
                    "real_profit_1u": finalized["real_profit_1u"],
                    "real_roi_pct": finalized["real_roi_pct"],
                    "synthetic_profit_1u": finalized["synthetic_profit_1u"],
                    "synthetic_roi_pct": finalized["synthetic_roi_pct"],
                    "max_losing_streak": max_losing_streak(won_flags),
                    "competitions_count": len(comps),
                    "chronological_stability": None,
                    "warnings": finalized["warnings"],
                    "confidence_status": finalized["confidence_status"],
                }
            )

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
            "filters": filters,
            "markets": rows,
            "note": (
                "Mercati indipendenti — prestazioni osservate. "
                "Non sommare i mercati tra loro. "
                "Medie quote null se assenti; unavailable conteggiato esplicitamente."
            ),
        }

    return _cached_or_compute(db, run_id, "markets", filters, compute)


def dashboard_ratings(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        _, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )
        cells: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
        for m in perf_markets:
            band = rating_band_dashboard(m.rating)
            s = snap_by_id.get(int(m.match_snapshot_id))
            bump_bucket_from_market(cells[(m.market_key, band)], m, s.competition_name if s else None)

        matrix = []
        for mk in MARKET_ORDER:
            for band in RATING_BANDS_DASHBOARD:
                b = finalize_bucket(cells.get((mk, band), agg_bucket()))
                matrix.append(
                    {
                        "market_key": mk,
                        "rating_band": band,
                        "sample_size": b["sample_size"],
                        "wins": b["won"],
                        "losses": b["lost"],
                        "hit_rate": b["hit_rate"],
                        "average_odds": b["average_real_odds"] or b["average_derived_odds"],
                        "real_quote_count": b["real_quote_count"],
                        "real_profit_1u": b["real_profit_1u"],
                        "real_roi_pct": b["real_roi_pct"],
                        "derived_quote_count": b["derived_quote_count"],
                        "synthetic_profit_1u": b["synthetic_profit_1u"],
                        "synthetic_roi_pct": b["synthetic_roi_pct"],
                        "competitions_count": b["competitions_count"],
                        "confidence_status": b["confidence_status"],
                    }
                )
        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "bands": list(RATING_BANDS_DASHBOARD),
            "matrix": matrix,
            "note": "Fascia alta non implica automaticamente performance migliore.",
        }

    return _cached_or_compute(db, run_id, "ratings", filters, compute)


def dashboard_purchasability(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        perf_snaps, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )

        by_band: dict[str, dict[str, Any]] = defaultdict(agg_bucket)
        by_market_band: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
        by_comp_band: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
        rating_x_purch: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)

        complete = partial = unavailable = 0
        for s in perf_snaps:
            purch = as_dict(s.purchasability_compatibility_json)
            st = purch.get("execution_status") or purch.get("observation_status")
            if st == "computed" or purch.get("markets"):
                complete += 1
            elif purch:
                partial += 1
            else:
                unavailable += 1

        for m in perf_markets:
            s = snap_by_id.get(int(m.match_snapshot_id))
            if not s:
                continue
            band = purchasability_band_dashboard(_purch_score_for_market(s, m.market_key))
            rb = rating_band_dashboard(m.rating)
            comp = s.competition_name or "unknown"
            bump_bucket_from_market(by_band[band], m, comp)
            bump_bucket_from_market(by_market_band[(m.market_key, band)], m, comp)
            bump_bucket_from_market(by_comp_band[(comp, band)], m, comp)
            bump_bucket_from_market(rating_x_purch[(rb, band)], m, comp)

        def fin_map(src: dict) -> list[dict[str, Any]]:
            out = []
            for key, b in sorted(src.items(), key=lambda x: str(x[0])):
                fb = finalize_bucket(b)
                if isinstance(key, tuple):
                    row = {"keys": list(key), **fb}
                else:
                    row = {"band": key, **fb}
                out.append(row)
            return out

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "bands": list(PURCH_BANDS_DASHBOARD),
            "distribution": {
                band: finalize_bucket(by_band.get(band, agg_bucket()))
                for band in PURCH_BANDS_DASHBOARD
            },
            "by_market": fin_map(by_market_band),
            "by_competition": fin_map(by_comp_band),
            "rating_x_purchasability": fin_map(rating_x_purch),
            "complete_count": complete,
            "partial_count": partial,
            "unavailable_count": unavailable,
            "profile_sample_size": len(perf_snaps),
            "execution_status": (
                "complete" if complete and not unavailable and not partial else "partial"
            ),
            "observation_status": "observational_only",
            "note": (
                "Acquistabilità osservazionale — non decisione finale di acquisto. "
                "Profitto reale e sintetico restano separati."
            ),
        }

    return _cached_or_compute(db, run_id, "purchasability", filters, compute)


def dashboard_signals(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        perf_snaps, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )
        markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]] = defaultdict(list)
        for m in perf_markets:
            markets_by_snap[int(m.match_snapshot_id)].append(m)

        models_out: list[dict[str, Any]] = []
        model_x_market: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
        model_x_comp: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
        concurrent_counts: dict[int, int] = defaultdict(int)

        for key in CECCHINO_WEIGHT_MODEL_KEYS:
            meta = model_meta_for_key(key)
            model_def = get_cecchino_weight_model(key)
            b = agg_bucket()
            won_flags: list[bool | None] = []
            matches_with = 0
            signals_activated = 0
            for s in perf_snaps:
                sigs = as_dict(s.signals_json)
                models = as_dict(sigs.get("models"))
                block = as_dict(models.get(key))
                active = as_list(block.get("active_signals"))
                settlements = as_list(block.get("settlements"))
                if active:
                    matches_with += 1
                    signals_activated += len(active)
                concurrent_counts[len(active)] += 1 if active else 0
                # Prefer settlement del modello; fallback market rows con signal
                if settlements:
                    for st in settlements:
                        if not isinstance(st, dict):
                            continue
                        mk = st.get("market_key")
                        # synthetic market-like bump
                        fake = next(
                            (m for m in markets_by_snap.get(int(s.id), []) if m.market_key == mk),
                            None,
                        )
                        if fake:
                            bump_bucket_from_market(b, fake, s.competition_name)
                            bump_bucket_from_market(
                                model_x_market[(key, mk)], fake, s.competition_name
                            )
                            bump_bucket_from_market(
                                model_x_comp[(key, s.competition_name or "unknown")],
                                fake,
                                s.competition_name,
                            )
                            won_flags.append(fake.won)
                else:
                    for m in markets_by_snap.get(int(s.id), []):
                        if not m.signal_active and key != CECCHINO_DEFAULT_WEIGHT_MODEL_KEY:
                            continue
                        if key == CECCHINO_DEFAULT_WEIGHT_MODEL_KEY and not m.signal_active:
                            continue
                        bump_bucket_from_market(b, m, s.competition_name)
                        bump_bucket_from_market(
                            model_x_market[(key, m.market_key)], m, s.competition_name
                        )
                        bump_bucket_from_market(
                            model_x_comp[(key, s.competition_name or "unknown")],
                            m,
                            s.competition_name,
                        )
                        won_flags.append(m.won)

            fb = finalize_bucket(b)
            # best/worst market
            mk_stats = [
                (mk, finalize_bucket(model_x_market[(key, mk)]))
                for mk in MARKET_ORDER
                if (key, mk) in model_x_market
            ]
            mk_roi = [
                (mk, v)
                for mk, v in mk_stats
                if v.get("real_roi_pct") is not None and int(v.get("real_quote_count") or 0) >= 10
            ]
            market_best = max(mk_roi, key=lambda x: float(x[1]["real_roi_pct"]))[0] if mk_roi else None
            market_worst = min(mk_roi, key=lambda x: float(x[1]["real_roi_pct"]))[0] if mk_roi else None
            comp_stats = [
                (c, finalize_bucket(v))
                for (k, c), v in model_x_comp.items()
                if k == key
            ]
            comp_roi = [
                (c, v)
                for c, v in comp_stats
                if v.get("real_roi_pct") is not None and int(v.get("real_quote_count") or 0) >= 10
            ]
            competition_best = (
                max(comp_roi, key=lambda x: float(x[1]["real_roi_pct"]))[0] if comp_roi else None
            )
            competition_worst = (
                min(comp_roi, key=lambda x: float(x[1]["real_roi_pct"]))[0] if comp_roi else None
            )

            models_out.append(
                {
                    "model_key": key,
                    "model_label": str(meta.get("model_label") or model_def.get("label") or key),
                    "model_short_label": str(model_def.get("short_label") or f"Modello {key}"),
                    "weights": model_weights_json(key),
                    "weights_version": str(meta.get("weights_version") or ""),
                    "is_current_model": key == CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
                    "signals_activated": signals_activated,
                    "matches_with_signal": matches_with,
                    "wins": fb["won"],
                    "losses": fb["lost"],
                    "hit_rate": fb["hit_rate"],
                    "real_quote_count": fb["real_quote_count"],
                    "real_profit": fb["real_profit_1u"],
                    "real_roi": fb["real_roi_pct"],
                    "derived_quote_count": fb["derived_quote_count"],
                    "synthetic_profit": fb["synthetic_profit_1u"],
                    "synthetic_roi": fb["synthetic_roi_pct"],
                    "average_odds": fb["average_real_odds"],
                    "max_losing_streak": max_losing_streak(won_flags),
                    "market_best": market_best,
                    "market_worst": market_worst,
                    "competition_best": competition_best,
                    "competition_worst": competition_worst,
                }
            )

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "models": models_out,
            "model_x_market": [
                {"model_key": k, "market_key": mk, **finalize_bucket(b)}
                for (k, mk), b in sorted(model_x_market.items())
            ],
            "model_x_competition": [
                {"model_key": k, "competition": c, **finalize_bucket(b)}
                for (k, c), b in sorted(model_x_comp.items())
            ],
            "concurrent_active_signals": dict(sorted(concurrent_counts.items())),
            "current_model_key": CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
            "note": "Prestazioni osservate dei modelli A–F. Nessun modello dichiarato vincitore.",
        }

    return _cached_or_compute(db, run_id, "signals", filters, compute)


def dashboard_balance(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        perf_snaps, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )
        markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]] = defaultdict(list)
        for m in perf_markets:
            markets_by_snap[int(m.match_snapshot_id)].append(m)

        pillars_out: list[dict[str, Any]] = []
        for key in BALANCE_CANONICAL_PILLARS:
            class_dist: dict[str, int] = defaultdict(int)
            score_dist: dict[str, int] = defaultdict(int)
            raw_values: list[float] = []
            complete = partial = unavailable = 0
            missing_fields: set[str] = set()
            by_market: dict[str, dict[str, Any]] = defaultdict(agg_bucket)
            by_comp: dict[str, dict[str, Any]] = defaultdict(agg_bucket)

            for s in perf_snaps:
                bal = as_dict(s.balance_v5_json)
                pillars = balance_pillars(bal)
                block = as_dict(pillars.get(key))
                obs = bal.get("observation_status") or (
                    "complete" if block else "unavailable"
                )
                if obs == "complete" and block.get("class_key"):
                    complete += 1
                elif block or bal:
                    partial += 1
                else:
                    unavailable += 1
                    missing_fields.add(key)
                ck = str(block.get("class_key") or "unknown")
                class_dist[ck] += 1
                val = block.get("value") or block.get("score")
                if val is not None:
                    try:
                        fv = float(val)
                        raw_values.append(fv)
                        score_dist[str(int(fv // 10) * 10)] += 1
                    except (TypeError, ValueError):
                        pass
                for m in markets_by_snap.get(int(s.id), []):
                    bump_bucket_from_market(by_market[m.market_key], m, s.competition_name)
                    bump_bucket_from_market(
                        by_comp[s.competition_name or "unknown"], m, s.competition_name
                    )

            pillars_out.append(
                {
                    "key": key,
                    "label": BALANCE_PILLAR_LABELS.get(key, key),
                    "raw_value_distribution": {
                        "count": len(raw_values),
                        "mean": round(sum(raw_values) / len(raw_values), 4) if raw_values else None,
                        "min": min(raw_values) if raw_values else None,
                        "max": max(raw_values) if raw_values else None,
                    },
                    "score_distribution": dict(sorted(score_dist.items())),
                    "class_distribution": dict(sorted(class_dist.items())),
                    "complete_count": complete,
                    "partial_count": partial,
                    "unavailable_count": unavailable,
                    "missing_fields": sorted(missing_fields),
                    "sample_size": len(perf_snaps),
                    "by_market": {
                        mk: finalize_bucket(b) for mk, b in sorted(by_market.items())
                    },
                    "by_competition": {
                        c: finalize_bucket(b) for c, b in sorted(by_comp.items())
                    },
                    "observation_status": (
                        "complete"
                        if complete and not unavailable
                        else ("partial" if complete or partial else "unavailable")
                    ),
                }
            )

        combinations = []
        for combo_id, p1, p2 in BALANCE_COMBINATIONS:
            groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
            for s in perf_snaps:
                bal = as_dict(s.balance_v5_json)
                pillars = balance_pillars(bal)
                c1 = str(as_dict(pillars.get(p1)).get("class_key") or "unknown")
                c2 = str(as_dict(pillars.get(p2)).get("class_key") or "unknown")
                for m in markets_by_snap.get(int(s.id), []):
                    bump_bucket_from_market(groups[(c1, c2)], m, s.competition_name)
            for (c1, c2), b in groups.items():
                fb = finalize_bucket(b)
                if int(fb["sample_size"]) < MIN_COMBO_SAMPLE:
                    continue
                combinations.append(
                    {
                        "combination_id": combo_id,
                        "conditions": {p1: c1, p2: c2},
                        "sample_size": fb["sample_size"],
                        "wins": fb["won"],
                        "losses": fb["lost"],
                        "hit_rate": fb["hit_rate"],
                        "real_profit": fb["real_profit_1u"],
                        "real_roi": fb["real_roi_pct"],
                        "synthetic_profit": fb["synthetic_profit_1u"],
                        "competitions_count": fb["competitions_count"],
                        "stability": confidence_status(int(fb["sample_size"])),
                    }
                )

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "pillars": pillars_out,
            "combinations": combinations,
            "note": (
                "Modulo osservazionale Equilibrio vs Squilibrio. "
                "Nessun consiglio gioca/non giocare."
            ),
        }

    return _cached_or_compute(db, run_id, "balance", filters, compute)


def dashboard_goal_intensity(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    GOAL_MARKETS = (
        "OVER_1_5",
        "OVER_2_5",
        "UNDER_2_5",
        "UNDER_3_5",
        "UNDER_PT_1_5",
        "OVER_PT_0_5",
        "OVER_PT_1_5",
    )

    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        perf_snaps, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )
        markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]] = defaultdict(list)
        for m in perf_markets:
            markets_by_snap[int(m.match_snapshot_id)].append(m)

        components = []
        for key in GI_PILLARS:
            class_dist: dict[str, int] = defaultdict(int)
            complete = partial = unavailable = missing = 0
            raw_values: list[float] = []
            scores: list[float] = []
            by_goal_market: dict[str, dict[str, Any]] = defaultdict(agg_bucket)
            by_comp: dict[str, dict[str, Any]] = defaultdict(agg_bucket)

            for s in perf_snaps:
                gi = as_dict(s.goal_intensity_compatibility_json)
                pillars = as_dict(gi.get("pillars"))
                block = as_dict(pillars.get(key))
                exec_st = gi.get("execution_status")
                if exec_st == "computed" and block:
                    complete += 1
                elif exec_st in ("insufficient_sample", "insufficient_ecdf_train") or (
                    gi and not block
                ):
                    partial += 1
                elif not gi:
                    unavailable += 1
                    missing += 1
                else:
                    partial += 1
                ck = str(block.get("class_key") or block.get("class") or "unknown")
                class_dist[ck] += 1
                for field, dest in (("raw_value", raw_values), ("score", scores), ("value", raw_values)):
                    v = block.get(field)
                    if v is not None:
                        try:
                            dest.append(float(v))
                        except (TypeError, ValueError):
                            pass
                for m in markets_by_snap.get(int(s.id), []):
                    if m.market_key in GOAL_MARKETS:
                        bump_bucket_from_market(
                            by_goal_market[m.market_key], m, s.competition_name
                        )
                    bump_bucket_from_market(
                        by_comp[s.competition_name or "unknown"], m, s.competition_name
                    )

            components.append(
                {
                    "key": key,
                    "label": GI_PILLAR_LABELS.get(key, key),
                    "raw_values": {
                        "count": len(raw_values),
                        "mean": round(sum(raw_values) / len(raw_values), 4) if raw_values else None,
                    },
                    "scores": {
                        "count": len(scores),
                        "mean": round(sum(scores) / len(scores), 2) if scores else None,
                    },
                    "class_distribution": dict(sorted(class_dist.items())),
                    "sample_size": len(perf_snaps),
                    "complete_count": complete,
                    "partial_count": partial,
                    "unavailable_count": unavailable,
                    "missing_count": missing,
                    "goal_markets": {
                        mk: finalize_bucket(b) for mk, b in sorted(by_goal_market.items())
                    },
                    "by_competition": {
                        c: finalize_bucket(b) for c, b in sorted(by_comp.items())
                    },
                }
            )

        # Combinazioni descrittive
        combos_spec = (
            ("produzione_ritmo", "offensive_production", "match_tempo"),
            ("produzione_solidita", "offensive_production", "defensive_solidity"),
            ("ritmo_stabilita", "match_tempo", "offensive_stability"),
            ("solidita_stabilita", "defensive_solidity", "offensive_stability"),
        )
        combinations = []
        for combo_id, p1, p2 in combos_spec:
            groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
            for s in perf_snaps:
                gi = as_dict(s.goal_intensity_compatibility_json)
                pillars = as_dict(gi.get("pillars"))
                c1 = str(
                    as_dict(pillars.get(p1)).get("class_key")
                    or as_dict(pillars.get(p1)).get("class")
                    or "unknown"
                )
                c2 = str(
                    as_dict(pillars.get(p2)).get("class_key")
                    or as_dict(pillars.get(p2)).get("class")
                    or "unknown"
                )
                for m in markets_by_snap.get(int(s.id), []):
                    if m.market_key in ("OVER_2_5", "UNDER_2_5", "OVER_1_5", "UNDER_3_5"):
                        bump_bucket_from_market(groups[(c1, c2)], m, s.competition_name)
            for (c1, c2), b in groups.items():
                fb = finalize_bucket(b)
                if int(fb["sample_size"]) < MIN_COMBO_SAMPLE:
                    continue
                combinations.append(
                    {
                        "combination_id": combo_id,
                        "conditions": {p1: c1, p2: c2},
                        "sample_size": fb["sample_size"],
                        "wins": fb["won"],
                        "losses": fb["lost"],
                        "hit_rate": fb["hit_rate"],
                        "real_profit": fb["real_profit_1u"],
                        "real_roi": fb["real_roi_pct"],
                    }
                )

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "components": components,
            "combinations": combinations,
            "note": (
                "Record parziali non nascosti. Dati mancanti non impostati a zero. "
                "Modulo osservazionale."
            ),
        }

    return _cached_or_compute(db, run_id, "goal_intensity", filters, compute)


def dashboard_competitions(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        # Filtra senza forzare eligibility per conteggi exclusi
        filtered_snaps = [s for s in snaps if _snap_passes_module_filters(s, filters)]
        if filters.get("competition"):
            filtered_snaps = [
                s for s in filtered_snaps if s.competition_name == filters["competition"]
            ]
        snap_by_id = {int(s.id): s for s in filtered_snaps}
        allowed = set(snap_by_id)
        filtered_markets = [
            m
            for m in markets
            if int(m.match_snapshot_id) in allowed
            and _market_passes_filters(m, snap_by_id.get(int(m.match_snapshot_id)), filters)
        ]

        by_comp: dict[str, list[CecchinoLabHistoricalMatchSnapshot]] = defaultdict(list)
        for s in filtered_snaps:
            by_comp[s.competition_name or "unknown"].append(s)

        items = []
        for comp, csnaps in sorted(by_comp.items()):
            cids = {int(s.id) for s in csnaps}
            cmkts = [m for m in filtered_markets if int(m.match_snapshot_id) in cids]
            eligible = [s for s in csnaps if s.historical_eligibility_status == ELIGIBLE_CORE]
            excluded = [
                s
                for s in csnaps
                if s.historical_eligibility_status != ELIGIBLE_CORE
                and not (s.error_json)
            ]
            errors = [s for s in csnaps if s.error_json or s.historical_eligibility_status == "error"]
            perf_m = [
                m
                for m in cmkts
                if snap_by_id.get(int(m.match_snapshot_id))
                and snap_by_id[int(m.match_snapshot_id)].historical_eligibility_status
                == ELIGIBLE_CORE
            ]
            real_cov = sum(1 for m in perf_m if m.is_real_book_quote)
            der_cov = sum(1 for m in perf_m if m.is_derived_quote)

            by_mk: dict[str, dict[str, Any]] = defaultdict(agg_bucket)
            for m in perf_m:
                bump_bucket_from_market(by_mk[m.market_key], m, comp)
            finalized_mk = {mk: finalize_bucket(b) for mk, b in by_mk.items()}
            roi_list = [
                (mk, v)
                for mk, v in finalized_mk.items()
                if v.get("real_roi_pct") is not None and int(v.get("real_quote_count") or 0) >= 10
            ]
            best_m = max(roi_list, key=lambda x: float(x[1]["real_roi_pct"]))[0] if roi_list else None
            worst_m = min(roi_list, key=lambda x: float(x[1]["real_roi_pct"]))[0] if roi_list else None

            excl_reasons: dict[str, int] = defaultdict(int)
            for s in excluded:
                excl_reasons[s.historical_eligibility_reason or "unknown"] += 1

            items.append(
                {
                    "competition_name": comp,
                    "country": None,
                    "processed": len(csnaps),
                    "eligible": len(eligible),
                    "excluded": len(excluded),
                    "errors": len(errors),
                    "coverage_pct": round(100.0 * len(eligible) / max(len(csnaps), 1), 2),
                    "markets_generated": len(perf_m),
                    "real_quote_coverage": round(100.0 * real_cov / max(len(perf_m), 1), 2),
                    "derived_quote_coverage": round(100.0 * der_cov / max(len(perf_m), 1), 2),
                    "best_market_by_real_roi": best_m,
                    "worst_market_by_real_roi": worst_m,
                    "real_profit_by_market": {
                        mk: v["real_profit_1u"] for mk, v in finalized_mk.items()
                    },
                    "real_roi_by_market": {
                        mk: v["real_roi_pct"] for mk, v in finalized_mk.items()
                    },
                    "exclusions_by_reason": dict(excl_reasons),
                    "module_coverage": _compute_module_coverage(csnaps),
                }
            )

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "competitions": items,
            "note": (
                "Nessun profitto globale del campionato. "
                "Mercati indipendenti non sommati."
            ),
        }

    return _cached_or_compute(db, run_id, "competitions", filters, compute)


def dashboard_timeline(
    db: Session,
    run_id: int,
    filters: dict[str, Any],
    *,
    granularity: str = "week",
    block_size: int = 50,
) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        perf_snaps, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )
        # Timeline include anche esclusi per conteggi processed/excluded
        timeline_snaps = [s for s in snaps if _snap_passes_module_filters(s, filters)]
        if filters.get("competition"):
            timeline_snaps = [
                s for s in timeline_snaps if s.competition_name == filters["competition"]
            ]
        timeline_snaps = sorted(
            timeline_snaps,
            key=lambda s: (
                s.kickoff_at or datetime.min.replace(tzinfo=timezone.utc),
                int(s.lab_match_id),
            ),
        )

        buckets: dict[str, list[CecchinoLabHistoricalMatchSnapshot]] = defaultdict(list)
        labels: dict[str, str] = {}
        ranges: dict[str, tuple[Any, Any]] = {}

        if granularity == "month":
            for s in timeline_snaps:
                if not s.kickoff_at:
                    continue
                key = s.kickoff_at.strftime("%Y-%m")
                buckets[key].append(s)
                labels[key] = key
                ranges[key] = (
                    date(s.kickoff_at.year, s.kickoff_at.month, 1),
                    s.kickoff_at.date(),
                )
        elif granularity == "chronological_block":
            bs = max(int(block_size or 50), 1)
            for i, s in enumerate(timeline_snaps):
                idx = i // bs
                key = f"block_{idx + 1}"
                buckets[key].append(s)
                labels[key] = f"Blocco {idx + 1} ({bs} partite)"
        else:  # week
            for s in timeline_snaps:
                if not s.kickoff_at:
                    continue
                iso = s.kickoff_at.isocalendar()
                key = f"{iso.year}-W{iso.week:02d}"
                buckets[key].append(s)
                labels[key] = key

        markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]] = defaultdict(list)
        for m in perf_markets:
            markets_by_snap[int(m.match_snapshot_id)].append(m)

        points = []
        for key in sorted(buckets.keys()):
            group = buckets[key]
            eligible = [s for s in group if s.historical_eligibility_status == ELIGIBLE_CORE]
            excluded = [s for s in group if s.historical_eligibility_status != ELIGIBLE_CORE]
            kickoffs = [s.kickoff_at for s in group if s.kickoff_at]
            mkts = []
            for s in eligible:
                mkts.extend(markets_by_snap.get(int(s.id), []))
            b = agg_bucket()
            for m in mkts:
                bump_bucket_from_market(b, m, None)
            fb = finalize_bucket(b)
            ratings = [m.rating for m in mkts if m.rating is not None]
            purch_scores = []
            for s in eligible:
                purch = as_dict(s.purchasability_compatibility_json)
                for row in purch.get("markets") or []:
                    if isinstance(row, dict) and row.get("score") is not None:
                        try:
                            purch_scores.append(float(row["score"]))
                        except (TypeError, ValueError):
                            pass
            bal_cov = sum(1 for s in eligible if s.balance_v5_json)
            gi_cov = sum(
                1
                for s in eligible
                if as_dict(s.goal_intensity_compatibility_json).get("execution_status")
                == "computed"
            )
            by_mk: dict[str, dict[str, Any]] = defaultdict(agg_bucket)
            for m in mkts:
                bump_bucket_from_market(by_mk[m.market_key], m, None)
            finalized_mk = {mk: finalize_bucket(b) for mk, b in by_mk.items()}
            points.append(
                {
                    "period_key": key,
                    "period_label": labels.get(key, key),
                    "historical_date_from": min(kickoffs).date().isoformat() if kickoffs else None,
                    "historical_date_to": max(kickoffs).date().isoformat() if kickoffs else None,
                    "processed": len(group),
                    "eligible": len(eligible),
                    "excluded": len(excluded),
                    "hit_rate": fb["hit_rate"],
                    "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
                    "average_purchasability": (
                        round(sum(purch_scores) / len(purch_scores), 2) if purch_scores else None
                    ),
                    "signals_count": sum(1 for m in mkts if m.signal_active),
                    "balance_coverage": round(100.0 * bal_cov / max(len(eligible), 1), 2),
                    "goal_intensity_coverage": round(100.0 * gi_cov / max(len(eligible), 1), 2),
                    "real_profit_by_market": {
                        mk: v["real_profit_1u"] for mk, v in finalized_mk.items()
                    },
                    "real_roi_by_market": {
                        mk: v["real_roi_pct"] for mk, v in finalized_mk.items()
                    },
                }
            )

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "granularity": granularity,
            "block_size": block_size,
            "points": points,
            "note": "Asse temporale = kickoff storico, non data di scansione.",
        }

    return _cached_or_compute(
        db, run_id, f"timeline:{granularity}:{block_size}", filters, compute
    )


def dashboard_patterns(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        markets = _load_markets(db, run_id)
        _, perf_markets, snap_by_id = _partition_universe(
            snaps, markets, filters, for_performance=True
        )
        raw = build_combined_patterns(perf_markets, snap_by_id)
        grouped = group_patterns_for_dashboard(raw)
        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
            "filters": filters,
            "positive": grouped["positive"],
            "negative": grouped["negative"],
            "watchlist": grouped["watchlist"],
            "unstable": grouped["unstable"],
            "diagnostics": grouped.get("diagnostics") or [],
            "status_thresholds": raw.get("status_thresholds"),
            "note": (
                "Pattern market-specific, candidato da verificare. "
                "Diagnostiche assenze dati separate. "
                "Nessuna modifica automatica alle formule. "
                "Nessuna giocata automatica suggerita."
            ),
        }

    return _cached_or_compute(db, run_id, "patterns", filters, compute)


def dashboard_exclusions(db: Session, run_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    REASON_META = {
        "insufficient_history": ("Storico insufficiente", True, False, "eligibility"),
        "excluded_insufficient_history": ("Storico insufficiente", True, False, "eligibility"),
        "zero_probability": ("Probabilità zero", False, True, "cecchino"),
        "missing_data": ("Dati mancanti", False, True, "data_quality"),
        "invalid_identity": ("Identità non valida", False, True, "identity"),
        "leakage_blocked": ("Leakage bloccato", True, False, "anti_leakage"),
        "calculation_error": ("Errore di calcolo", False, True, "engine"),
        "missing_result": ("Risultato mancante", False, True, "settlement"),
    }

    def compute(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
        snaps = _load_snapshots_lean(db, run_id)
        excluded = [
            s
            for s in snaps
            if s.historical_eligibility_status != ELIGIBLE_CORE
            and _snap_passes_module_filters(s, {**filters, "balance_class": None, "goal_intensity_status": None, "purchasability_status": None})
        ]
        if filters.get("competition"):
            excluded = [s for s in excluded if s.competition_name == filters["competition"]]

        by_reason: dict[str, list[CecchinoLabHistoricalMatchSnapshot]] = defaultdict(list)
        for s in excluded:
            code = s.historical_eligibility_reason or s.historical_eligibility_status or "unknown"
            by_reason[code].append(s)

        total = len(excluded) or 1
        items = []
        for code, group in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            meta = REASON_META.get(code)
            if meta:
                label, expected, quality, module = meta
            else:
                label = code
                expected = False
                quality = True
                module = "unknown"
            kickoffs = [s.kickoff_at for s in group if s.kickoff_at]
            comps = sorted({s.competition_name for s in group if s.competition_name})
            chrono: dict[str, int] = defaultdict(int)
            for s in group:
                if s.kickoff_at:
                    chrono[s.kickoff_at.strftime("%Y-%m")] += 1
            items.append(
                {
                    "reason_code": code,
                    "label": label,
                    "total": len(group),
                    "percentage": round(100.0 * len(group) / total, 2),
                    "competitions": comps,
                    "chronological_distribution": dict(sorted(chrono.items())),
                    "first_occurrence": min(kickoffs).isoformat() if kickoffs else None,
                    "last_occurrence": max(kickoffs).isoformat() if kickoffs else None,
                    "related_module": module,
                    "is_expected": expected,
                    "is_data_quality_problem": quality,
                }
            )

        return {
            "run_id": int(run.id),
            "is_provisional": _is_provisional(run),
            "filters": filters,
            "total_excluded": len(excluded),
            "items": items,
            "note": "Le esclusioni non contaminano le metriche di performance.",
        }

    return _cached_or_compute(db, run_id, "exclusions", filters, compute)


def list_dashboard_matches(
    db: Session,
    run_id: int,
    filters: dict[str, Any],
    *,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "kickoff_at",
    sort_order: str = "asc",
) -> dict[str, Any]:
    run = _get_run(db, run_id)
    snaps = _load_snapshots_lean(db, run_id)
    markets = _load_markets(db, run_id)
    markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]] = defaultdict(list)
    for m in markets:
        markets_by_snap[int(m.match_snapshot_id)].append(m)

    # Per explorer: eligibility_status dal filtro (default eligible_core, ma può essere all)
    elig_filter = filters.get("eligibility_status")
    rows = []
    for s in snaps:
        if not _snap_passes_module_filters(s, filters):
            continue
        if elig_filter and elig_filter != "all":
            if s.historical_eligibility_status != elig_filter:
                continue
        mkts = markets_by_snap.get(int(s.id), [])
        # market-level filters: keep snap if any market matches (or no market filter)
        if filters.get("market_key") or filters.get("rating_band") or filters.get("quote_quality") or filters.get("signal_active") is not None or filters.get("purchasability_band") or filters.get("signal_model"):
            if not any(_market_passes_filters(m, s, filters) for m in mkts) and mkts:
                # if no markets and filters require markets, skip eligible with no markets
                if any(
                    filters.get(k)
                    for k in (
                        "market_key",
                        "rating_band",
                        "quote_quality",
                        "purchasability_band",
                        "signal_model",
                    )
                ) or filters.get("signal_active") is not None:
                    continue

        highest = None
        highest_rating = None
        for m in mkts:
            if m.rating is not None and (highest_rating is None or m.rating > highest_rating):
                highest_rating = int(m.rating)
                highest = m.market_key
        sigs = as_dict(s.signals_json)
        models = as_dict(sigs.get("models"))
        active_models = [
            k
            for k in CECCHINO_WEIGHT_MODEL_KEYS
            if as_list(as_dict(models.get(k)).get("active_signals"))
        ]
        bal = as_dict(s.balance_v5_json)
        bal_class, _ = structural_class(bal.get("structural_summary") if bal else None)
        gi = as_dict(s.goal_intensity_compatibility_json)
        purch = as_dict(s.purchasability_compatibility_json)
        won = [m.market_key for m in mkts if m.won is True]
        lost = [m.market_key for m in mkts if m.won is False]
        real_n = sum(1 for m in mkts if m.is_real_book_quote)
        der_n = sum(1 for m in mkts if m.is_derived_quote)
        result = as_dict(s.result_json)
        ft = as_dict(result.get("fulltime") or result.get("ft"))
        rows.append(
            {
                "snapshot_id": int(s.id),
                "lab_match_id": int(s.lab_match_id),
                "date": s.kickoff_at.isoformat() if s.kickoff_at else None,
                "competition": s.competition_name,
                "home_team": s.home_team,
                "away_team": s.away_team,
                "result": {
                    "ft_home": ft.get("home") or result.get("ft_home"),
                    "ft_away": ft.get("away") or result.get("ft_away"),
                    "ft_result": result.get("ft_result"),
                },
                "eligibility": s.historical_eligibility_status,
                "exclusion_reason": s.historical_eligibility_reason,
                "highest_rating_market": highest,
                "highest_rating": highest_rating,
                "purchasability_summary": {
                    "execution_status": purch.get("execution_status"),
                    "markets_count": len(as_list(purch.get("markets"))),
                },
                "active_signal_models": active_models,
                "balance_class": bal_class,
                "goal_intensity_status": gi.get("execution_status") or "unavailable",
                "quote_coverage": {"real": real_n, "derived": der_n, "total": len(mkts)},
                "won_markets": won,
                "lost_markets": lost,
            }
        )

    reverse = sort_order.lower() == "desc"
    if sort_by == "rating":
        rows.sort(key=lambda r: r.get("highest_rating") or -1, reverse=reverse)
    elif sort_by == "competition":
        rows.sort(key=lambda r: r.get("competition") or "", reverse=reverse)
    else:
        rows.sort(key=lambda r: r.get("date") or "", reverse=reverse)

    page = rows[offset : offset + limit]
    return {
        "run_id": int(run.id),
        "is_provisional": _is_provisional(run),
        "filters": filters,
        "items": page,
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


def get_dashboard_match_detail(db: Session, run_id: int, snapshot_id: int) -> dict[str, Any]:
    run = _get_run(db, run_id)
    snap = db.get(CecchinoLabHistoricalMatchSnapshot, snapshot_id)
    if not snap or int(snap.run_id) != int(run_id):
        raise CecchinoLabImportError(
            "snapshot_not_found", "Snapshot non trovato per questo run", status_code=404
        )
    markets = list(
        db.scalars(
            select(CecchinoLabHistoricalMarketResult).where(
                CecchinoLabHistoricalMarketResult.match_snapshot_id == snapshot_id
            )
        ).all()
    )
    cecchino = as_dict(snap.cecchino_output_json)
    result = as_dict(snap.result_json)
    ft = as_dict(result.get("fulltime") or result.get("ft"))
    ht = as_dict(result.get("halftime") or result.get("ht"))
    settlement = [
        {
            "market_key": m.market_key,
            "market_label": m.market_label,
            "won": m.won,
            "is_real_book_quote": m.is_real_book_quote,
            "is_derived_quote": m.is_derived_quote,
            "quota_book": float(m.quota_book) if m.quota_book is not None else None,
            "quota_cecchino": float(m.quota_cecchino) if m.quota_cecchino is not None else None,
            "prob_cecchino": float(m.prob_cecchino) if m.prob_cecchino is not None else None,
            "rating": m.rating,
            "edge_pct": float(m.edge_pct) if m.edge_pct is not None else None,
            "signal_active": m.signal_active,
            "profit_1u_real": float(m.profit_1u_real) if m.profit_1u_real is not None else None,
            "profit_1u_synthetic": (
                float(m.profit_1u_synthetic) if m.profit_1u_synthetic is not None else None
            ),
            "profit_category": m.profit_category,
            "evaluation_status": m.evaluation_status,
        }
        for m in markets
    ]
    return {
        "run_id": int(run.id),
        "snapshot_id": int(snap.id),
        "identity": {
            "lab_match_id": int(snap.lab_match_id),
            "competition": snap.competition_name,
            "season_label": snap.season_label,
            "kickoff_at": snap.kickoff_at.isoformat() if snap.kickoff_at else None,
            "home_team": snap.home_team,
            "away_team": snap.away_team,
            "eligibility": snap.historical_eligibility_status,
            "exclusion_reason": snap.historical_eligibility_reason,
        },
        "prematch": {
            "contexts": as_dict(snap.input_snapshot_json),
            "picchetti": as_dict(cecchino.get("picchetti")),
            "cecchino_final": as_dict(cecchino.get("final")),
            "goal_markets": as_dict(cecchino.get("goal_markets")),
            "historical_kpi": as_dict(snap.historical_kpi_json),
            "signal_models": as_dict(snap.signals_json),
            "balance": as_dict(snap.balance_v5_json),
            "goal_intensity": as_dict(snap.goal_intensity_compatibility_json),
            "purchasability": as_dict(snap.purchasability_compatibility_json),
            "quote_sources": as_dict(snap.quote_sources_json),
            "module_availability": as_dict(snap.module_availability_json),
            "pre_match_hash": snap.pre_match_payload_sha256,
            "locked_at": snap.pre_match_locked_at.isoformat() if snap.pre_match_locked_at else None,
            "label": "Analisi conosciuta prima della partita",
        },
        "result_after_lock": {
            "ft": ft or {
                "home": result.get("ft_home"),
                "away": result.get("ft_away"),
                "result": result.get("ft_result"),
            },
            "ht": ht or {
                "home": result.get("ht_home"),
                "away": result.get("ht_away"),
                "result": result.get("ht_result"),
            },
            "settlement": settlement,
            "settlement_summary": as_dict(snap.settlement_summary_json),
            "label": "Risultato collegato dopo il blocco",
        },
    }
