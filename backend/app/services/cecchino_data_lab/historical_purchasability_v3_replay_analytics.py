"""Analytics read-only sui risultati persistiti del Replay Acquistabilità V3 (STEP 3C.1).

Nessun ricalcolo formula, nessuna scrittura DB, nessun full ORM load.
"""

from __future__ import annotations

import math
import statistics
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.models.cecchino_lab_purchasability_v3_replay_run import (
    COMPLETED_STATUSES,
    CecchinoLabPurchasabilityV3ReplayRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_analytics_agg import (
    classify_purchasability_gate,
)

PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION = (
    "cecchino_lab_purchasability_v3_analytics_v1"
)
ANALYTICS_CACHE_TTL_S = 300
CACHE_KIND_SUMMARY = "summary"
CACHE_KIND_EXPORT_ANALYSIS = "export_analysis"
CACHE_KIND_EXPORT_FULL = "export_full"
CACHE_MAX_ENTRIES = 64
REPLAY_NOT_COMPLETED_MSG = (
    "Il replay deve essere completato prima di generare analytics o report."
)
CI_MIN_SAMPLE = 30
KEYSET_BATCH = 500
V2_SNAPSHOT_BATCH = 100

V3_MARKET_ORDER: tuple[str, ...] = (
    "HOME",
    "DRAW",
    "AWAY",
    "OVER_2_5",
    "UNDER_2_5",
    "ONE_X",
    "X_TWO",
    "ONE_TWO",
)
FAMILY_MATCH_WINNER_FT = "MATCH_WINNER_FT"
FAMILY_GOALS_FT_2_5 = "GOALS_FT_2_5"
FAMILY_DOUBLE_CHANCE = "DOUBLE_CHANCE"
FAMILY_CANONICAL: dict[str, tuple[str, ...]] = {
    FAMILY_MATCH_WINNER_FT: ("HOME", "DRAW", "AWAY"),
    FAMILY_GOALS_FT_2_5: ("OVER_2_5", "UNDER_2_5"),
    FAMILY_DOUBLE_CHANCE: ("ONE_X", "X_TWO", "ONE_TWO"),
}
MARKET_TO_FAMILY: dict[str, str] = {
    mk: fam for fam, markets in FAMILY_CANONICAL.items() for mk in markets
}
THRESHOLDS: tuple[int, ...] = (20, 40, 60, 70, 80, 90)
SCORE_BANDS: tuple[str, ...] = (
    "0-19",
    "20-39",
    "40-59",
    "60-79",
    "80-89",
    "90-100",
)
VQ_BANDS: tuple[str, ...] = ("0-19", "20-39", "40-59", "60-79", "80-100")
PENALTY_FIELDS: tuple[str, ...] = (
    "probability_risk_penalty",
    "opposite_market_pressure_penalty",
    "extreme_divergence_penalty",
    "family_ambiguity_penalty",
    "quote_quality_penalty",
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
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def clear_purchasability_v3_analytics_cache() -> None:
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
    replay_id: int,
    kind: str,
    completed_at: Any,
    formula_version: str | None,
    runtime_commit: str | None,
) -> str:
    return "|".join(
        [
            str(int(replay_id)),
            kind,
            PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
            _iso(completed_at) or "",
            str(formula_version or ""),
            str(runtime_commit or ""),
        ]
    )


def classify_calc_bucket(row: dict[str, Any]) -> str:
    """Classificazione aggregata: gate ha priorità su not_applicable della formula."""
    status = str(row.get("calculation_status") or "")
    gate = str(row.get("gate_status") or "")
    score = row.get("score")
    if status == "error":
        return "error"
    if status in ("source_not_replayable", "unavailable"):
        return "unavailable"
    if gate and gate != "passed" and score is None:
        return "gate_failed"
    if score is not None:
        return "scored"
    if status == "not_applicable":
        return "not_applicable"
    if status in ("available", "partial"):
        return "unavailable"
    return "unclassified"


def score_band_for(score: Any) -> str | None:
    s = _i(score)
    if s is None:
        return None
    if s < 20:
        return "0-19"
    if s < 40:
        return "20-39"
    if s < 60:
        return "40-59"
    if s < 80:
        return "60-79"
    if s < 90:
        return "80-89"
    return "90-100"


def vq_band_for(value: Any) -> str | None:
    s = _f(value)
    if s is None:
        return None
    if s < 20:
        return "0-19"
    if s < 40:
        return "20-39"
    if s < 60:
        return "40-59"
    if s < 80:
        return "60-79"
    return "80-100"


def penalty_band_for(value: Any) -> str | None:
    v = _f(value)
    if v is None:
        return None
    if v == 0:
        return "0"
    if v <= 5:
        return ">0-5"
    if v <= 10:
        return ">5-10"
    if v <= 20:
        return ">10-20"
    if v <= 35:
        return ">20-35"
    return ">35"


def total_penalty_band_for(value: Any) -> str | None:
    v = _f(value)
    if v is None:
        return None
    if v < 10:
        return "0-9.99"
    if v < 20:
        return "10-19.99"
    if v < 30:
        return "20-29.99"
    if v < 40:
        return "30-39.99"
    if v < 50:
        return "40-49.99"
    return "50+"


def competition_sample_flag(n: int) -> str:
    if n < 30:
        return "insufficient"
    if n < 100:
        return "small"
    if n < 300:
        return "medium"
    return "large"


def wilson_ci95(wins: int, n: int) -> tuple[float | None, float | None]:
    if n < CI_MIN_SAMPLE:
        return None, None
    if n <= 0:
        return None, None
    z = 1.96
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    low = (centre - margin) / denom
    high = (centre + margin) / denom
    return round(max(0.0, low) * 100.0, 4), round(min(1.0, high) * 100.0, 4)


def mean_profit_ci95(
    profits: list[float],
) -> tuple[float | None, float | None, float | None]:
    n = len(profits)
    if n < CI_MIN_SAMPLE:
        return None, None, None
    mean = statistics.fmean(profits)
    if n == 1:
        return round(mean, 6), round(mean, 6), round(mean, 6)
    sd = statistics.stdev(profits)
    se = sd / math.sqrt(n)
    margin = 1.96 * se
    return round(mean, 6), round(mean - margin, 6), round(mean + margin, 6)


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if p <= 0:
        return sorted_vals[0]
    if p >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def build_performance_stats(
    rows: list[dict[str, Any]],
    *,
    profit_field: str,
    odds_field: str = "quota_book",
) -> dict[str, Any]:
    profits: list[float] = []
    odds: list[float] = []
    scores: list[float] = []
    values: list[float] = []
    qualities: list[float] = []
    penalties: list[float] = []
    wins = 0
    losses = 0
    void_or_zero = 0
    won_null = 0
    settled_with_won = 0

    for r in rows:
        pf = _f(r.get(profit_field))
        if pf is None:
            continue
        profits.append(pf)
        od = _f(r.get(odds_field))
        if od is not None:
            odds.append(od)
        sc = _f(r.get("score"))
        if sc is not None:
            scores.append(sc)
        vs = _f(r.get("value_score"))
        if vs is not None:
            values.append(vs)
        qs = _f(r.get("quality_score"))
        if qs is not None:
            qualities.append(qs)
        tp = _f(r.get("total_penalty"))
        if tp is not None:
            penalties.append(tp)
        won = r.get("won")
        if won is True:
            wins += 1
            settled_with_won += 1
        elif won is False:
            losses += 1
            settled_with_won += 1
        else:
            won_null += 1
        if pf == 0.0:
            void_or_zero += 1

    stake = len(profits)
    if stake == 0:
        return {
            "stake_count": 0,
            "profit_units": None,
            "roi_pct": None,
            "wins": 0,
            "losses": 0,
            "void_or_zero_profit": 0,
            "won_null": 0,
            "hit_rate_pct": None,
            "average_odds": None,
            "median_odds": None,
            "average_score": None,
            "average_value_score": None,
            "average_quality_score": None,
            "average_total_penalty": None,
            "ci_method": None,
            "roi_ci95_low": None,
            "roi_ci95_high": None,
            "hit_rate_ci95_low": None,
            "hit_rate_ci95_high": None,
            "ci_null_reason": "insufficient_sample",
        }

    profit_units = sum(profits)
    roi_pct = (profit_units / stake) * 100.0
    hit_rate = (wins / settled_with_won * 100.0) if settled_with_won else None
    mean_p, low_p, high_p = mean_profit_ci95(profits)
    hit_low, hit_high = wilson_ci95(wins, settled_with_won)
    ci_ok = stake >= CI_MIN_SAMPLE
    return {
        "stake_count": stake,
        "profit_units": round(profit_units, 6),
        "roi_pct": round(roi_pct, 6),
        "wins": wins,
        "losses": losses,
        "void_or_zero_profit": void_or_zero,
        "won_null": won_null,
        "hit_rate_pct": round(hit_rate, 6) if hit_rate is not None else None,
        "average_odds": round(statistics.fmean(odds), 6) if odds else None,
        "median_odds": round(_median(odds) or 0, 6) if odds else None,
        "average_score": round(statistics.fmean(scores), 6) if scores else None,
        "average_value_score": round(statistics.fmean(values), 6) if values else None,
        "average_quality_score": (
            round(statistics.fmean(qualities), 6) if qualities else None
        ),
        "average_total_penalty": (
            round(statistics.fmean(penalties), 6) if penalties else None
        ),
        "ci_method": "wilson_hit_rate_and_normal_mean_profit" if ci_ok else None,
        "roi_ci95_low": round(low_p * 100.0, 6) if low_p is not None else None,
        "roi_ci95_high": round(high_p * 100.0, 6) if high_p is not None else None,
        "hit_rate_ci95_low": hit_low,
        "hit_rate_ci95_high": hit_high,
        "ci_null_reason": None if ci_ok else "insufficient_sample",
    }


def ensure_replay_ready_for_analytics(
    db: Session, replay_id: int
) -> CecchinoLabPurchasabilityV3ReplayRun:
    replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, int(replay_id))
    if replay is None:
        raise CecchinoLabImportError(
            "replay_not_found",
            f"Replay Acquistabilità V3 non trovato: {replay_id}",
            status_code=404,
        )
    if str(replay.status) not in COMPLETED_STATUSES:
        raise CecchinoLabImportError(
            "replay_not_completed",
            REPLAY_NOT_COMPLETED_MSG,
            status_code=409,
            details={"replay_id": int(replay_id), "status": str(replay.status)},
        )
    return replay


LEAN_COLUMNS: tuple[str, ...] = (
    "replay_run_id",
    "source_scan_run_id",
    "source_snapshot_id",
    "lab_match_id",
    "competition_name",
    "kickoff_at",
    "chronological_order",
    "market_key",
    "market_family",
    "quote_source",
    "quote_quality",
    "performance_type",
    "is_real_book_quote",
    "is_derived_quote",
    "derivation_method",
    "quota_book",
    "quota_cecchino",
    "prob_book_fair",
    "prob_cecchino",
    "edge_pct",
    "vantaggio_prob",
    "calculation_status",
    "gate_status",
    "gate_reason_codes_json",
    "score",
    "raw_score",
    "score_class",
    "value_score",
    "quality_score",
    "total_penalty",
    "probability_risk_penalty",
    "opposite_market_pressure_penalty",
    "extreme_divergence_penalty",
    "family_ambiguity_penalty",
    "quote_quality_penalty",
    "opposite_market_key",
    "selected_is_family_edge_leader",
    "family_edge_gap_or_deficit",
    "won",
    "profit_1u_real",
    "profit_1u_synthetic",
    "performance_evaluation_status",
    "result_reason",
    "pre_match_only",
    "post_match_fields_excluded",
    "formula_payload_sha256",
    "source_pre_match_payload_sha256",
    "source_pre_match_locked_at",
    "formula_payload_fields_json",
    "reason_codes_json",
    "warnings_json",
)


def _mapping_to_lean(m: Any) -> dict[str, Any]:
    if hasattr(m, "_mapping"):
        raw = dict(m._mapping)
    elif isinstance(m, dict):
        raw = m
    else:
        raw = {c: getattr(m, c, None) for c in LEAN_COLUMNS}
    out: dict[str, Any] = {}
    for k in LEAN_COLUMNS:
        if k in raw:
            out[k] = raw[k]
    # alias stabile
    out["replay_id"] = out.get("replay_run_id")
    return out


def iter_lean_replay_result_rows(
    db: Session, replay_id: int
) -> Iterator[dict[str, Any]]:
    """Keyset pagination transaction-safe su colonne scalari."""
    R = CecchinoLabPurchasabilityV3ReplayResult
    cols = [getattr(R, c) for c in LEAN_COLUMNS if hasattr(R, c)]
    last_snap: int | None = None
    last_mk: str | None = None
    while True:
        stmt = (
            select(*cols)
            .where(R.replay_run_id == int(replay_id))
            .order_by(R.source_snapshot_id.asc(), R.market_key.asc())
            .limit(KEYSET_BATCH)
        )
        if last_snap is not None and last_mk is not None:
            stmt = stmt.where(
                (R.source_snapshot_id > last_snap)
                | (
                    (R.source_snapshot_id == last_snap)
                    & (R.market_key > last_mk)
                )
            )
        rows = list(db.execute(stmt).all())
        if not rows:
            break
        for r in rows:
            lean = _mapping_to_lean(r)
            yield lean
            last_snap = int(lean["source_snapshot_id"])
            last_mk = str(lean["market_key"])
        if len(rows) < KEYSET_BATCH:
            break


def iter_compact_export_rows(
    rows: list[dict[str, Any]] | Iterator[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    for r in rows:
        yield {
            "replay_id": r.get("replay_id") or r.get("replay_run_id"),
            "source_scan_run_id": r.get("source_scan_run_id"),
            "source_snapshot_id": r.get("source_snapshot_id"),
            "lab_match_id": r.get("lab_match_id"),
            "competition_name": r.get("competition_name"),
            "kickoff_at": _iso(r.get("kickoff_at")),
            "market_key": r.get("market_key"),
            "market_family": r.get("market_family")
            or MARKET_TO_FAMILY.get(str(r.get("market_key") or "")),
            "quote_source": r.get("quote_source"),
            "quote_quality": r.get("quote_quality"),
            "performance_type": r.get("performance_type"),
            "is_real_book_quote": bool(r.get("is_real_book_quote")),
            "is_derived_quote": bool(r.get("is_derived_quote")),
            "quota_book": _f(r.get("quota_book")),
            "quota_cecchino": _f(r.get("quota_cecchino")),
            "prob_book_fair": _f(r.get("prob_book_fair")),
            "prob_cecchino": _f(r.get("prob_cecchino")),
            "edge_pct": _f(r.get("edge_pct")),
            "vantaggio_prob": _f(r.get("vantaggio_prob")),
            "calculation_status": r.get("calculation_status"),
            "gate_status": r.get("gate_status"),
            "score": _i(r.get("score")),
            "score_class": r.get("score_class"),
            "value_score": _f(r.get("value_score")),
            "quality_score": _f(r.get("quality_score")),
            "total_penalty": _f(r.get("total_penalty")),
            "probability_risk_penalty": _f(r.get("probability_risk_penalty")),
            "opposite_market_pressure_penalty": _f(
                r.get("opposite_market_pressure_penalty")
            ),
            "extreme_divergence_penalty": _f(r.get("extreme_divergence_penalty")),
            "family_ambiguity_penalty": _f(r.get("family_ambiguity_penalty")),
            "quote_quality_penalty": _f(r.get("quote_quality_penalty")),
            "opposite_market_key": r.get("opposite_market_key"),
            "selected_is_family_edge_leader": r.get("selected_is_family_edge_leader"),
            "family_edge_gap_or_deficit": _f(r.get("family_edge_gap_or_deficit")),
            "won": r.get("won"),
            "profit_1u_real": _f(r.get("profit_1u_real")),
            "profit_1u_synthetic": _f(r.get("profit_1u_synthetic")),
            "performance_evaluation_status": r.get("performance_evaluation_status"),
        }


def _is_scored(row: dict[str, Any]) -> bool:
    return (
        row.get("score") is not None
        and str(row.get("gate_status") or "") == "passed"
        and str(row.get("calculation_status") or "") != "error"
    )


def _is_gate_failed(row: dict[str, Any]) -> bool:
    return classify_calc_bucket(row) == "gate_failed"


def _is_unavailable(row: dict[str, Any]) -> bool:
    return classify_calc_bucket(row) == "unavailable"


def _real_perf_ready(row: dict[str, Any]) -> bool:
    return bool(row.get("is_real_book_quote")) and _f(row.get("profit_1u_real")) is not None


def _synth_perf_ready(row: dict[str, Any]) -> bool:
    return bool(row.get("is_derived_quote")) and _f(row.get("profit_1u_synthetic")) is not None


def _tie_key(row: dict[str, Any], family: str) -> tuple:
    canon = FAMILY_CANONICAL.get(family, ())
    mk = str(row.get("market_key") or "")
    try:
        order = canon.index(mk)
    except ValueError:
        order = 999
    return (
        -(_f(row.get("score")) or -1.0),
        -(_f(row.get("quality_score")) or -1.0),
        -(_f(row.get("value_score")) or -1.0),
        -(_f(row.get("edge_pct")) or -1e9),
        order,
    )


def build_family_decisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_snap_fam: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    snap_meta: dict[int, dict[str, Any]] = {}
    snap_families_seen: dict[int, set[str]] = defaultdict(set)

    for r in rows:
        mk = str(r.get("market_key") or "")
        fam = str(r.get("market_family") or MARKET_TO_FAMILY.get(mk) or "")
        if fam not in FAMILY_CANONICAL:
            continue
        sid = int(r.get("source_snapshot_id") or 0)
        snap_families_seen[sid].add(fam)
        snap_meta.setdefault(
            sid,
            {
                "replay_id": r.get("replay_id") or r.get("replay_run_id"),
                "competition_name": r.get("competition_name"),
                "kickoff_at": r.get("kickoff_at"),
            },
        )
        if _is_scored(r):
            by_snap_fam[(sid, fam)].append(r)

    decisions: list[dict[str, Any]] = []
    for sid, families in snap_families_seen.items():
        meta = snap_meta.get(sid, {})
        for fam in FAMILY_CANONICAL:
            if fam not in families and (sid, fam) not in by_snap_fam:
                # snapshot senza mercati di quella famiglia: skip
                continue
            cands = by_snap_fam.get((sid, fam), [])
            if not cands:
                decisions.append(
                    {
                        "replay_id": meta.get("replay_id"),
                        "snapshot_id": sid,
                        "family": fam,
                        "selected_market": None,
                        "score": None,
                        "score_class": None,
                        "value_score": None,
                        "quality_score": None,
                        "total_penalty": None,
                        "edge_pct": None,
                        "quota_book": None,
                        "is_real_book_quote": None,
                        "is_derived_quote": None,
                        "won": None,
                        "profit_1u_real": None,
                        "profit_1u_synthetic": None,
                        "candidates_available": 0,
                        "tie_count": 0,
                        "tie_break_used": None,
                        "no_selection_reason": "no_scored_candidates",
                        "diagnostic_family_selection": True,
                        "not_operational_strategy": True,
                        "competition_name": meta.get("competition_name"),
                        "kickoff_at": _iso(meta.get("kickoff_at")),
                    }
                )
                continue
            ranked = sorted(cands, key=lambda x: _tie_key(x, fam))
            best = ranked[0]
            best_score = _f(best.get("score"))
            ties = [
                c
                for c in ranked
                if _f(c.get("score")) == best_score
            ]
            tie_break = None
            if len(ties) > 1:
                tie_break = (
                    "score_desc;quality_score_desc;value_score_desc;"
                    "edge_pct_desc;canonical_market_order"
                )
            use_synth = fam == FAMILY_DOUBLE_CHANCE
            decisions.append(
                {
                    "replay_id": meta.get("replay_id"),
                    "snapshot_id": sid,
                    "family": fam,
                    "selected_market": best.get("market_key"),
                    "score": _i(best.get("score")),
                    "score_class": best.get("score_class"),
                    "value_score": _f(best.get("value_score")),
                    "quality_score": _f(best.get("quality_score")),
                    "total_penalty": _f(best.get("total_penalty")),
                    "edge_pct": _f(best.get("edge_pct")),
                    "quota_book": _f(best.get("quota_book")),
                    "is_real_book_quote": bool(best.get("is_real_book_quote")),
                    "is_derived_quote": bool(best.get("is_derived_quote")),
                    "won": best.get("won"),
                    "profit_1u_real": (
                        None if use_synth else _f(best.get("profit_1u_real"))
                    ),
                    "profit_1u_synthetic": (
                        _f(best.get("profit_1u_synthetic")) if use_synth else None
                    ),
                    "candidates_available": len(cands),
                    "tie_count": max(0, len(ties) - 1),
                    "tie_break_used": tie_break,
                    "no_selection_reason": None,
                    "diagnostic_family_selection": True,
                    "not_operational_strategy": True,
                    "competition_name": meta.get("competition_name"),
                    "kickoff_at": _iso(meta.get("kickoff_at")),
                }
            )
    decisions.sort(key=lambda d: (int(d["snapshot_id"]), str(d["family"])))
    return decisions


def build_temporal_halves_by_competition(
    rows: list[dict[str, Any]],
) -> dict[str, dict[int, str]]:
    """Split deterministico per campionato a livello snapshot."""
    by_comp: dict[str, dict[int, tuple]] = defaultdict(dict)
    for r in rows:
        comp = str(r.get("competition_name") or "UNKNOWN")
        sid = int(r.get("source_snapshot_id") or 0)
        if sid in by_comp[comp]:
            continue
        by_comp[comp][sid] = (
            r.get("kickoff_at") or datetime.min.replace(tzinfo=timezone.utc),
            int(r.get("chronological_order") or 0),
            sid,
        )
    out: dict[str, dict[int, str]] = {}
    for comp, snaps in by_comp.items():
        ordered = sorted(snaps.items(), key=lambda kv: kv[1])
        n = len(ordered)
        first_n = n // 2  # floor(n/2); secondo blocco prende il resto
        mapping: dict[int, str] = {}
        for i, (sid, _) in enumerate(ordered):
            mapping[sid] = "first_half" if i < first_n else "second_half"
        out[comp] = mapping
    return out


def _replay_meta(replay: Any) -> dict[str, Any]:
    return {
        "replay_id": int(getattr(replay, "id")),
        "source_scan_run_id": int(getattr(replay, "source_scan_run_id")),
        "status": str(getattr(replay, "status")),
        "replay_schema_version": getattr(replay, "replay_schema_version", None),
        "replay_engine_version": getattr(replay, "replay_engine_version", None),
        "candidate_version": getattr(replay, "candidate_version", None),
        "formula_version": getattr(replay, "formula_version", None),
        "audit_version": getattr(replay, "audit_version", None),
        "preflight_schema_version": getattr(replay, "preflight_schema_version", None),
        "integrity_policy_version": getattr(replay, "integrity_policy_version", None),
        "source_scan_git_commit": getattr(replay, "source_scan_git_commit", None),
        "runtime_git_commit": getattr(replay, "runtime_git_commit", None),
        "completed_at": _iso(getattr(replay, "completed_at", None)),
        "evaluations_total": int(getattr(replay, "evaluations_total", 0) or 0),
        "results_persisted": int(getattr(replay, "results_persisted", 0) or 0),
        "scored_count": int(getattr(replay, "scored_count", 0) or 0),
        "gate_failed_count": int(getattr(replay, "gate_failed_count", 0) or 0),
        "unavailable_count": int(getattr(replay, "unavailable_count", 0) or 0),
        "not_applicable_count": int(getattr(replay, "not_applicable_count", 0) or 0),
        "error_count": int(getattr(replay, "error_count", 0) or 0),
        "unclassified_count": int(getattr(replay, "unclassified_count", 0) or 0),
        "real_quote_count": int(getattr(replay, "real_quote_count", 0) or 0),
        "derived_quote_count": int(getattr(replay, "derived_quote_count", 0) or 0),
        "unavailable_quote_count": int(
            getattr(replay, "unavailable_quote_count", 0) or 0
        ),
    }


def _empty_perf_bucket() -> dict[str, Any]:
    return build_performance_stats([], profit_field="profit_1u_real")


def _v2_band(score: Any, gate_status: str) -> str | None:
    if gate_status != "accepted":
        return None
    return score_band_for(score)


def _normalize_v2_state(gate_status: str, score: Any) -> str:
    if gate_status == "accepted" and score is not None:
        return "scored"
    if gate_status in (
        "rejected",
        "gate_rejected",
        "failed",
        "blocked",
        "not_passed",
    ) or (gate_status and gate_status != "accepted" and score is None):
        return "gate"
    if score is None:
        return "unavailable"
    return "scored"


def _normalize_v3_state(row: dict[str, Any]) -> str:
    bucket = classify_calc_bucket(row)
    if bucket == "scored":
        return "scored"
    if bucket == "gate_failed":
        return "gate"
    if bucket == "unavailable":
        return "unavailable"
    return bucket


def _build_v2_v3_comparison(
    rows: list[dict[str, Any]],
    v2_markets_by_snapshot: dict[int, list[dict[str, Any]]] | None,
) -> dict[str, Any]:
    v2_index: dict[tuple[int, str], dict[str, Any]] = {}
    if v2_markets_by_snapshot:
        for sid, markets in v2_markets_by_snapshot.items():
            for mk_row in markets:
                if not isinstance(mk_row, dict):
                    continue
                mk = str(mk_row.get("market_key") or "")
                if not mk:
                    continue
                gate_info = classify_purchasability_gate(mk_row)
                v2_index[(int(sid), mk)] = {
                    "gate_status": gate_info.get("gate_status"),
                    "score": mk_row.get("score"),
                    "score_class": mk_row.get("class"),
                }

    transitions: dict[str, int] = defaultdict(int)
    deltas: list[float] = []
    joined = 0
    missing_v2 = 0
    missing_v3 = 0
    v3_keys = {(int(r["source_snapshot_id"]), str(r["market_key"])) for r in rows}
    for key in v2_index:
        if key not in v3_keys:
            missing_v3 += 1

    for r in rows:
        key = (int(r["source_snapshot_id"]), str(r["market_key"]))
        v2 = v2_index.get(key)
        if v2 is None:
            missing_v2 += 1
            transitions["unavailable"] += 1
            continue
        joined += 1
        v2_state = _normalize_v2_state(str(v2.get("gate_status") or ""), v2.get("score"))
        v3_state = _normalize_v3_state(r)
        if v2_state == "gate" and v3_state == "gate":
            transitions["gate_to_gate"] += 1
        elif v2_state == "gate" and v3_state == "scored":
            transitions["gate_to_score"] += 1
        elif v2_state == "scored" and v3_state == "gate":
            transitions["score_to_gate"] += 1
        elif v2_state == "scored" and v3_state == "scored":
            b2 = score_band_for(v2.get("score"))
            b3 = score_band_for(r.get("score"))
            if b2 and b3:
                i2 = SCORE_BANDS.index(b2) if b2 in SCORE_BANDS else -1
                i3 = SCORE_BANDS.index(b3) if b3 in SCORE_BANDS else -1
                if i3 > i2:
                    transitions["score_band_up"] += 1
                elif i3 < i2:
                    transitions["score_band_down"] += 1
                else:
                    transitions["stable_band"] += 1
            else:
                transitions["stable_band"] += 1
            s2 = _f(v2.get("score"))
            s3 = _f(r.get("score"))
            if s2 is not None and s3 is not None:
                deltas.append(s3 - s2)
        else:
            transitions["unavailable"] += 1

    corr = None
    if len(deltas) >= 2:
        # correlazione descrittiva: usiamo solo delta mean come proxy semplice
        corr = {
            "delta_score_n": len(deltas),
            "delta_score_mean": round(statistics.fmean(deltas), 6),
            "delta_score_median": round(_median(deltas) or 0, 6),
            "note": "descriptive_only_not_pearson",
        }

    return {
        "diagnostic_only": True,
        "formula_recomputed": False,
        "join_coverage": {
            "joined": joined,
            "missing_v2": missing_v2,
            "missing_v3": missing_v3,
            "v3_rows": len(rows),
            "v2_entries": len(v2_index),
        },
        "transition_matrix": dict(transitions),
        "score_correlation_descriptive": corr,
        "warning": (
            "Non dichiarare V3 migliore soltanto perché produce score diversi. "
            "Confronto diagnostico read-only."
        ),
    }


def compute_analytics_from_lean_rows(
    *,
    replay: Any,
    rows: list[dict[str, Any]],
    v2_markets_by_snapshot: dict[int, list[dict[str, Any]]] | None = None,
    duration_ms: int = 0,
    snapshot_batches: int = 0,
    v2_snapshot_batches: int = 0,
    max_rows_held_in_memory: int | None = None,
) -> dict[str, Any]:
    meta = _replay_meta(replay)
    warnings: list[str] = []
    blockers: list[dict[str, str]] = []

    if not meta.get("formula_version"):
        blockers.append(
            {
                "code": "missing_formula_version",
                "message": "formula_version assente sul replay",
            }
        )
    if not meta.get("replay_schema_version"):
        blockers.append(
            {
                "code": "missing_replay_schema_version",
                "message": "replay_schema_version assente sul replay",
            }
        )
    if meta["results_persisted"] != meta["evaluations_total"]:
        blockers.append(
            {
                "code": "results_persisted_mismatch",
                "message": (
                    f"results_persisted({meta['results_persisted']}) != "
                    f"evaluations_total({meta['evaluations_total']})"
                ),
            }
        )
    if meta["error_count"] > 0:
        blockers.append(
            {
                "code": "error_count_nonzero",
                "message": f"error_count={meta['error_count']}",
            }
        )
    if meta["unclassified_count"] > 0:
        blockers.append(
            {
                "code": "unclassified_count_nonzero",
                "message": f"unclassified_count={meta['unclassified_count']}",
            }
        )
    if len(rows) != meta["results_persisted"]:
        blockers.append(
            {
                "code": "rows_read_mismatch",
                "message": (
                    f"rows_read({len(rows)}) != results_persisted({meta['results_persisted']})"
                ),
            }
        )

    buckets = {
        "scored": 0,
        "gate_failed": 0,
        "unavailable": 0,
        "not_applicable": 0,
        "error": 0,
        "unclassified": 0,
    }
    quote_buckets = {"real": 0, "derived": 0, "unavailable": 0}
    market_counts = {mk: 0 for mk in V3_MARKET_ORDER}
    unique_keys: set[tuple[int, int, str]] = set()
    pre_match_false = 0
    post_excluded_false = 0
    sha_missing = 0
    sha_missing_non_unavail = 0

    scored_rows: list[dict[str, Any]] = []
    gate_failed_rows: list[dict[str, Any]] = []
    unavailable_rows: list[dict[str, Any]] = []
    real_perf_rows: list[dict[str, Any]] = []
    synth_perf_rows: list[dict[str, Any]] = []

    by_market_rows: dict[str, list[dict[str, Any]]] = {
        mk: [] for mk in V3_MARKET_ORDER
    }
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_band: dict[str, list[dict[str, Any]]] = {b: [] for b in SCORE_BANDS}
    gate_reason_counts: dict[str, int] = defaultdict(int)
    gate_reason_by_market: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )

    for r in rows:
        bucket = classify_calc_bucket(r)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        mk = str(r.get("market_key") or "")
        if mk in market_counts:
            market_counts[mk] += 1
            by_market_rows[mk].append(r)
        sid = int(r.get("source_snapshot_id") or 0)
        unique_keys.add((int(r.get("replay_id") or r.get("replay_run_id") or 0), sid, mk))
        if r.get("pre_match_only") is False:
            pre_match_false += 1
        if r.get("post_match_fields_excluded") is False:
            post_excluded_false += 1
        if not r.get("formula_payload_sha256"):
            sha_missing += 1
            if bucket != "unavailable":
                sha_missing_non_unavail += 1

        qq = str(r.get("quote_quality") or "")
        if qq == "real" or (r.get("is_real_book_quote") and not r.get("is_derived_quote")):
            quote_buckets["real"] += 1
        elif qq == "derived" or r.get("is_derived_quote"):
            quote_buckets["derived"] += 1
        else:
            quote_buckets["unavailable"] += 1

        if bucket == "scored" or _is_scored(r):
            scored_rows.append(r)
            cls = str(r.get("score_class") or "unknown")
            by_class[cls].append(r)
            band = score_band_for(r.get("score"))
            if band:
                by_band[band].append(r)
        elif bucket == "gate_failed":
            gate_failed_rows.append(r)
            reasons = r.get("gate_reason_codes_json") or []
            if isinstance(reasons, list):
                for code in reasons:
                    c = str(code)
                    gate_reason_counts[c] += 1
                    if mk:
                        gate_reason_by_market[mk][c] += 1
        elif bucket == "unavailable":
            unavailable_rows.append(r)

        if _real_perf_ready(r):
            real_perf_rows.append(r)
        if _synth_perf_ready(r):
            synth_perf_rows.append(r)

    all_n = len(rows)
    bucket_sum = sum(buckets.values())
    quote_sum = sum(quote_buckets.values())
    market_sum = sum(market_counts.values())

    recon_ok = True
    recon_checks: list[dict[str, Any]] = []

    def _check(code: str, ok: bool, detail: Any = None) -> None:
        nonlocal recon_ok
        recon_checks.append({"code": code, "ok": ok, "detail": detail})
        if not ok:
            recon_ok = False
            blockers.append({"code": code, "message": f"reconciliation failed: {code}"})

    _check("bucket_sum_equals_all", bucket_sum == all_n, {"sum": bucket_sum, "all": all_n})
    _check(
        "quote_sum_equals_all",
        quote_sum == all_n,
        {"sum": quote_sum, "all": all_n},
    )
    _check(
        "market_sum_equals_all",
        market_sum == all_n,
        {"sum": market_sum, "all": all_n},
    )
    _check(
        "unique_keys_equal_rows",
        len(unique_keys) == all_n,
        {"unique": len(unique_keys), "rows": all_n},
    )
    _check("pre_match_only_false_zero", pre_match_false == 0, pre_match_false)
    _check(
        "post_match_fields_excluded_false_zero",
        post_excluded_false == 0,
        post_excluded_false,
    )
    _check(
        "formula_payload_sha_missing_only_unavailable",
        sha_missing_non_unavail == 0,
        {"missing_total": sha_missing, "missing_non_unavailable": sha_missing_non_unavail},
    )
    _check(
        "source_results_persisted_equals_rows",
        all_n == meta["results_persisted"],
        {"rows": all_n, "persisted": meta["results_persisted"]},
    )

    if meta["status"] == "completed_with_warnings":
        warnings.append("replay_completed_with_warnings")

    status = "blocked" if blockers else (
        "ready_with_warnings" if warnings else "ready"
    )

    halves = build_temporal_halves_by_competition(rows)

    # Gate analysis
    edge_non_pos = 0
    vant_non_pos = 0
    both_non_pos = 0
    input_missing = 0
    for r in gate_failed_rows:
        reasons = [str(x) for x in (r.get("gate_reason_codes_json") or [])]
        edge = _f(r.get("edge_pct"))
        vant = _f(r.get("vantaggio_prob"))
        if edge is not None and edge <= 0:
            edge_non_pos += 1
        if vant is not None and vant <= 0:
            vant_non_pos += 1
        if (edge is not None and edge <= 0) and (vant is not None and vant <= 0):
            both_non_pos += 1
        if any("missing" in x or "input" in x for x in reasons):
            input_missing += 1

    gate_passed_n = len(scored_rows)
    gate_failed_n = len(gate_failed_rows)
    gate_denom = gate_passed_n + gate_failed_n
    gate_analysis = {
        "gate_passed": gate_passed_n,
        "gate_failed": gate_failed_n,
        "gate_pass_rate": (
            round(gate_passed_n / gate_denom * 100.0, 6) if gate_denom else None
        ),
        "reason_codes": dict(sorted(gate_reason_counts.items())),
        "reason_codes_by_market": {
            mk: dict(sorted(v.items())) for mk, v in gate_reason_by_market.items()
        },
        "edge_non_positive": edge_non_pos,
        "vantaggio_non_positive": vant_non_pos,
        "both_non_positive": both_non_pos,
        "input_gate_missing": input_missing,
        "gate_failed_not_score_zero": True,
        "gate_failed_performance_diagnostic": {
            "not_a_strategy": True,
            "by_market": {},
        },
    }

    for mk in V3_MARKET_ORDER:
        passed = [r for r in by_market_rows[mk] if _is_scored(r)]
        failed = [r for r in by_market_rows[mk] if _is_gate_failed(r)]
        gate_analysis["gate_failed_performance_diagnostic"]["by_market"][mk] = {
            "gate_passed": {
                "n": len(passed),
                "real": build_performance_stats(
                    [r for r in passed if _real_perf_ready(r)],
                    profit_field="profit_1u_real",
                ),
                "synthetic": build_performance_stats(
                    [r for r in passed if _synth_perf_ready(r)],
                    profit_field="profit_1u_synthetic",
                ),
            },
            "gate_failed": {
                "n": len(failed),
                "real": build_performance_stats(
                    [r for r in failed if _real_perf_ready(r)],
                    profit_field="profit_1u_real",
                ),
                "synthetic": build_performance_stats(
                    [r for r in failed if _synth_perf_ready(r)],
                    profit_field="profit_1u_synthetic",
                ),
            },
        }

    # Penalties
    penalties_out: dict[str, Any] = {
        "descriptive_observational_analysis": True,
        "fields": {},
        "total_penalty_bands": {},
    }
    for field in PENALTY_FIELDS:
        vals_all: list[float] = []
        applied_rows: list[dict[str, Any]] = []
        not_applied_rows: list[dict[str, Any]] = []
        for r in scored_rows:
            v = _f(r.get(field))
            if v is None:
                continue
            vals_all.append(v)
            if v > 0:
                applied_rows.append(r)
            else:
                not_applied_rows.append(r)
        vals_sorted = sorted(vals_all)
        applied_vals = [v for v in vals_all if v > 0]
        bands: dict[str, int] = defaultdict(int)
        for v in vals_all:
            b = penalty_band_for(v)
            if b:
                bands[b] += 1
        penalties_out["fields"][field] = {
            "count_available": len(vals_all),
            "count_applied": len(applied_vals),
            "application_rate": (
                round(len(applied_vals) / len(vals_all) * 100.0, 6) if vals_all else None
            ),
            "mean": round(statistics.fmean(vals_all), 6) if vals_all else None,
            "median": round(_median(vals_all) or 0, 6) if vals_all else None,
            "min": min(vals_all) if vals_all else None,
            "max": max(vals_all) if vals_all else None,
            "p25": round(_percentile(vals_sorted, 25) or 0, 6) if vals_sorted else None,
            "p75": round(_percentile(vals_sorted, 75) or 0, 6) if vals_sorted else None,
            "p90": round(_percentile(vals_sorted, 90) or 0, 6) if vals_sorted else None,
            "sum_points": round(sum(vals_all), 6) if vals_all else None,
            "average_score_when_applied": (
                round(
                    statistics.fmean(
                        [_f(r.get("score")) or 0 for r in applied_rows]
                    ),
                    6,
                )
                if applied_rows
                else None
            ),
            "average_score_when_not_applied": (
                round(
                    statistics.fmean(
                        [_f(r.get("score")) or 0 for r in not_applied_rows]
                    ),
                    6,
                )
                if not_applied_rows
                else None
            ),
            "performance_when_applied_real": build_performance_stats(
                [r for r in applied_rows if _real_perf_ready(r)],
                profit_field="profit_1u_real",
            ),
            "performance_when_not_applied_real": build_performance_stats(
                [r for r in not_applied_rows if _real_perf_ready(r)],
                profit_field="profit_1u_real",
            ),
            "bands": dict(bands),
        }

    tp_bands: dict[str, int] = defaultdict(int)
    for r in scored_rows:
        b = total_penalty_band_for(r.get("total_penalty"))
        if b:
            tp_bands[b] += 1
    penalties_out["total_penalty_bands"] = dict(tp_bands)

    # Value/Quality matrix
    vq_matrix: dict[str, dict[str, Any]] = {}
    for vb in VQ_BANDS:
        for qb in VQ_BANDS:
            cell_rows = [
                r
                for r in scored_rows
                if vq_band_for(r.get("value_score")) == vb
                and vq_band_for(r.get("quality_score")) == qb
            ]
            key = f"value_{vb}__quality_{qb}"
            vq_matrix[key] = {
                "value_band": vb,
                "quality_band": qb,
                "n": len(cell_rows),
                "real": build_performance_stats(
                    [r for r in cell_rows if _real_perf_ready(r)],
                    profit_field="profit_1u_real",
                ),
                "synthetic": build_performance_stats(
                    [r for r in cell_rows if _synth_perf_ready(r)],
                    profit_field="profit_1u_synthetic",
                ),
                "average_final_score": (
                    round(
                        statistics.fmean(
                            [_f(r.get("score")) or 0 for r in cell_rows]
                        ),
                        6,
                    )
                    if cell_rows
                    else None
                ),
                "not_an_automatic_strategy": True,
            }

    # Family decisions
    family_decisions = build_family_decisions(rows)
    family_summary: dict[str, Any] = {}
    for fam in FAMILY_CANONICAL:
        fam_decs = [d for d in family_decisions if d["family"] == fam]
        selected = [d for d in fam_decs if d.get("selected_market")]
        market_dist: dict[str, int] = defaultdict(int)
        for d in selected:
            market_dist[str(d["selected_market"])] += 1
        use_synth = fam == FAMILY_DOUBLE_CHANCE
        # performance on decision rows reconstructed as synthetic dicts
        perf_rows = []
        for d in selected:
            perf_rows.append(
                {
                    "won": d.get("won"),
                    "score": d.get("score"),
                    "value_score": d.get("value_score"),
                    "quality_score": d.get("quality_score"),
                    "total_penalty": d.get("total_penalty"),
                    "quota_book": d.get("quota_book"),
                    "profit_1u_real": d.get("profit_1u_real"),
                    "profit_1u_synthetic": d.get("profit_1u_synthetic"),
                    "is_real_book_quote": d.get("is_real_book_quote"),
                    "is_derived_quote": d.get("is_derived_quote"),
                }
            )
        family_summary[fam] = {
            "snapshot_decisions": len(fam_decs),
            "selections": len(selected),
            "no_selection": len(fam_decs) - len(selected),
            "selected_market_distribution": dict(market_dist),
            "tie_count_total": sum(int(d.get("tie_count") or 0) for d in selected),
            "performance": build_performance_stats(
                perf_rows,
                profit_field=(
                    "profit_1u_synthetic" if use_synth else "profit_1u_real"
                ),
            ),
            "diagnostic_family_selection": True,
            "not_operational_strategy": True,
            "do_not_sum_across_families": True,
        }

    # By market / threshold / temporal / competition
    by_market: dict[str, Any] = {}
    by_threshold: dict[str, Any] = {}
    temporal_stability: dict[str, Any] = {"split_rule": "per_competition_snapshot_floor_n_over_2"}
    competition_stability: dict[str, Any] = {}

    for mk in V3_MARKET_ORDER:
        mrows = by_market_rows[mk]
        m_scored = [r for r in mrows if _is_scored(r)]
        m_gate = [r for r in mrows if _is_gate_failed(r)]
        m_unavail = [r for r in mrows if _is_unavailable(r)]
        m_real = [r for r in m_scored if _real_perf_ready(r)]
        m_synth = [r for r in m_scored if _synth_perf_ready(r)]
        class_dist: dict[str, int] = defaultdict(int)
        band_dist: dict[str, int] = defaultdict(int)
        for r in m_scored:
            class_dist[str(r.get("score_class") or "unknown")] += 1
            b = score_band_for(r.get("score"))
            if b:
                band_dist[b] += 1
        band_perf = {
            b: {
                "n": len([r for r in m_scored if score_band_for(r.get("score")) == b]),
                "real": build_performance_stats(
                    [
                        r
                        for r in m_scored
                        if score_band_for(r.get("score")) == b and _real_perf_ready(r)
                    ],
                    profit_field="profit_1u_real",
                ),
                "synthetic": build_performance_stats(
                    [
                        r
                        for r in m_scored
                        if score_band_for(r.get("score")) == b and _synth_perf_ready(r)
                    ],
                    profit_field="profit_1u_synthetic",
                ),
            }
            for b in SCORE_BANDS
        }
        thr_out: dict[str, Any] = {}
        for thr in THRESHOLDS:
            eligible = [r for r in m_scored if (_i(r.get("score")) or -1) >= thr]
            real_ready = [r for r in eligible if _real_perf_ready(r)]
            synth_ready = [r for r in eligible if _synth_perf_ready(r)]
            # competition polarity on real
            by_comp_profit: dict[str, list[float]] = defaultdict(list)
            for r in real_ready:
                by_comp_profit[str(r.get("competition_name") or "UNKNOWN")].append(
                    _f(r.get("profit_1u_real")) or 0.0
                )
            pos = neg = zero = insuff = 0
            best = worst = None
            best_p = None
            worst_p = None
            for comp, ps in by_comp_profit.items():
                n = len(ps)
                if n < 30:
                    insuff += 1
                    continue
                total = sum(ps)
                if total > 0:
                    pos += 1
                elif total < 0:
                    neg += 1
                else:
                    zero += 1
                if best_p is None or total > best_p:
                    best_p = total
                    best = comp
                if worst_p is None or total < worst_p:
                    worst_p = total
                    worst = comp
            # halves
            first_rows = []
            second_rows = []
            for r in real_ready:
                comp = str(r.get("competition_name") or "UNKNOWN")
                half = halves.get(comp, {}).get(int(r["source_snapshot_id"]))
                if half == "first_half":
                    first_rows.append(r)
                elif half == "second_half":
                    second_rows.append(r)
            first_stats = build_performance_stats(
                first_rows, profit_field="profit_1u_real"
            )
            second_stats = build_performance_stats(
                second_rows, profit_field="profit_1u_real"
            )
            thr_out[f"score_ge_{thr}"] = {
                "eligible_scored_rows": len(eligible),
                "performance_ready_real": len(real_ready),
                "performance_ready_synthetic": len(synth_ready),
                "real": build_performance_stats(
                    real_ready, profit_field="profit_1u_real"
                ),
                "synthetic": build_performance_stats(
                    synth_ready, profit_field="profit_1u_synthetic"
                ),
                "first_half_real": first_stats,
                "second_half_real": second_stats,
                "competitions_positive": pos,
                "competitions_negative": neg,
                "competitions_zero": zero,
                "competitions_insufficient": insuff,
                "best_competition": best,
                "worst_competition": worst,
            }
        by_threshold[mk] = thr_out

        # temporal for market (scored real)
        first_m = []
        second_m = []
        for r in m_real:
            comp = str(r.get("competition_name") or "UNKNOWN")
            half = halves.get(comp, {}).get(int(r["source_snapshot_id"]))
            if half == "first_half":
                first_m.append(r)
            elif half == "second_half":
                second_m.append(r)
        fs = build_performance_stats(first_m, profit_field="profit_1u_real")
        ss = build_performance_stats(second_m, profit_field="profit_1u_real")
        delta = None
        if fs["roi_pct"] is not None and ss["roi_pct"] is not None:
            delta = round(ss["roi_pct"] - fs["roi_pct"], 6)
        direction = "insufficient_evidence"
        if fs["roi_pct"] is not None and ss["roi_pct"] is not None:
            if fs["roi_pct"] > 0 and ss["roi_pct"] > 0:
                direction = "positive_both_halves"
            elif fs["roi_pct"] < 0 and ss["roi_pct"] < 0:
                direction = "negative_both_halves"
            elif (fs["roi_pct"] >= 0) != (ss["roi_pct"] >= 0):
                direction = "sign_flip"
            else:
                direction = "directionally_consistent"
        temporal_stability[mk] = {
            "n_first_half": fs["stake_count"],
            "roi_first_half": fs["roi_pct"],
            "n_second_half": ss["stake_count"],
            "roi_second_half": ss["roi_pct"],
            "delta_roi": delta,
            "direction_consistency": direction,
        }

        # competition stability
        comp_out: dict[str, Any] = {}
        by_comp: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in mrows:
            by_comp[str(r.get("competition_name") or "UNKNOWN")].append(r)
        for comp, crows in by_comp.items():
            c_scored = [r for r in crows if _is_scored(r)]
            c_gate_pass = len(c_scored)
            c_gate_fail = len([r for r in crows if _is_gate_failed(r)])
            denom = c_gate_pass + c_gate_fail
            c_real = [r for r in c_scored if _real_perf_ready(r)]
            c_synth = [r for r in c_scored if _synth_perf_ready(r)]
            real_stats = build_performance_stats(c_real, profit_field="profit_1u_real")
            synth_stats = build_performance_stats(
                c_synth, profit_field="profit_1u_synthetic"
            )
            sample_n = real_stats["stake_count"] or len(c_scored)
            comp_out[comp] = {
                "scored_count": len(c_scored),
                "gate_pass_rate": (
                    round(c_gate_pass / denom * 100.0, 6) if denom else None
                ),
                "sample_flag": competition_sample_flag(int(sample_n)),
                "real": real_stats,
                "synthetic": synth_stats,
                "average_score": (
                    round(
                        statistics.fmean(
                            [_f(r.get("score")) or 0 for r in c_scored]
                        ),
                        6,
                    )
                    if c_scored
                    else None
                ),
            }
        competition_stability[mk] = comp_out

        by_market[mk] = {
            "evaluations_total": len(mrows),
            "scored": len(m_scored),
            "gate_failed": len(m_gate),
            "unavailable": len(m_unavail),
            "real_quote": sum(1 for r in mrows if quote_buckets and (
                str(r.get("quote_quality") or "") == "real"
                or (r.get("is_real_book_quote") and not r.get("is_derived_quote"))
            )),
            "derived_quote": sum(
                1
                for r in mrows
                if str(r.get("quote_quality") or "") == "derived"
                or r.get("is_derived_quote")
            ),
            "score_class_distribution": dict(class_dist),
            "score_band_distribution": dict(band_dist),
            "score_band_performance": band_perf,
            "threshold_performance": thr_out,
            "performance_real": build_performance_stats(
                m_real, profit_field="profit_1u_real"
            ),
            "performance_synthetic": build_performance_stats(
                m_synth, profit_field="profit_1u_synthetic"
            ),
            "quote_type": (
                "derived"
                if mk in ("ONE_X", "X_TWO", "ONE_TWO")
                else "real"
            ),
            "diagnostic_only_if_derived": mk in ("ONE_X", "X_TWO", "ONE_TWO"),
            "exclude_from_real_roi": mk in ("ONE_X", "X_TWO", "ONE_TWO"),
            "not_a_real_bet365_quote": mk in ("ONE_X", "X_TWO", "ONE_TWO"),
        }

    # Global score distributions
    score_distribution = {
        "scored": len(scored_rows),
        "gate_failed": len(gate_failed_rows),
        "unavailable": len(unavailable_rows),
        "non_numeric_categories": {
            "gate_failed": len(gate_failed_rows),
            "unavailable": len(unavailable_rows),
            "error": buckets.get("error", 0),
            "unclassified": buckets.get("unclassified", 0),
        },
        "by_score_class": {
            k: {"n": len(v)} for k, v in sorted(by_class.items())
        },
        "by_score_band": {
            b: {"n": len(by_band[b])} for b in SCORE_BANDS
        },
        "gate_failed_not_mapped_to_0_19": True,
    }

    by_score_class = {
        k: {
            "n": len(v),
            "real": build_performance_stats(
                [r for r in v if _real_perf_ready(r)], profit_field="profit_1u_real"
            ),
            "synthetic": build_performance_stats(
                [r for r in v if _synth_perf_ready(r)],
                profit_field="profit_1u_synthetic",
            ),
        }
        for k, v in sorted(by_class.items())
    }
    by_score_band = {
        b: {
            "n": len(by_band[b]),
            "real": build_performance_stats(
                [r for r in by_band[b] if _real_perf_ready(r)],
                profit_field="profit_1u_real",
            ),
            "synthetic": build_performance_stats(
                [r for r in by_band[b] if _synth_perf_ready(r)],
                profit_field="profit_1u_synthetic",
            ),
        }
        for b in SCORE_BANDS
    }

    tech_real = build_performance_stats(real_perf_rows, profit_field="profit_1u_real")
    tech_synth = build_performance_stats(
        synth_perf_rows, profit_field="profit_1u_synthetic"
    )
    tech_real["technical_aggregate_only"] = True
    tech_real["do_not_interpret_as_strategy"] = True
    tech_synth["technical_aggregate_only"] = True
    tech_synth["do_not_interpret_as_strategy"] = True
    tech_synth["diagnostic_only"] = True
    tech_synth["exclude_from_real_roi"] = True
    tech_synth["not_a_real_bet365_quote"] = True

    universes = {
        "ALL_EVALUATIONS": all_n,
        "SCORED_EVALUATIONS": len(scored_rows),
        "GATE_FAILED_EVALUATIONS": len(gate_failed_rows),
        "UNAVAILABLE_EVALUATIONS": len(unavailable_rows),
        "REAL_PERFORMANCE_UNIVERSE": len(real_perf_rows),
        "SYNTHETIC_PERFORMANCE_UNIVERSE": len(synth_perf_rows),
    }

    reconciliation = {
        "status": "ok" if recon_ok and not blockers else "failed",
        "all_evaluations": all_n,
        "buckets": buckets,
        "quote_buckets": quote_buckets,
        "market_counts": market_counts,
        "unique_replay_snapshot_market": len(unique_keys),
        "pre_match_only_false_count": pre_match_false,
        "post_match_fields_excluded_false_count": post_excluded_false,
        "formula_payload_sha_missing_count": sha_missing,
        "checks": recon_checks,
    }

    payload = {
        "schema_version": PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
        "status": status,
        "generated_at": _utcnow().isoformat(),
        "replay": meta,
        "universes": universes,
        "reconciliation": reconciliation,
        "score_distribution": score_distribution,
        "gate_analysis": gate_analysis,
        "performance_real": tech_real,
        "performance_synthetic": tech_synth,
        "by_market": by_market,
        "by_score_class": by_score_class,
        "by_score_band": by_score_band,
        "by_threshold": by_threshold,
        "penalties": penalties_out,
        "value_quality_matrix": vq_matrix,
        "family_decisions": {
            "summary": family_summary,
            "decision_count": len(family_decisions),
            "diagnostic_family_selection": True,
            "not_operational_strategy": True,
            "do_not_sum_across_families": True,
        },
        "family_decisions_rows": family_decisions,
        "temporal_stability": temporal_stability,
        "competition_stability": competition_stability,
        "v2_v3_comparison": _build_v2_v3_comparison(rows, v2_markets_by_snapshot),
        "warnings": warnings,
        "blockers": blockers,
        "resource_profile": {
            "strategy": "sql_aggregates_and_keyset_streaming",
            "rows_read": all_n,
            "snapshot_batches": snapshot_batches,
            "max_rows_held_in_memory": max_rows_held_in_memory
            if max_rows_held_in_memory is not None
            else all_n,
            "v2_snapshot_batches": v2_snapshot_batches,
            "duration_ms": duration_ms,
            "formula_recomputed": False,
        },
        "metadata": {
            "formula_recomputed": False,
            "analytics_reads_persisted_replay": True,
            "source_replay_id": meta["replay_id"],
            "source_replay_immutable": True,
            "performance_real_and_synthetic_separated": True,
            "report_valid": status in ("ready", "ready_with_warnings"),
        },
    }
    return _json_safe(payload)


def _load_v2_markets_batched(
    db: Session, *, scan_run_id: int, snapshot_ids: list[int]
) -> tuple[dict[int, list[dict[str, Any]]], int]:
    out: dict[int, list[dict[str, Any]]] = {}
    batches = 0
    S = CecchinoLabHistoricalMatchSnapshot
    for i in range(0, len(snapshot_ids), V2_SNAPSHOT_BATCH):
        chunk = snapshot_ids[i : i + V2_SNAPSHOT_BATCH]
        batches += 1
        stmt = (
            select(S.id, S.purchasability_compatibility_json)
            .where(S.run_id == int(scan_run_id))
            .where(S.id.in_(chunk))
        )
        for sid, purch in db.execute(stmt).all():
            payload = purch if isinstance(purch, dict) else {}
            markets = payload.get("markets") or []
            if isinstance(markets, list):
                out[int(sid)] = [m for m in markets if isinstance(m, dict)]
            else:
                out[int(sid)] = []
    return out, batches


def get_purchasability_v3_replay_analytics(
    db: Session, replay_id: int
) -> dict[str, Any]:
    replay = ensure_replay_ready_for_analytics(db, replay_id)
    key = _cache_key(
        replay_id=int(replay_id),
        kind=CACHE_KIND_SUMMARY,
        completed_at=getattr(replay, "completed_at", None),
        formula_version=getattr(replay, "formula_version", None),
        runtime_commit=getattr(replay, "runtime_git_commit", None),
    )
    cached = _cache_get(key)
    if cached is not None:
        return cached

    t0 = time.monotonic()
    rows = list(iter_lean_replay_result_rows(db, int(replay_id)))
    snap_ids = sorted({int(r["source_snapshot_id"]) for r in rows})
    snapshot_batches = (len(snap_ids) + KEYSET_BATCH - 1) // KEYSET_BATCH if snap_ids else 0
    v2_map, v2_batches = _load_v2_markets_batched(
        db,
        scan_run_id=int(replay.source_scan_run_id),
        snapshot_ids=snap_ids,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    payload = compute_analytics_from_lean_rows(
        replay=replay,
        rows=rows,
        v2_markets_by_snapshot=v2_map,
        duration_ms=duration_ms,
        snapshot_batches=snapshot_batches,
        v2_snapshot_batches=v2_batches,
        max_rows_held_in_memory=len(rows),
    )
    _cache_set(key, payload)
    return payload
