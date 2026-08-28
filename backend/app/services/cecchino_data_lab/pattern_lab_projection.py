"""Proiezione READ-ONLY MATCH+MARKET per Pattern Lab.

Nessun ricalcolo motori: legge snapshot JSONB + market_results.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.services.cecchino_data_lab.historical_analytics_agg import (
    BALANCE_CANONICAL_PILLARS,
    GI_PILLARS,
    as_dict,
    as_list,
    balance_pillars,
    structural_class,
)
from app.services.cecchino_data_lab.pattern_lab_constants import (
    DEFAULT_ELIGIBILITY,
    SNAPSHOT_CHUNK_SIZE,
)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def index_kpi_rows(kpi_json: Any) -> dict[str, dict[str, Any]]:
    data = as_dict(kpi_json)
    rows = as_list(data.get("rows"))
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        mk = row.get("market_key")
        if mk:
            out[str(mk)] = row
    return out


def index_purch_v36(purch_json: Any) -> dict[str, dict[str, Any]]:
    data = as_dict(purch_json)
    markets = as_list(data.get("markets"))
    out: dict[str, dict[str, Any]] = {}
    for row in markets:
        if not isinstance(row, dict):
            continue
        mk = row.get("market_key")
        if mk:
            out[str(mk)] = row
    # Prefer engine_batch items for richer components when present
    batch = as_dict(data.get("engine_batch"))
    items = as_list(batch.get("items"))
    for it in items:
        if not isinstance(it, dict):
            continue
        mk = it.get("market_key")
        if not mk:
            continue
        key = str(mk)
        base = dict(out.get(key) or {})
        ref = as_dict(it.get("reference"))
        components = as_dict(it.get("components"))
        gate = as_dict(it.get("gate"))
        if ref.get("score") is not None:
            base["score"] = ref.get("score")
        if ref.get("class") is not None:
            base["class"] = ref.get("class")
        if it.get("status") is not None:
            base["status"] = it.get("status")
        if it.get("gate_status") is not None or gate.get("gate_status") is not None:
            base["gate_status"] = it.get("gate_status") or gate.get("gate_status")
        base["value_core"] = it.get("value_core") or ref.get("value_core")
        base["structural_factor"] = it.get("structural_factor") or ref.get("structural_factor")
        base["quality_factor"] = it.get("quality_factor") or ref.get("quality_factor")
        base["acquisition_core"] = it.get("acquisition_core") or ref.get("acquisition_core")
        base["components"] = components or None
        out[key] = base
    return out


def _signal_excel_flags(sources: Any) -> dict[str, bool | None]:
    cols = {"D": None, "E": None, "F": None, "G": None}
    if not isinstance(sources, list):
        return {f"pre_signal_excel_{k.lower()}": None for k in cols}
    seen: set[str] = set()
    for src in sources:
        if not isinstance(src, dict):
            continue
        col = str(src.get("source_column") or src.get("column_key") or "").upper()
        if col.startswith("EXCEL_"):
            col = col.replace("EXCEL_", "", 1)
        if col in cols:
            seen.add(col)
    return {
        "pre_signal_excel_d": True if "D" in seen else (False if sources else None),
        "pre_signal_excel_e": True if "E" in seen else (False if sources else None),
        "pre_signal_excel_f": True if "F" in seen else (False if sources else None),
        "pre_signal_excel_g": True if "G" in seen else (False if sources else None),
    }


def _signal_fields(market: CecchinoLabHistoricalMarketResult) -> dict[str, Any]:
    sources = market.signal_sources_json
    src_dict = sources if isinstance(sources, dict) else {}
    raw_sources = as_list(src_dict.get("sources"))
    yes_cols = as_list(src_dict.get("consensus_yes_columns"))
    count = _int(src_dict.get("acquired_signal_count"))
    if count is None:
        count = _int(src_dict.get("active_signal_count"))
    if count is None:
        count = 1 if market.signal_active else 0
    excel = _signal_excel_flags(raw_sources)
    # Also mark from consensus_yes_columns
    for col in yes_cols:
        text = str(col or "").upper().replace("EXCEL_", "")
        key = f"pre_signal_excel_{text.lower()}"
        if key in excel:
            excel[key] = True
    return {
        "pre_signal_active": bool(market.signal_active),
        "pre_signal_count": int(count or 0),
        "pre_signal_family": src_dict.get("signal_family"),
        "pre_signal_detail": src_dict or None,
        "pre_consensus_yes_count": _int(src_dict.get("consensus_yes_count"))
        or len(yes_cols)
        or None,
        "pre_consensus_status": src_dict.get("acquisition_status"),
        "pre_consensus_yes_columns": yes_cols or None,
        **excel,
    }


def _balance_fields(balance_json: Any) -> dict[str, Any]:
    bal = as_dict(balance_json)
    pillars = balance_pillars(bal)
    struct_class, _ = structural_class(bal.get("structural_summary") if bal else None)
    out: dict[str, Any] = {
        "pre_balance_structural_class": struct_class if bal else None,
        "pre_balance_observation_status": bal.get("observation_status"),
    }
    for key in BALANCE_CANONICAL_PILLARS:
        block = pillars.get(key) or {}
        out[f"pre_balance_{key}_score"] = _num(block.get("score"))
        out[f"pre_balance_{key}_class"] = block.get("class_key")
        out[f"pre_balance_{key}_value"] = _num(block.get("value"))
    gap = pillars.get("gap_coherence") or {}
    out["pre_balance_geometry"] = _num(gap.get("score"))
    return out


def _goal_v4_compat_fields(gi_json: Any) -> dict[str, Any]:
    gi = as_dict(gi_json)
    pillars = as_dict(gi.get("pillars"))
    final = as_dict(gi.get("final_class"))
    out: dict[str, Any] = {
        "pre_goal_v4_compat_execution_status": gi.get("execution_status"),
        "pre_goal_v4_compat_composite": _num(gi.get("composite_gi_a_strict_core")),
        "pre_goal_v4_compat_final_class": final.get("key") or final.get("label"),
        "pre_goal_v4_compat_direction": final.get("key") or final.get("label"),
        "pre_goal_v4_compat_final_score": _num(final.get("score")),
    }
    for key in GI_PILLARS:
        block = as_dict(pillars.get(key))
        out[f"pre_goal_v4_compat_{key}_score"] = _num(block.get("score"))
        out[f"pre_goal_v4_compat_{key}_class"] = block.get("class_key")
        out[f"pre_goal_v4_compat_{key}_raw"] = _num(block.get("raw_value"))
    return out


def _purch_fields(purch_row: dict[str, Any] | None) -> dict[str, Any]:
    if not purch_row:
        return {
            "pre_purch_v36_score": None,
            "pre_purch_v36_class": None,
            "pre_purch_v36_status": None,
            "pre_purch_v36_gate_status": None,
            "pre_purch_v36_value_core": None,
            "pre_purch_v36_structural_factor": None,
            "pre_purch_v36_quality_factor": None,
            "pre_purch_v36_acquisition_core": None,
        }
    return {
        "pre_purch_v36_score": _num(purch_row.get("score")),
        "pre_purch_v36_class": purch_row.get("class"),
        "pre_purch_v36_status": purch_row.get("status"),
        "pre_purch_v36_gate_status": purch_row.get("gate_status"),
        "pre_purch_v36_value_core": _num(purch_row.get("value_core")),
        "pre_purch_v36_structural_factor": _num(purch_row.get("structural_factor")),
        "pre_purch_v36_quality_factor": _num(purch_row.get("quality_factor")),
        "pre_purch_v36_acquisition_core": _num(purch_row.get("acquisition_core")),
    }


def _kpi_fields(
    market: CecchinoLabHistoricalMarketResult,
    kpi_row: dict[str, Any] | None,
) -> dict[str, Any]:
    row = kpi_row or {}
    score_acquisto = _num(row.get("score_acquisto"))
    edge = _num(market.edge_pct if market.edge_pct is not None else row.get("edge_pct"))
    rating = _int(market.rating if market.rating is not None else row.get("rating"))
    vantaggio = _num(
        market.vantaggio_prob if market.vantaggio_prob is not None else row.get("vantaggio_prob")
    )
    value_positive = None
    if score_acquisto is not None:
        value_positive = score_acquisto > 0
    elif edge is not None and vantaggio is not None:
        value_positive = edge > 0 and vantaggio > 0
    return {
        "pre_rating": rating,
        "pre_rating_label": row.get("rating_label"),
        "pre_edge_pct": edge,
        "pre_value": score_acquisto,
        "pre_score_acquisto": score_acquisto,
        "pre_value_positive": value_positive,
        "pre_vantaggio_prob": vantaggio,
        "pre_prob_cecchino": _num(
            market.prob_cecchino if market.prob_cecchino is not None else row.get("prob_cecchino")
        ),
        "pre_prob_book": _num(row.get("prob_book") or market.prob_book_raw),
        "pre_prob_book_fair": _num(market.prob_book_fair),
        "pre_quota_cecchino": _num(
            market.quota_cecchino if market.quota_cecchino is not None else row.get("quota_cecchino")
        ),
        "pre_kpi_status": row.get("status"),
        "pre_book_source": row.get("book_source"),
        "pre_cecchino_source": row.get("cecchino_source"),
    }


def _quote_fields(market: CecchinoLabHistoricalMarketResult) -> dict[str, Any]:
    quota = _num(market.quota_book)
    implied = round(1.0 / quota, 6) if quota and quota > 1.0 else None
    if market.is_real_book_quote:
        qtype = "real"
    elif market.is_derived_quote:
        qtype = "derived"
    else:
        qtype = None
    return {
        "pre_quota_bet365": quota,
        "pre_quote_type": qtype,
        "pre_implied_probability": implied,
        "pre_is_real_book_quote": bool(market.is_real_book_quote),
        "pre_is_derived_quote": bool(market.is_derived_quote),
        "pre_derivation_method": market.derivation_method,
        "pre_quote_source_type": market.quote_source_type,
    }


def _target_fields(
    market: CecchinoLabHistoricalMarketResult,
    result_json: Any,
) -> dict[str, Any]:
    result = as_dict(result_json)
    ft = as_dict(result.get("fulltime") or result.get("ft"))
    ht = as_dict(result.get("halftime") or result.get("ht"))
    won = market.won
    status = str(market.evaluation_status or "")
    is_void = status in ("void", "not_evaluable", "result_missing") or (
        won is None and status not in ("won", "lost", "settled")
    )
    if status == "settled" and won is True:
        is_void = False
    if status == "settled" and won is False:
        is_void = False
    profit = None
    if market.is_real_book_quote and market.profit_1u_real is not None:
        profit = _num(market.profit_1u_real)
    elif market.profit_1u_synthetic is not None:
        profit = _num(market.profit_1u_synthetic)
    elif market.profit_1u_real is not None:
        profit = _num(market.profit_1u_real)
    return {
        "target_evaluation_status": market.evaluation_status,
        "target_won": True if won is True else (False if won is False else None),
        "target_lost": True if won is False else (False if won is True else None),
        "target_void": bool(is_void) if won is None else False,
        "target_profit_1u": profit,
        "target_profit_1u_real": _num(market.profit_1u_real),
        "target_profit_1u_synthetic": _num(market.profit_1u_synthetic),
        "target_profit_category": market.profit_category,
        "target_result_reason": market.result_reason,
        "target_ft_home": _int(ft.get("home")),
        "target_ft_away": _int(ft.get("away")),
        "target_ht_home": _int(ht.get("home")),
        "target_ht_away": _int(ht.get("away")),
        "target_ft_result": result.get("ft_result"),
    }


def _observational_fields(
    market: CecchinoLabHistoricalMarketResult,
    quote_obs: Any,
) -> dict[str, Any]:
    obs = as_dict(quote_obs)
    movements = as_list(obs.get("movements") or obs.get("markets"))
    hit: dict[str, Any] | None = None
    for row in movements:
        if isinstance(row, dict) and str(row.get("market_key")) == market.market_key:
            hit = row
            break
    if not hit:
        # nested by market_key
        by_mk = as_dict(obs.get("by_market"))
        cand = by_mk.get(market.market_key)
        if isinstance(cand, dict):
            hit = cand
    hit = hit or {}
    return {
        "observational_only_quota_closing": _num(hit.get("quota_closing")),
        "observational_only_implied_prob_closing": _num(hit.get("implied_probability_closing")),
        "observational_only_movement_delta_pct": _num(hit.get("delta_pct")),
        "observational_only_movement_direction": hit.get("direction"),
        "observational_only_movement_intensity": hit.get("intensity"),
        "observational_only_availability_horizon": hit.get("availability_horizon")
        or obs.get("availability_horizon"),
    }


def project_row(
    snap: CecchinoLabHistoricalMatchSnapshot,
    market: CecchinoLabHistoricalMarketResult,
    *,
    kpi_by_market: dict[str, dict[str, Any]] | None = None,
    purch_by_market: dict[str, dict[str, Any]] | None = None,
    bb_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Una riga flat RUN+MATCH+MARKET."""
    kpi_idx = kpi_by_market if kpi_by_market is not None else index_kpi_rows(snap.historical_kpi_json)
    purch_idx = (
        purch_by_market
        if purch_by_market is not None
        else index_purch_v36(snap.purchasability_compatibility_json)
    )
    kpi_row = kpi_idx.get(market.market_key)
    purch_row = purch_idx.get(market.market_key)
    bb = bb_meta or {}

    row: dict[str, Any] = {
        # identity
        "run_id": int(snap.run_id),
        "season": snap.season_label,
        "competition": snap.competition_name,
        "lab_match_id": int(snap.lab_match_id),
        "snapshot_id": int(snap.id),
        "kickoff_at": _iso(snap.kickoff_at),
        "home_team": snap.home_team,
        "away_team": snap.away_team,
        "market_key": market.market_key,
        "market_label": market.market_label,
        "eligibility_status": snap.historical_eligibility_status,
        **_quote_fields(market),
        **_kpi_fields(market, kpi_row),
        **_signal_fields(market),
        **_balance_fields(snap.balance_v5_json),
        **_goal_v4_compat_fields(snap.goal_intensity_compatibility_json),
        **_purch_fields(purch_row),
        "pre_pattern_lab_bet_builder_active": bool(bb.get("active")),
        "pre_pattern_lab_bet_builder_rank": bb.get("rank"),
        "pre_pattern_lab_bet_builder_selection_reason": bb.get("reason"),
        "pre_pattern_lab_bet_builder_origin": bb.get("origin"),
        **_target_fields(market, snap.result_json),
        **_observational_fields(market, snap.quote_observations_json),
    }
    return row


def iter_snapshot_id_batches(
    db: Session,
    run_ids: list[int],
    *,
    eligibility: str | None = DEFAULT_ELIGIBILITY,
    chunk_size: int = SNAPSHOT_CHUNK_SIZE,
) -> Iterator[list[int]]:
    """Yield batch di snapshot_id ordinati — senza caricare JSONB."""
    if not run_ids:
        return
    q = (
        select(CecchinoLabHistoricalMatchSnapshot.id)
        .where(CecchinoLabHistoricalMatchSnapshot.run_id.in_(run_ids))
        .order_by(
            CecchinoLabHistoricalMatchSnapshot.run_id.asc(),
            CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc().nulls_last(),
            CecchinoLabHistoricalMatchSnapshot.id.asc(),
        )
    )
    if eligibility and eligibility != "all":
        q = q.where(
            CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == eligibility
        )
    batch: list[int] = []
    for sid in db.scalars(q).yield_per(chunk_size):
        batch.append(int(sid))
        if len(batch) >= chunk_size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_snapshots_by_ids(
    db: Session,
    snapshot_ids: list[int],
) -> list[CecchinoLabHistoricalMatchSnapshot]:
    if not snapshot_ids:
        return []
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
                    CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status,
                    CecchinoLabHistoricalMatchSnapshot.historical_kpi_json,
                    CecchinoLabHistoricalMatchSnapshot.signals_json,
                    CecchinoLabHistoricalMatchSnapshot.balance_v5_json,
                    CecchinoLabHistoricalMatchSnapshot.goal_intensity_compatibility_json,
                    CecchinoLabHistoricalMatchSnapshot.purchasability_compatibility_json,
                    CecchinoLabHistoricalMatchSnapshot.quote_observations_json,
                    CecchinoLabHistoricalMatchSnapshot.cecchino_output_json,
                    CecchinoLabHistoricalMatchSnapshot.result_json,
                )
            )
            .where(CecchinoLabHistoricalMatchSnapshot.id.in_(snapshot_ids))
        ).all()
    )


def load_markets_for_snapshots(
    db: Session,
    snapshot_ids: list[int],
) -> list[CecchinoLabHistoricalMarketResult]:
    if not snapshot_ids:
        return []
    return list(
        db.scalars(
            select(CecchinoLabHistoricalMarketResult)
            .where(CecchinoLabHistoricalMarketResult.match_snapshot_id.in_(snapshot_ids))
            .order_by(
                CecchinoLabHistoricalMarketResult.match_snapshot_id.asc(),
                CecchinoLabHistoricalMarketResult.market_key.asc(),
            )
        ).all()
    )
