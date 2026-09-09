"""Summary di run RUN V2: coverage, distribuzioni, esito anti-leakage."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import (
    CecchinoRunV2MarketResult,
    CecchinoRunV2MatchSnapshot,
    CecchinoRunV2Run,
)
from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKETS,
    LAYER_CORE_STRICT,
    LAYER_ECONOMIC,
    RUN_V2_EXPORT_SCHEMA_VERSION,
    RUN_V2_EXTRA_STATS_VERSION,
    RUN_V2_FEATURE_CONTRACT_VERSION,
    RUN_V2_QUOTE_POLICY_VERSION,
    RUN_V2_VERSION,
)


def _market_coverage(db: Session, run_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            CecchinoRunV2MarketResult.market_key,
            CecchinoRunV2MarketResult.observation_layer,
            func.count().label("rows"),
            func.sum(
                func.cast(CecchinoRunV2MarketResult.market_quote_available, Integer)
            ).label("with_quote"),
            func.sum(
                func.cast(CecchinoRunV2MarketResult.market_available, Integer)
            ).label("with_prediction"),
        )
        .where(CecchinoRunV2MarketResult.run_id == run_id)
        .group_by(
            CecchinoRunV2MarketResult.market_key,
            CecchinoRunV2MarketResult.observation_layer,
        )
        .order_by(
            CecchinoRunV2MarketResult.market_key,
            CecchinoRunV2MarketResult.observation_layer,
        )
    ).all()

    label_by_key = {m.key: m.export_key for m in CORE_MARKETS}
    out: list[dict[str, Any]] = []
    for market_key, layer, total, with_quote, with_prediction in rows:
        out.append(
            {
                "market_key": market_key,
                "export_key": label_by_key.get(market_key, market_key),
                "observation_layer": layer,
                "rows": int(total or 0),
                "rows_with_quote": int(with_quote or 0),
                "rows_with_prediction": int(with_prediction or 0),
                "quote_coverage_pct": (
                    round(100.0 * float(with_quote or 0) / float(total), 2) if total else None
                ),
                "used_for_prediction": layer == LAYER_CORE_STRICT,
                "pre_match_input_safe": layer == LAYER_CORE_STRICT,
            }
        )
    return out


def _competition_breakdown(db: Session, run_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            CecchinoRunV2MatchSnapshot.competition_name,
            CecchinoRunV2MatchSnapshot.season_label,
            func.count().label("matches"),
            func.min(CecchinoRunV2MatchSnapshot.kickoff_at),
            func.max(CecchinoRunV2MatchSnapshot.kickoff_at),
        )
        .where(CecchinoRunV2MatchSnapshot.run_id == run_id)
        .group_by(
            CecchinoRunV2MatchSnapshot.competition_name,
            CecchinoRunV2MatchSnapshot.season_label,
        )
        .order_by(
            CecchinoRunV2MatchSnapshot.competition_name,
            CecchinoRunV2MatchSnapshot.season_label,
        )
    ).all()
    return [
        {
            "competition": comp,
            "season_label": season,
            "matches": int(matches or 0),
            "first_kickoff": first.isoformat() if first else None,
            "last_kickoff": last.isoformat() if last else None,
        }
        for comp, season, matches, first, last in rows
    ]


def _economic_benchmark_totals(db: Session, run_id: int) -> dict[str, Any]:
    total_rows, settled, profit = db.execute(
        select(
            func.count(),
            func.count(CecchinoRunV2MarketResult.economic_benchmark_profit),
            func.coalesce(func.sum(CecchinoRunV2MarketResult.economic_benchmark_profit), 0),
        ).where(
            CecchinoRunV2MarketResult.run_id == run_id,
            CecchinoRunV2MarketResult.observation_layer == LAYER_ECONOMIC,
        )
    ).one()

    settled = int(settled or 0)
    profit = float(profit or 0.0)
    return {
        "rows": int(total_rows or 0),
        "rows_settled": settled,
        "economic_benchmark_profit_total": round(profit, 4),
        "economic_benchmark_roi_avg": round(profit / settled, 6) if settled else None,
        "used_for_prediction": False,
        "pre_match_input_safe": False,
        "economic_observation_only": True,
        "note": (
            "Metriche derivate da quote near-closing *_last_seen: benchmark "
            "economico, non performance di un sistema deployabile."
        ),
    }


def _extra_stats_coverage(db: Session, run_id: int) -> dict[str, Any]:
    total, with_referee, with_history = db.execute(
        select(
            func.count(),
            func.count(CecchinoRunV2MatchSnapshot.referee),
            func.sum(func.cast(CecchinoRunV2MatchSnapshot.history_count > 0, Integer)),
        ).where(CecchinoRunV2MatchSnapshot.run_id == run_id)
    ).one()

    total = int(total or 0)
    return {
        "snapshots": total,
        "with_referee": int(with_referee or 0),
        "with_prior_history": int(with_history or 0),
        "referee_coverage_pct": (
            round(100.0 * float(with_referee or 0) / float(total), 2) if total else None
        ),
    }


def build_run_summary(
    db: Session,
    *,
    run: CecchinoRunV2Run,
    progress: dict[str, Any],
    auditor: Any,
) -> dict[str, Any]:
    run_id = int(run.id)
    matches = int(
        db.execute(
            select(func.count()).where(CecchinoRunV2MatchSnapshot.run_id == run_id)
        ).scalar()
        or 0
    )

    return {
        "run_id": run_id,
        "run_version": RUN_V2_VERSION,
        "export_schema_version": RUN_V2_EXPORT_SCHEMA_VERSION,
        "feature_contract_version": RUN_V2_FEATURE_CONTRACT_VERSION,
        "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
        "extra_stats_version": RUN_V2_EXTRA_STATS_VERSION,
        "core_formula_freeze": True,
        "matches": matches,
        "date_range": {
            "start": run.min_kickoff_at.isoformat() if run.min_kickoff_at else None,
            "end": run.max_kickoff_at.isoformat() if run.max_kickoff_at else None,
        },
        "progress": progress,
        "competitions": _competition_breakdown(db, run_id),
        "market_coverage": _market_coverage(db, run_id),
        "extra_stats_coverage": _extra_stats_coverage(db, run_id),
        "economic_benchmark": _economic_benchmark_totals(db, run_id),
        "leakage_audit": auditor.to_dict() if auditor is not None else None,
    }
