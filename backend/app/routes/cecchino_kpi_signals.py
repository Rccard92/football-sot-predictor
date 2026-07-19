"""Route Segnali KPI Cecchino (modulo separato da Monitoraggio Segnali)."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.schemas.cecchino_kpi_signals import (
    CecchinoKpiSignalsBackfillBody,
    CecchinoKpiSignalsRevaluateBody,
    CecchinoPurchasabilityValidationJobBody,
    CecchinoPurchasabilityValidationSyncBody,
)
from app.services.cecchino.cecchino_kpi_signals import (
    backfill_kpi_signals,
    revaluate_kpi_signals_for_range,
)
from app.services.cecchino.cecchino_kpi_signals_aggregation import (
    build_kpi_signals_summary,
    export_kpi_signals_csv,
    list_kpi_signal_activations,
)
from app.services.cecchino.cecchino_historical_reliability import (
    build_historical_reliability_for_panel,
)
from app.services.cecchino.cecchino_purchasability_candidate import (
    build_purchasability_candidate_for_fixture,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_purchasability_features_for_fixture,
)
from app.services.cecchino.cecchino_purchasability_validation import (
    build_purchasability_validation_health,
    build_purchasability_validation_rows,
    export_purchasability_validation_csv,
    sync_and_evaluate_purchasability_validation_range,
)
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    build_purchasability_promotion_readiness,
    build_purchasability_validation_summary,
)
from app.services.cecchino.cecchino_purchasability_validation_jobs import (
    PurchasabilityValidationJobConflict,
    PurchasabilityValidationJobNotFound,
    get_purchasability_validation_job,
    get_purchasability_validation_job_result,
    start_purchasability_validation_job,
)

router = APIRouter(prefix="/cecchino/kpi-signals", tags=["cecchino-kpi-signals"])
admin_router = APIRouter(prefix="/admin/cecchino/kpi-signals", tags=["admin-cecchino-kpi-signals"])
validation_admin_router = APIRouter(
    prefix="/admin/cecchino/purchasability-validation",
    tags=["admin-cecchino-purchasability-validation"],
)
logger = logging.getLogger(__name__)


def _summary_payload(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None,
    selection_key: str | None,
    normalized_market: str | None,
    evaluation_status: str | None,
    league_name: str | None,
    country_name: str | None,
    only_current: bool,
    include_diagnostics: bool,
) -> dict:
    return build_kpi_signals_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        include_diagnostics=include_diagnostics,
    )


@router.get("/summary")
def kpi_signals_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    rating_bucket: str | None = Query(None),
    selection_key: str | None = Query(None),
    normalized_market: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    league_name: str | None = Query(None),
    country_name: str | None = Query(None),
    only_current: bool = Query(True),
    include_diagnostics: bool = Query(True),
    db: Session = Depends(get_db),
):
    payload = _summary_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        include_diagnostics=include_diagnostics,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/activations")
def kpi_signals_activations(
    date_from: date = Query(...),
    date_to: date = Query(...),
    rating_bucket: str | None = Query(None),
    selection_key: str | None = Query(None),
    normalized_market: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    league_name: str | None = Query(None),
    country_name: str | None = Query(None),
    only_current: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    payload = list_kpi_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/historical-reliability")
def kpi_signals_historical_reliability(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Affidabilità storica v1.1 — read-only, batch per Pannello KPI."""
    payload = build_historical_reliability_for_panel(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability-empirical")
def kpi_signals_purchasability_empirical(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """LEGACY alias — Affidabilità storica (ex Acquistabilità empirica).

    Preferire GET /api/cecchino/kpi-signals/historical-reliability.
    """
    payload = build_historical_reliability_for_panel(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    payload = {
        **payload,
        "deprecated": True,
        "replacement_endpoint": "/api/cecchino/kpi-signals/historical-reliability",
    }
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability-preview/features/{today_fixture_id}")
def kpi_signals_purchasability_preview_features(
    today_fixture_id: int,
    db: Session = Depends(get_db),
):
    """Debug read-only — feature Acquistabilità V1 Preview (Fase 2/5).

    Solo snapshot salvati. Nessuno score, nessuna scrittura, nessuna API esterna.
    """
    fixture = db.get(CecchinoTodayFixture, today_fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="today_fixture_not_found")
    payload = build_purchasability_features_for_fixture(fixture)
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability-preview/candidate/{today_fixture_id}")
def kpi_signals_purchasability_preview_candidate(
    today_fixture_id: int,
    db: Session = Depends(get_db),
):
    """Debug read-only — candidato Acquistabilità V1 Preview (candidate_2 attivo).

    Feature layer → balanced_geometric_v1_1. Nessuna scrittura.
    """
    fixture = db.get(CecchinoTodayFixture, today_fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="today_fixture_not_found")
    payload = build_purchasability_candidate_for_fixture(fixture)
    output = getattr(fixture, "cecchino_output_json", None)
    persisted = None
    if isinstance(output, dict):
        persisted = output.get("purchasability_preview")
    if isinstance(persisted, dict) and persisted.get("candidate_version"):
        payload["persisted_snapshot_meta"] = {
            "available": True,
            "candidate_version": persisted.get("candidate_version"),
            "hash": persisted.get("full_candidate_payload_sha256"),
            "source_snapshot_at": persisted.get("source_snapshot_at"),
        }
    else:
        payload["persisted_snapshot_meta"] = {"available": False}
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/export.csv")
def kpi_signals_export_csv(
    date_from: date = Query(...),
    date_to: date = Query(...),
    rating_bucket: str | None = Query(None),
    selection_key: str | None = Query(None),
    normalized_market: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    league_name: str | None = Query(None),
    country_name: str | None = Query(None),
    only_current: bool = Query(True),
    db: Session = Depends(get_db),
):
    csv_text = export_kpi_signals_csv(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
    )
    return PlainTextResponse(content=csv_text, media_type="text/csv")


@admin_router.post("/backfill")
def kpi_signals_backfill(
    body: CecchinoKpiSignalsBackfillBody,
    db: Session = Depends(get_db),
):
    try:
        payload = backfill_kpi_signals(
            db,
            date_from=body.date_from,
            date_to=body.date_to,
            only_missing=body.only_missing,
            evaluate_after=body.evaluate_after,
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except Exception as exc:
        logger.exception("KPI signals backfill fatal error")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": "kpi_signals_backfill_failed",
                "message": str(exc)[:500],
                "errors": [],
            },
        )


@admin_router.post("/revaluate")
def kpi_signals_revaluate(
    body: CecchinoKpiSignalsRevaluateBody,
    db: Session = Depends(get_db),
):
    payload = revaluate_kpi_signals_for_range(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
    )
    return JSONResponse(content=jsonable_encoder(payload))


# --- Acquistabilità Validazione Fase 5 ---


@router.get("/purchasability-validation/health")
def purchasability_validation_health(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_validation_health(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability-validation/summary")
def purchasability_validation_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    candidate_version: str | None = Query(None),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    score_band: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    source_cohort: str | None = Query(None),
    promotion_eligible_only: bool = Query(True),
    bootstrap_iterations: int = Query(200, ge=10, le=2000),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_validation_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version,
        competition_id=competition_id,
        market_key=market_key,
        score_band=score_band,
        evaluation_status=evaluation_status,
        source_cohort=source_cohort,
        promotion_eligible_only=promotion_eligible_only,
        bootstrap_iterations=bootstrap_iterations,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability-validation/rows")
def purchasability_validation_rows(
    date_from: date = Query(...),
    date_to: date = Query(...),
    candidate_version: str | None = Query(None),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    score_band: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    source_cohort: str | None = Query(None),
    promotion_eligible_only: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_validation_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version,
        competition_id=competition_id,
        market_key=market_key,
        score_band=score_band,
        evaluation_status=evaluation_status,
        source_cohort=source_cohort,
        promotion_eligible_only=promotion_eligible_only,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability-validation/readiness")
def purchasability_validation_readiness(
    date_from: date = Query(...),
    date_to: date = Query(...),
    candidate_version: str | None = Query(None),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    bootstrap_iterations: int = Query(200, ge=10, le=2000),
    promotion_eligible_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_promotion_readiness(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version,
        competition_id=competition_id,
        market_key=market_key,
        bootstrap_iterations=bootstrap_iterations,
        promotion_eligible_only=promotion_eligible_only,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability-validation/export.csv")
def purchasability_validation_export_csv(
    date_from: date = Query(...),
    date_to: date = Query(...),
    candidate_version: str | None = Query(None),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    score_band: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    source_cohort: str | None = Query(None),
    promotion_eligible_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    csv_text = export_purchasability_validation_csv(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version,
        competition_id=competition_id,
        market_key=market_key,
        score_band=score_band,
        evaluation_status=evaluation_status,
        source_cohort=source_cohort,
        promotion_eligible_only=promotion_eligible_only,
    )
    return PlainTextResponse(content=csv_text, media_type="text/csv")


@router.post("/purchasability-validation/jobs", status_code=202)
def purchasability_validation_start_job(
    body: CecchinoPurchasabilityValidationJobBody,
):
    try:
        payload = start_purchasability_validation_job(
            date_from=body.date_from,
            date_to=body.date_to,
            candidate_version=body.candidate_version,
            competition_id=body.competition_id,
            market_key=body.market_key,
            bootstrap_iterations=body.bootstrap_iterations,
            promotion_eligible_only=body.promotion_eligible_only,
        )
        return JSONResponse(status_code=202, content=jsonable_encoder(payload))
    except PurchasabilityValidationJobConflict as exc:
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "code": "purchasability_validation_job_already_running",
                "active_job_id": exc.active_job_id,
                "active_filters": exc.active_filters,
            },
        )


@router.get("/purchasability-validation/jobs/{job_id}")
def purchasability_validation_job_status(job_id: str):
    try:
        payload = get_purchasability_validation_job(job_id)
        return JSONResponse(content=jsonable_encoder(payload))
    except PurchasabilityValidationJobNotFound:
        raise HTTPException(status_code=404, detail="validation_job_not_found_or_expired")


@router.get("/purchasability-validation/jobs/{job_id}/result")
def purchasability_validation_job_result(job_id: str):
    try:
        payload = get_purchasability_validation_job_result(job_id)
        return JSONResponse(content=jsonable_encoder(payload))
    except PurchasabilityValidationJobNotFound:
        raise HTTPException(status_code=404, detail="validation_job_not_found_or_expired")


@validation_admin_router.post("/sync")
def purchasability_validation_admin_sync(
    body: CecchinoPurchasabilityValidationSyncBody,
    db: Session = Depends(get_db),
):
    try:
        payload = sync_and_evaluate_purchasability_validation_range(
            db,
            date_from=body.date_from,
            date_to=body.date_to,
            include_legacy_derived=body.include_legacy_derived,
            evaluate_after=body.evaluate_after,
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except Exception as exc:
        logger.exception("purchasability validation sync fatal error")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": "purchasability_validation_sync_failed",
                "message": str(exc)[:500],
            },
        )
