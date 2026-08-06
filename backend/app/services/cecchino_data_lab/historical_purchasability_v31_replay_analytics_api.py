"""Entry-point analytics / decision / export V3.1 sul replay persistito."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.models.cecchino_lab_purchasability_v3_replay_run import (
    COMPLETED_STATUSES,
    CecchinoLabPurchasabilityV3ReplayRun,
)
from app.schemas.cecchino_purchasability_v3 import PURCHASABILITY_V3_FORMULA_VERSION
from app.schemas.cecchino_purchasability_v31 import PURCHASABILITY_V31_FORMULA_VERSION
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_purchasability_operational import (
    get_operational_purchasability_config,
    promote_purchasability_v31,
    rollback_purchasability_to_v3,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_analytics import (
    build_v31_analytics_payload,
)
from app.services.cecchino_data_lab.historical_purchasability_v31_go_no_go import (
    evaluate_purchasability_v31_go_no_go,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

LEAN_FIELDS = (
    "id",
    "replay_run_id",
    "source_scan_run_id",
    "source_snapshot_id",
    "source_market_result_id",
    "lab_match_id",
    "competition_name",
    "kickoff_at",
    "chronological_order",
    "market_key",
    "market_family",
    "quote_quality",
    "is_real_book_quote",
    "is_derived_quote",
    "quota_book",
    "edge_pct",
    "vantaggio_prob",
    "prob_cecchino",
    "calculation_status",
    "gate_status",
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
    "reason_codes_json",
    "warnings_json",
    "won",
    "profit_1u_real",
    "profit_1u_synthetic",
    "performance_evaluation_status",
    "pre_match_only",
    "post_match_fields_excluded",
)


def _row_to_dict(r: CecchinoLabPurchasabilityV3ReplayResult) -> dict[str, Any]:
    return {f: getattr(r, f, None) for f in LEAN_FIELDS}


def _load_lean_rows(db: Session, replay_id: int) -> list[dict[str, Any]]:
    cols = [getattr(CecchinoLabPurchasabilityV3ReplayResult, f) for f in LEAN_FIELDS]
    stmt = (
        select(CecchinoLabPurchasabilityV3ReplayResult)
        .options(load_only(*cols))
        .where(CecchinoLabPurchasabilityV3ReplayResult.replay_run_id == replay_id)
        .order_by(
            CecchinoLabPurchasabilityV3ReplayResult.kickoff_at.asc().nulls_last(),
            CecchinoLabPurchasabilityV3ReplayResult.source_snapshot_id.asc(),
            CecchinoLabPurchasabilityV3ReplayResult.market_key.asc(),
        )
    )
    return [_row_to_dict(r) for r in db.scalars(stmt).all()]


def _find_v3_replay_for_run(db: Session, source_run_id: int) -> int | None:
    row = db.scalars(
        select(CecchinoLabPurchasabilityV3ReplayRun)
        .where(
            CecchinoLabPurchasabilityV3ReplayRun.source_scan_run_id == source_run_id,
            CecchinoLabPurchasabilityV3ReplayRun.formula_version
            == PURCHASABILITY_V3_FORMULA_VERSION,
            CecchinoLabPurchasabilityV3ReplayRun.status.in_(tuple(COMPLETED_STATUSES)),
        )
        .order_by(CecchinoLabPurchasabilityV3ReplayRun.id.asc())
    ).first()
    return int(row.id) if row else None


def get_purchasability_v31_replay_analytics(
    db: Session,
    replay_id: int,
) -> dict[str, Any]:
    replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
    if not replay:
        raise CecchinoLabImportError("replay_not_found", "Replay non trovato", status_code=404)
    if replay.formula_version != PURCHASABILITY_V31_FORMULA_VERSION:
        raise CecchinoLabImportError(
            "formula_mismatch",
            "Analytics V3.1 richiedono un replay V3.1",
            status_code=409,
        )
    if replay.status not in COMPLETED_STATUSES:
        raise CecchinoLabImportError(
            "replay_not_completed",
            "Il replay deve essere completato prima delle analytics",
            status_code=409,
        )

    rows = _load_lean_rows(db, replay_id)
    v3_rows: list[dict[str, Any]] = []
    v3_id = _find_v3_replay_for_run(db, int(replay.source_scan_run_id))
    if v3_id is not None:
        v3_rows = _load_lean_rows(db, v3_id)

    recon_ok = (
        int(replay.unclassified_count or 0) == 0
        and int(replay.results_persisted or 0) == int(replay.evaluations_total or 0)
    )
    profile = (replay.summary_json or {}).get("resource_profile") or {}
    ctx = {
        "formula_version": replay.formula_version,
        "replay_id": int(replay.id),
        "source_run_id": int(replay.source_scan_run_id),
        "has_independent_holdout": False,
        "leakage_detected": False,
        "future_data_used": False,
        "integrity_invalid": False,
        "unclassified_count": int(replay.unclassified_count or 0),
        "reconciliation_ok": recon_ok,
        "ambiguous_join_count": 0,
        "duplicate_results_count": 0,
        "formula_version_mismatch": False,
        "v3_modified": False,
        "real_synthetic_mixed": False,
        "validation_commit": replay.runtime_git_commit,
    }
    meta = {
        "replay_id": int(replay.id),
        "source_scan_run_id": int(replay.source_scan_run_id),
        "formula_version": replay.formula_version,
        "candidate_version": replay.candidate_version,
        "audit_version": replay.audit_version,
        "status": replay.status,
        "results_persisted": int(replay.results_persisted or 0),
        "evaluations_total": int(replay.evaluations_total or 0),
        "formula_invocations": profile.get("formula_invocations"),
        "v3_replay_id_matched": v3_id,
        "operational": get_operational_purchasability_config(),
    }
    return build_v31_analytics_payload(
        rows, replay_meta=meta, v3_rows=v3_rows, context=ctx
    )


def get_purchasability_v31_decision(
    db: Session,
    replay_id: int,
) -> dict[str, Any]:
    analytics = get_purchasability_v31_replay_analytics(db, replay_id)
    decision = analytics.get("decision") or evaluate_purchasability_v31_go_no_go(
        analytics, context={}
    )
    return {
        "replay_id": replay_id,
        "decision": decision,
        "analytics_schema_version": analytics.get("schema_version"),
        "positive_signal_health": analytics.get("positive_signal_health"),
        "temporal_split": analytics.get("temporal_split"),
    }


def promote_purchasability_v31_from_replay(
    db: Session,
    *,
    replay_id: int,
    confirm_token: str,
    expected_formula_version: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    decision_payload = get_purchasability_v31_decision(db, replay_id)
    decision = decision_payload.get("decision") or {}
    decision_code = str(decision.get("decision") or "")
    revision = resolve_code_revision()
    replay = db.get(CecchinoLabPurchasabilityV3ReplayRun, replay_id)
    assert replay is not None
    result = promote_purchasability_v31(
        replay_id=replay_id,
        decision=decision_code,
        formula_version=expected_formula_version,
        confirm_token=confirm_token,
        validation_meta={
            "source_run_id": int(replay.source_scan_run_id),
            "decision_version": decision.get("decision_version"),
            "validation_commit": revision.get("git_commit") or replay.runtime_git_commit,
        },
        idempotency_key=idempotency_key,
    )
    return {
        "promotion": result,
        "decision": decision,
    }


def rollback_operational_to_v3(*, confirm_token: str) -> dict[str, Any]:
    return rollback_purchasability_to_v3(confirm_token=confirm_token)


def build_v31_export_rows(db: Session, replay_id: int) -> dict[str, Any]:
    """Export strutturato V3.1 (metadata + lean rows arricchite)."""
    analytics = get_purchasability_v31_replay_analytics(db, replay_id)
    rows = _load_lean_rows(db, replay_id)
    from app.services.cecchino_data_lab.historical_purchasability_v31_analytics import (
        reconstruct_historical_factor,
        assign_temporal_split,
    )

    split = assign_temporal_split(rows)
    export_rows = []
    for r in rows:
        hf, hf_reason = reconstruct_historical_factor(r)
        export_rows.append(
            {
                **{k: r.get(k) for k in (
                    "source_snapshot_id",
                    "market_key",
                    "market_family",
                    "quote_quality",
                    "is_real_book_quote",
                    "is_derived_quote",
                    "score",
                    "score_class",
                    "gate_status",
                    "calculation_status",
                    "reason_codes_json",
                    "value_score",
                    "quality_score",
                    "raw_score",
                    "probability_risk_penalty",
                    "opposite_market_pressure_penalty",
                    "extreme_divergence_penalty",
                    "family_ambiguity_penalty",
                    "won",
                    "profit_1u_real",
                    "profit_1u_synthetic",
                    "kickoff_at",
                    "chronological_order",
                    "competition_name",
                    "pre_match_only",
                    "post_match_fields_excluded",
                )},
                "historical_factor": hf,
                "historical_factor_reason": hf_reason,
                "holdout_flag": r.get("_temporal_split") == "pseudo_holdout",
                "temporal_split": r.get("_temporal_split"),
            }
        )
    return {
        "metadata": analytics.get("replay"),
        "temporal_split": split,
        "decision": analytics.get("decision"),
        "positive_signal_health": analytics.get("positive_signal_health"),
        "rows": export_rows,
    }
