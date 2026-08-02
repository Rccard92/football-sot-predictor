"""Helper ufficiale Acquistabilità V3 per report/dashboard Run (STEP 3C.2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.models.cecchino_lab_purchasability_v3_replay_run import (
    STATUS_COMPLETED_WITH_WARNINGS,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics import (
    PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
    get_purchasability_v3_replay_analytics,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_export import (
    PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_resolver import (
    LEGACY_PURCHASABILITY_FALLBACK_ALLOWED,
    official_purchasability_unavailable_payload,
    try_resolve_official_purchasability_v3_replay,
)


def load_official_v3_purch_score_index(
    db: Session, replay_id: int
) -> dict[tuple[int, str], Any]:
    """Mappa (source_snapshot_id, market_key) → score dai risultati replay V3."""
    R = CecchinoLabPurchasabilityV3ReplayResult
    rows = db.execute(
        select(R.source_snapshot_id, R.market_key, R.score).where(
            R.replay_run_id == int(replay_id)
        )
    ).all()
    out: dict[tuple[int, str], Any] = {}
    for snap_id, market_key, score in rows:
        out[(int(snap_id), str(market_key))] = score
    return out


def resolve_v3_purch_band_score_index(
    db: Session, source_scan_run_id: int, filters: dict[str, Any]
) -> dict[tuple[int, str], Any] | None:
    """Indice score V3 per filtro banda, o None se il filtro va ignorato.

    None se ``purchasability_band`` non è impostato oppure non c'è replay ufficiale
    (in quel caso non si legge V2 e non si applica il filtro).
    """
    if not filters.get("purchasability_band"):
        return None
    replay = try_resolve_official_purchasability_v3_replay(db, source_scan_run_id)
    if replay is None:
        return None
    return load_official_v3_purch_score_index(db, int(replay.id))


def _by_market_summary(by_market: Any) -> dict[str, Any]:
    if not isinstance(by_market, dict):
        return {}
    summary: dict[str, Any] = {}
    for mk, payload in by_market.items():
        if not isinstance(payload, dict):
            summary[str(mk)] = payload
            continue
        summary[str(mk)] = {
            "evaluations_total": payload.get("evaluations_total"),
            "scored": payload.get("scored"),
            "gate_failed": payload.get("gate_failed"),
            "unavailable": payload.get("unavailable"),
            "real_quote": payload.get("real_quote"),
            "derived_quote": payload.get("derived_quote"),
            "real": payload.get("real"),
            "synthetic": payload.get("synthetic"),
        }
    return summary


def build_official_purchasability_section(
    db: Session, source_scan_run_id: int
) -> dict[str, Any]:
    """Sezione Acquistabilità per Sintesi/report: solo V3, mai legacy."""
    replay = try_resolve_official_purchasability_v3_replay(db, source_scan_run_id)
    if replay is None:
        return official_purchasability_unavailable_payload(
            source_scan_run_id=source_scan_run_id
        )

    analytics = get_purchasability_v3_replay_analytics(db, int(replay.id))
    universes = analytics.get("universes") or {}
    recon = analytics.get("reconciliation") or {}
    quote_buckets = recon.get("quote_buckets") or {}
    status = analytics.get("status") or (
        "ready_with_warnings"
        if str(replay.status) == STATUS_COMPLETED_WITH_WARNINGS
        else "ready"
    )

    return {
        "status": status,
        "official_purchasability_version": "V3",
        "official_version": "V3",
        "source_type": "historical_replay",
        "official_purchasability_source": "replay_v3",
        "replay_id": int(replay.id),
        "replay_status": str(replay.status),
        "formula_version": replay.formula_version,
        "replay_engine_version": replay.replay_engine_version,
        "replay_schema_version": replay.replay_schema_version,
        "candidate_version": replay.candidate_version,
        "analytics_schema_version": analytics.get("schema_version")
        or PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
        "export_schema_version": PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
        "results_persisted": int(replay.results_persisted or 0),
        "evaluations_total": int(replay.evaluations_total or 0),
        "scored": universes.get("SCORED_EVALUATIONS", int(replay.scored_count or 0)),
        "gate_failed": universes.get(
            "GATE_FAILED_EVALUATIONS", int(replay.gate_failed_count or 0)
        ),
        "unavailable": universes.get(
            "UNAVAILABLE_EVALUATIONS", int(replay.unavailable_count or 0)
        ),
        "real_quote_count": quote_buckets.get(
            "real", int(replay.real_quote_count or 0)
        ),
        "derived_quote_count": quote_buckets.get(
            "derived", int(replay.derived_quote_count or 0)
        ),
        "formula_recomputed": False,
        "reconciliation": recon,
        "reconciliation_status": recon.get("status"),
        "universes": universes,
        "score_distribution": analytics.get("score_distribution"),
        "gate_analysis": analytics.get("gate_analysis"),
        "performance_real": analytics.get("performance_real"),
        "performance_synthetic": analytics.get("performance_synthetic"),
        "by_market": _by_market_summary(analytics.get("by_market")),
        "family_decisions": analytics.get("family_decisions"),
        "legacy_purchasability_read": False,
        "legacy_fallback_allowed": LEGACY_PURCHASABILITY_FALLBACK_ALLOWED,
        "legacy_fallback_used": False,
        "analytics": analytics,
        "analytics_metadata": analytics.get("metadata"),
    }


def build_official_dashboard_purchasability(
    db: Session, source_scan_run_id: int, *, filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Payload dashboard sezione Acquistabilità (V3 only)."""
    section = build_official_purchasability_section(db, source_scan_run_id)
    section["run_id"] = int(source_scan_run_id)
    section["filters"] = filters or {}
    if section.get("status") == "unavailable":
        section["message"] = section.get("message") or (
            "Acquistabilità V3 non disponibile"
        )
    return section


def build_official_match_purchasability(
    db: Session, source_scan_run_id: int, snapshot_id: int
) -> dict[str, Any]:
    """Riferimento Acquistabilità V3 per match detail — mai compatibility JSON."""
    replay = try_resolve_official_purchasability_v3_replay(db, source_scan_run_id)
    if replay is None:
        return official_purchasability_unavailable_payload(
            source_scan_run_id=source_scan_run_id
        )

    R = CecchinoLabPurchasabilityV3ReplayResult
    rows = list(
        db.scalars(
            select(R)
            .options(
                load_only(
                    R.id,
                    R.market_key,
                    R.market_family,
                    R.score,
                    R.raw_score,
                    R.score_class,
                    R.gate_status,
                    R.calculation_status,
                    R.is_real_book_quote,
                    R.is_derived_quote,
                    R.quote_quality,
                    R.performance_type,
                    R.edge_pct,
                    R.value_score,
                    R.quality_score,
                )
            )
            .where(
                R.replay_run_id == int(replay.id),
                R.source_snapshot_id == int(snapshot_id),
            )
            .order_by(R.market_key.asc())
        ).all()
    )

    status = (
        "ready_with_warnings"
        if str(replay.status) == STATUS_COMPLETED_WITH_WARNINGS
        else "ready"
    )
    markets = [
        {
            "market_key": r.market_key,
            "market_family": r.market_family,
            "score": int(r.score) if r.score is not None else None,
            "raw_score": float(r.raw_score) if r.raw_score is not None else None,
            "score_class": r.score_class,
            "gate_status": r.gate_status,
            "calculation_status": r.calculation_status,
            "is_real_book_quote": bool(r.is_real_book_quote),
            "is_derived_quote": bool(r.is_derived_quote),
            "quote_quality": r.quote_quality,
            "performance_type": r.performance_type,
            "edge_pct": float(r.edge_pct) if r.edge_pct is not None else None,
            "value_score": float(r.value_score) if r.value_score is not None else None,
            "quality_score": (
                float(r.quality_score) if r.quality_score is not None else None
            ),
        }
        for r in rows
    ]
    return {
        "status": status,
        "official_version": "V3",
        "official_purchasability_version": "V3",
        "source_type": "historical_replay",
        "official_purchasability_source": "replay_v3",
        "source_scan_run_id": int(source_scan_run_id),
        "snapshot_id": int(snapshot_id),
        "replay_id": int(replay.id),
        "replay_status": str(replay.status),
        "formula_version": replay.formula_version,
        "replay_engine_version": replay.replay_engine_version,
        "candidate_version": replay.candidate_version,
        "markets": markets,
        "markets_count": len(markets),
        "legacy_purchasability_read": False,
        "legacy_fallback_allowed": LEGACY_PURCHASABILITY_FALLBACK_ALLOWED,
        "legacy_fallback_used": False,
        "formula_recomputed": False,
    }


__all__ = [
    "build_official_dashboard_purchasability",
    "build_official_match_purchasability",
    "build_official_purchasability_section",
    "load_official_v3_purch_score_index",
    "resolve_v3_purch_band_score_index",
]
