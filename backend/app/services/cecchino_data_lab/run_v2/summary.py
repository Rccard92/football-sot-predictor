"""Summary di run RUN V2: coverage, distribuzioni, esito anti-leakage."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, case, func, select
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import (
    CecchinoRunV2MarketResult,
    CecchinoRunV2MatchSnapshot,
    CecchinoRunV2Run,
)
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKETS,
    LAYER_CORE_STRICT,
    LAYER_ECONOMIC,
    RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION,
    RUN_V2_EXPORT_SCHEMA_VERSION,
    RUN_V2_EXTRA_STATS_VERSION,
    RUN_V2_FEATURE_CONTRACT_VERSION,
    RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
    RUN_V2_QUOTE_POLICY_VERSION,
    RUN_V2_SCOPE_BALANCED_PILOT,
    RUN_V2_VERSION,
)


def _season_label_from_run(run: CecchinoRunV2Run) -> str | None:
    policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
    raw = policy.get("season_label") or policy.get("season")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _policy(run: CecchinoRunV2Run) -> dict[str, Any]:
    return run.module_policy_json if isinstance(run.module_policy_json, dict) else {}


def _eligible_target(run: CecchinoRunV2Run) -> int | None:
    policy = _policy(run)
    if str(run.run_scope or "") != RUN_V2_SCOPE_BALANCED_PILOT and policy.get(
        "pilot_strategy"
    ) != RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP:
        return None
    raw = policy.get("eligible_per_competition")
    if raw is None:
        raw = policy.get("target_eligible_per_competition")
    if raw is None:
        return RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION
    return value if value > 0 else RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION


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


def _competition_breakdown(
    db: Session,
    run_id: int,
    *,
    eligible_target: int | None = None,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            CecchinoRunV2MatchSnapshot.competition_name,
            CecchinoRunV2MatchSnapshot.season_label,
            func.count().label("matches"),
            func.sum(
                case(
                    (
                        CecchinoRunV2MatchSnapshot.eligibility_status == ELIGIBLE_CORE,
                        1,
                    ),
                    else_=0,
                )
            ).label("eligible_core"),
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
    out: list[dict[str, Any]] = []
    for comp, season, matches, eligible_core, first, last in rows:
        got = int(eligible_core or 0)
        row: dict[str, Any] = {
            "competition": comp,
            "season_label": season,
            "matches": int(matches or 0),
            "eligible_core": got,
            "first_kickoff": first.isoformat() if first else None,
            "last_kickoff": last.isoformat() if last else None,
        }
        if eligible_target is not None:
            row["target_eligible_per_competition"] = int(eligible_target)
            row["target_reached"] = got >= int(eligible_target)
            row["eligible_vs_target"] = f"{got}/{int(eligible_target)}"
        out.append(row)
    return out


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

    rows = int(total_rows or 0)
    if rows == 0:
        # Nuove RUN non materializzano piu LAYER_ECONOMIC: non emettere i flag
        # legacy (pre_match_input_safe=false / economic_observation_only=true)
        # che confondono le quote CORE STRICT.
        return {
            "active": False,
            "deprecated_for_new_runs": True,
            "rows": 0,
            "rows_settled": 0,
            "economic_benchmark_profit_total": None,
            "economic_benchmark_roi_avg": None,
            "note": (
                "Layer economic_observation non usato; quote enrichment = "
                "CORE STRICT closing/pre-kickoff."
            ),
        }

    settled = int(settled or 0)
    profit = float(profit or 0.0)
    return {
        "active": True,
        "deprecated_for_new_runs": False,
        "rows": rows,
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
    policy = _policy(run)
    eligible_target = _eligible_target(run)
    competitions = _competition_breakdown(
        db, run_id, eligible_target=eligible_target
    )

    summary: dict[str, Any] = {
        "run_id": run_id,
        "run_version": RUN_V2_VERSION,
        "export_schema_version": RUN_V2_EXPORT_SCHEMA_VERSION,
        "feature_contract_version": RUN_V2_FEATURE_CONTRACT_VERSION,
        "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
        "extra_stats_version": RUN_V2_EXTRA_STATS_VERSION,
        "core_formula_freeze": True,
        "season_label": _season_label_from_run(run),
        "run_scope": run.run_scope,
        "max_matches": run.max_matches,
        "pilot_strategy": policy.get("pilot_strategy"),
        "eligible_per_competition": eligible_target,
        "target_eligible_per_competition": eligible_target,
        "matches": matches,
        "date_range": {
            "start": run.min_kickoff_at.isoformat() if run.min_kickoff_at else None,
            "end": run.max_kickoff_at.isoformat() if run.max_kickoff_at else None,
        },
        "progress": progress,
        "competitions": competitions,
        "market_coverage": _market_coverage(db, run_id),
        "extra_stats_coverage": _extra_stats_coverage(db, run_id),
        "economic_benchmark": _economic_benchmark_totals(db, run_id),
        "leakage_audit": auditor.to_dict() if auditor is not None else None,
    }

    if eligible_target is not None:
        under = [
            {
                "competition": c["competition"],
                "eligible_core": c["eligible_core"],
                "target_eligible_per_competition": eligible_target,
            }
            for c in competitions
            if int(c.get("eligible_core") or 0) < int(eligible_target)
        ]
        summary["balanced_pilot_warnings"] = (
            [
                {
                    "code": "balanced_pilot_under_target",
                    "message": (
                        f"{len(under)} competizioni sotto target "
                        f"({eligible_target} eligible_core/comp)"
                    ),
                    "competitions": under,
                }
            ]
            if under
            else []
        )

    return summary
