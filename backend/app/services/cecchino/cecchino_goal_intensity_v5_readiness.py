"""Readiness Intensità Goal Avanzata v5 — monitoring/governance.

Riusa gate di build_prospective_monitoring e MINIMUM_PROSPECTIVE_MATCHES.
Signals sempre blocked; decision default continue_monitoring.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    SNAPSHOT_COMPLETED,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.services.cecchino.cecchino_goal_intensity_v5 import (
    build_calibration,
    build_candidates,
    build_data_health,
    build_overview,
    get_active_bundle,
)
from app.services.cecchino.cecchino_goal_intensity_v5_monitoring_adapter import (
    normalize_goal_v5_monitoring_contract,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    MINIMUM_PROSPECTIVE_MATCHES,
    _bundle_summary,
    build_prospective_monitoring,
)
from app.services.cecchino.cecchino_goal_intensity_v5_readiness_policy import (
    GOAL_INTENSITY_V5_READINESS_POLICY_VERSION,
    GOAL_INTENSITY_V5_READINESS_VERSION,
    MIN_PROSPECTIVE_COMPLETED,
    build_goal_intensity_v5_readiness_policy_payload,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 300.0
_cache_lock = threading.Lock()
_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def clear_goal_intensity_v5_readiness_cache() -> None:
    with _cache_lock:
        _cache.clear()
    try:
        from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import (
            clear_goal_intensity_v4_v5_benchmark_cache,
        )

        clear_goal_intensity_v4_v5_benchmark_cache()
    except Exception:  # noqa: BLE001
        pass


def _gate(
    *,
    key: str,
    category: str,
    status: str,
    value: Any = None,
    threshold: Any = None,
    numerator: Any = None,
    denominator: Any = None,
    reason_codes: list[str] | None = None,
    promotion_blocking: bool = True,
    label_it: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "category": category,
        "status": status,
        "value": value,
        "threshold": threshold,
        "numerator": numerator,
        "denominator": denominator,
        "reason_codes": reason_codes or [],
        "promotion_blocking": promotion_blocking,
        "label_it": label_it or key.replace("_", " "),
    }


def build_goal_intensity_v5_readiness(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, Any]:
    cache_key = (
        GOAL_INTENSITY_V5_READINESS_VERSION,
        GOAL_INTENSITY_V5_READINESS_POLICY_VERSION,
        date_from,
        date_to,
        competition_id,
    )
    with _cache_lock:
        hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL_S:
            out = dict(hit[1])
            out["cache_hit"] = True
            return out

    bundle = get_active_bundle(db)
    policy = build_goal_intensity_v5_readiness_policy_payload()
    monitoring = build_prospective_monitoring(db, bundle)
    all_snaps: list[CecchinoGoalIntensityV5PreviewSnapshot] = []
    bundle_summary = None
    if bundle is not None:
        all_snaps = list(
            db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
                )
            ).all()
        )
        bundle_summary = _bundle_summary(bundle, db)
    normalized = normalize_goal_v5_monitoring_contract(
        monitoring=monitoring,
        snapshots=all_snaps,
        bundle_summary=bundle_summary,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    health = build_data_health(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )

    tech_gates: list[dict[str, Any]] = []
    if bundle is None:
        tech_gates.append(
            _gate(
                key="active_bundle_present",
                category="technical",
                status="fail",
                value=False,
                threshold=True,
                reason_codes=["bundle_missing"],
                label_it="Bundle attivo presente",
            )
        )
        completed_n = 0
        all_n = 0
        pending_n = 0
        locked_n = 0
        incomplete_n = 0
        error_n = 0
    else:
        tech_gates.append(
            _gate(
                key="active_bundle_present",
                category="technical",
                status="pass",
                value=True,
                threshold=True,
                label_it="Bundle attivo presente",
            )
        )
        tech_gates.append(
            _gate(
                key="definition_hash_valid",
                category="technical",
                status="pass" if bundle.candidate_definition_hash else "fail",
                value=bool(bundle.candidate_definition_hash),
                label_it="Definition hash valido",
            )
        )
        snaps = list(
            db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id
                )
            ).all()
        )
        all_n = int(normalized.get("total_snapshots") or 0)
        completed_n = int(normalized.get("completed_snapshots") or 0)
        pending_n = int(normalized.get("pending_snapshots") or 0)
        locked_n = int(normalized.get("locked_snapshots") or 0)
        incomplete_n = int(normalized.get("incomplete_snapshots") or 0)
        error_n = int(normalized.get("error_snapshots") or 0)
        no_target_ok = all(s.no_target_used_in_score is not False for s in snaps) if snaps else True
        tech_gates.append(
            _gate(
                key="no_target_used",
                category="technical",
                status="pass" if no_target_ok else "fail",
                value=no_target_ok,
                label_it="Nessun target usato nello score",
            )
        )
        for issue in health.get("issues") or []:
            tech_gates.append(
                _gate(
                    key=str(issue.get("reason_code") or "issue"),
                    category="technical",
                    status="fail" if issue.get("severity") == "blocking" else "wait",
                    value=issue.get("count"),
                    reason_codes=[str(issue.get("reason_code"))],
                    label_it=str(issue.get("reason_code") or "issue").replace("_", " "),
                )
            )

    sample_status = (
        "pass"
        if completed_n >= MIN_PROSPECTIVE_COMPLETED
        else ("wait" if all_n == 0 or completed_n < MIN_PROSPECTIVE_COMPLETED else "fail")
    )
    progress_gates = [
        _gate(
            key="minimum_prospective_completed",
            category="prospective",
            status=sample_status,
            value=completed_n,
            threshold=MIN_PROSPECTIVE_COMPLETED,
            numerator=completed_n,
            denominator=MIN_PROSPECTIVE_COMPLETED,
            reason_codes=["prospective_not_started"]
            if all_n == 0
            else (["insufficient_completed_sample"] if completed_n < MIN_PROSPECTIVE_COMPLETED else []),
            label_it="Campione prospettico completed minimo",
        )
    ]

    phase = monitoring.get("phase_2b_readiness") or {}
    blocking = list(phase.get("blocking_issues") or [])
    recommended_next_step = phase.get("recommended_next_step")
    if recommended_next_step is None:
        if completed_n < MIN_PROSPECTIVE_COMPLETED:
            recommended_next_step = "continue_prospective_monitoring"
        elif blocking:
            recommended_next_step = "revise_candidate_definition"
        else:
            recommended_next_step = "phase_2b_replacement_review"

    next_step_labels = {
        "continue_prospective_monitoring": "Continua raccolta prospettica",
        "revise_candidate_definition": "Revisiona definizione candidati",
        "phase_2b_replacement_review": "Revisione manuale Phase 2B",
    }

    if all_n == 0:
        maturity = "prospective_not_started"
        maturity_it = "Raccolta prospettica non iniziata"
    elif completed_n == 0:
        maturity = "prospective_collecting"
        maturity_it = "Raccolta prospettica in corso"
    elif completed_n < MIN_PROSPECTIVE_COMPLETED:
        maturity = "insufficient_completed_sample"
        maturity_it = "Campione completed insufficiente"
    elif blocking:
        maturity = "review_required"
        maturity_it = "Revisione richiesta"
    elif completed_n >= MIN_PROSPECTIVE_COMPLETED and not blocking:
        maturity = "ready_for_manual_review"
        maturity_it = "Pronto per revisione manuale"
    else:
        maturity = "validation_in_progress"
        maturity_it = "Valutazione in corso"

    # Benchmark Phase 2B (informativo; non altera Signals)
    phase_2b_benchmark: dict[str, Any] = {
        "status": "skipped_below_minimum",
        "benchmark_version": "cecchino_goal_intensity_v4_v5_prospective_benchmark_v1",
        "paired_complete_n": 0,
        "recommended_next_step": recommended_next_step,
    }
    if completed_n >= MIN_PROSPECTIVE_COMPLETED:
        try:
            from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import (
                build_goal_intensity_v4_v5_prospective_benchmark,
                build_phase_2b_benchmark_summary,
            )

            benchmark_payload = build_goal_intensity_v4_v5_prospective_benchmark(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
            phase_2b_benchmark = build_phase_2b_benchmark_summary(benchmark_payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "phase_2b_benchmark_failed error_code=%s", type(exc).__name__
            )
            phase_2b_benchmark = {
                "status": "unavailable",
                "benchmark_version": "cecchino_goal_intensity_v4_v5_prospective_benchmark_v1",
                "paired_complete_n": 0,
                "blocking_reasons": [type(exc).__name__],
                "recommended_next_step": recommended_next_step,
            }

    first_completed = None
    earliest = None
    if bundle is not None:
        completed_rows = [
            s
            for s in db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
                    CecchinoGoalIntensityV5PreviewSnapshot.result_attached_at.is_not(None),
                )
            ).all()
        ]
        if completed_rows:
            ts = min(s.result_attached_at for s in completed_rows if s.result_attached_at)
            first_completed = ts.isoformat() if ts else None
            # earliest review dipende dal gate 200: non calcolabile fino a sample
            earliest = None if completed_n < MIN_PROSPECTIVE_COMPLETED else first_completed

    out = make_json_safe(
        {
            "status": "ok",
            "readiness_version": GOAL_INTENSITY_V5_READINESS_VERSION,
            "policy_version": GOAL_INTENSITY_V5_READINESS_POLICY_VERSION,
            "policy": policy,
            "operational_status": "preview_monitored",
            "operational_status_label_it": "Preview monitorata",
            "scientific_maturity": maturity,
            "scientific_maturity_label_it": maturity_it,
            "signals_integration_status": "blocked",
            "signals_integration_status_label_it": "Bloccata",
            "current_decision": "continue_monitoring",
            "current_decision_label_it": (
                "Continua monitoraggio fino alla revisione manuale"
                if maturity == "ready_for_manual_review"
                else "Continua monitoraggio"
            ),
            "recommended_next_step": recommended_next_step,
            "recommended_next_step_label_it": next_step_labels.get(
                str(recommended_next_step), str(recommended_next_step)
            ),
            "manual_review_status": (
                "eligible" if maturity == "ready_for_manual_review" else "not_eligible"
            ),
            "technical_gates": {"gates": tech_gates},
            "prospective_gates": {"gates": progress_gates},
            "prospective_progress": {
                "completed": completed_n,
                "pending": pending_n,
                "locked": locked_n,
                "incomplete": incomplete_n,
                "error": error_n,
                "snapshots": all_n,
                "minimum": MIN_PROSPECTIVE_COMPLETED,
                "progress_pct": round(
                    (completed_n / MIN_PROSPECTIVE_COMPLETED) * 100.0, 2
                )
                if MIN_PROSPECTIVE_COMPLETED
                else 0.0,
                "remaining": max(0, MIN_PROSPECTIVE_COMPLETED - completed_n),
                "excess": max(0, completed_n - MIN_PROSPECTIVE_COMPLETED),
                "minimum_reached": completed_n >= MIN_PROSPECTIVE_COMPLETED,
                "first_snapshot_at": (normalized.get("coverage_global") or {}).get("first_snapshot"),
                "first_completed_at": first_completed,
                "earliest_theoretical_review_at": earliest,
            },
            "coverage_global": normalized.get("coverage_global"),
            "coverage_in_period": normalized.get("coverage_in_period"),
            "monitoring_normalized": normalized,
            "phase_2b_benchmark": phase_2b_benchmark,
            "scientific": {
                "phase_2b_readiness": phase,
                "phase_2b_benchmark": phase_2b_benchmark,
                "blocking_issues": blocking,
                "calibration": build_calibration(db, date_from=date_from, date_to=date_to),
                "candidates": build_candidates(db, date_from=date_from, date_to=date_to),
            },
            "data_health": health,
            "overview_summary": build_overview(
                db, date_from=date_from, date_to=date_to, competition_id=competition_id
            ),
            "cache_hit": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "competition_id": competition_id,
            },
        }
    )
    with _cache_lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[cache_key] = (time.monotonic(), dict(out))
    return out


def build_goal_intensity_v5_dossier_files(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
) -> dict[str, bytes]:
    from fastapi.encoders import jsonable_encoder

    readiness = build_goal_intensity_v5_readiness(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    policy = build_goal_intensity_v5_readiness_policy_payload()

    def _jb(obj: Any) -> bytes:
        encoded = jsonable_encoder(make_json_safe(obj))
        return (
            json.dumps(encoded, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8")

    readme = (
        "# Intensità Goal Avanzata v5 — Dossier readiness\n\n"
        "Solo readiness/monitoring. Non sostituisce lo ZIP forensic.\n"
        f"Readiness: {GOAL_INTENSITY_V5_READINESS_VERSION}\n"
        f"Policy: {GOAL_INTENSITY_V5_READINESS_POLICY_VERSION}\n"
        "Signals: blocked. Decisione default: continue_monitoring.\n"
    ).encode("utf-8")

    return {
        "README.md": readme,
        "goal_overview.json": _jb(readiness.get("overview_summary")),
        "goal_readiness.json": _jb(readiness),
        "goal_readiness_policy.json": _jb(policy),
        "goal_prospective_progress.json": _jb(readiness.get("prospective_progress")),
        "goal_candidates_summary.json": _jb(
            (readiness.get("scientific") or {}).get("candidates")
        ),
        "goal_calibration_summary.json": _jb(
            (readiness.get("scientific") or {}).get("calibration")
        ),
        "goal_stability_summary.json": _jb({"note": "Vedere export forensic per fold/mese"}),
        "goal_data_health.json": _jb(readiness.get("data_health")),
        "goal_warning.json": _jb(
            {"blocking_issues": (readiness.get("scientific") or {}).get("blocking_issues")}
        ),
        "benchmark_v4_v5_summary.json": _jb(readiness.get("phase_2b_benchmark")),
        "metadata.json": _jb(
            {
                "readiness_version": GOAL_INTENSITY_V5_READINESS_VERSION,
                "policy_version": GOAL_INTENSITY_V5_READINESS_POLICY_VERSION,
                "filters": {
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "competition_id": competition_id,
                },
            }
        ),
    }
