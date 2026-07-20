"""Route Monitoraggio Moduli Cecchino — overview + analysis pack."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino.cecchino_module_monitoring_exports import (
    VALID_MODULE_KEYS,
    build_module_analysis_pack_audit,
    build_module_analysis_pack_zip,
    build_module_export_status,
    build_module_monitoring_overview,
    build_module_rows_csv,
    build_module_summary_payload,
    build_modules_analysis_packs_audit,
)
from app.services.cecchino.cecchino_module_monitoring_reconciliation import (
    build_purchasability_evaluation_cardinality_report,
)

router = APIRouter(
    prefix="/cecchino/module-monitoring",
    tags=["cecchino-module-monitoring"],
)


@router.get("/overview")
def module_monitoring_overview(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    payload = build_module_monitoring_overview(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/analysis-packs-audit")
def module_monitoring_all_analysis_packs_audit(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    payload = build_modules_analysis_packs_audit(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        include_rows=include_rows,
        include_debug=include_debug,
        source_cohort_filter=source_cohort or "all",
    )
    return JSONResponse(content=jsonable_encoder(payload))


# IMPORTANT: dedicated paths BEFORE /{module_key} routes to avoid conflicts
@router.get("/purchasability-cardinality")
def purchasability_cardinality_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_evaluation_cardinality_report(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/balance-v5/empirical/health")
def balance_empirical_health(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_health,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_health(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        )
    )


@router.get("/balance-v5/empirical/summary")
def balance_empirical_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_summary,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_summary(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        )
    )


@router.get("/balance-v5/empirical/rows")
def balance_empirical_rows(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        query_balance_empirical_rows,
    )

    return JSONResponse(
        content=jsonable_encoder(
            query_balance_empirical_rows(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
                evaluation_status=evaluation_status,
                f36_class=f36_class,
                dominance_class=dominance_class,
                draw_credibility_class=draw_credibility_class,
                gap_class=gap_class,
                limit=limit,
                offset=offset,
            )
        )
    )


@router.get("/balance-v5/empirical/target-contract")
def balance_empirical_target_contract():
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_target_contract,
    )

    return JSONResponse(content=jsonable_encoder(build_balance_empirical_target_contract()))


@router.get("/balance-v5/empirical/cardinality")
def balance_empirical_cardinality(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_cardinality,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_cardinality(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        )
    )


def _analysis_filters_from_query(
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    source_cohort: str | None,
    country_name: str | None,
    f36_class: str | None,
    dominance_class: str | None,
    dominance_selection: str | None,
    draw_credibility_class: str | None,
    gap_class: str | None,
) -> dict:
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        normalize_analysis_filters,
    )

    return normalize_analysis_filters(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort or "all",
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )


@router.get("/balance-v5/empirical/analysis/overview")
def balance_empirical_analysis_overview(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        build_balance_empirical_analysis_overview,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_analysis_overview(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort or "all",
            )
        )
    )


@router.get("/balance-v5/empirical/analysis/f36")
def balance_empirical_analysis_f36(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    country_name: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    dominance_selection: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        get_f36_analysis,
    )

    filters = _analysis_filters_from_query(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    return JSONResponse(content=jsonable_encoder(get_f36_analysis(db, filters=filters)))


@router.get("/balance-v5/empirical/analysis/dominance")
def balance_empirical_analysis_dominance(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    country_name: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    dominance_selection: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        get_dominance_analysis,
    )

    filters = _analysis_filters_from_query(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    return JSONResponse(
        content=jsonable_encoder(get_dominance_analysis(db, filters=filters))
    )


@router.get("/balance-v5/empirical/analysis/draw-credibility")
def balance_empirical_analysis_draw_credibility(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    country_name: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    dominance_selection: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        get_draw_credibility_analysis,
    )

    filters = _analysis_filters_from_query(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    return JSONResponse(
        content=jsonable_encoder(get_draw_credibility_analysis(db, filters=filters))
    )


@router.get("/balance-v5/empirical/analysis/gap")
def balance_empirical_analysis_gap(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    country_name: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    dominance_selection: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        get_gap_analysis,
    )

    filters = _analysis_filters_from_query(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    return JSONResponse(content=jsonable_encoder(get_gap_analysis(db, filters=filters)))


@router.get("/balance-v5/empirical/analysis/stability")
def balance_empirical_analysis_stability(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    country_name: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    dominance_selection: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        build_balance_empirical_stability_analysis,
    )

    filters = _analysis_filters_from_query(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_stability_analysis(db, filters=filters)
        )
    )


@router.get("/balance-v5/empirical/analysis/data-health")
def balance_empirical_analysis_data_health(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    country_name: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    dominance_selection: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        build_balance_empirical_data_health_analysis,
    )

    filters = _analysis_filters_from_query(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_data_health_analysis(db, filters=filters)
        )
    )


@router.get("/balance-v5/empirical/analysis/dependency")
def balance_empirical_analysis_dependency(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query("all"),
    country_name: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    dominance_selection: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
        build_balance_empirical_dependency_analysis,
    )

    filters = _analysis_filters_from_query(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_dependency_analysis(db, filters=filters)
        )
    )


class BalanceEmpiricalAnalysisJobBody(BaseModel):
    date_from: date
    date_to: date
    competition_id: int | None = None
    source_cohort: str | None = "all"
    country_name: str | None = None
    f36_class: str | None = None
    dominance_class: str | None = None
    dominance_selection: str | None = None
    draw_credibility_class: str | None = None
    gap_class: str | None = None
    bootstrap_iterations: int = Field(default=2000, ge=500, le=10000)


@router.post("/balance-v5/empirical/analysis/jobs", status_code=202)
def balance_empirical_analysis_jobs_create(
    body: BalanceEmpiricalAnalysisJobBody,
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis_jobs import (
        BalanceEmpiricalAnalysisJobConflict,
        enqueue_balance_empirical_analysis_job,
        normalize_job_filters,
    )

    del db  # job apre la propria sessione
    try:
        filters = normalize_job_filters(**body.model_dump())
        payload = enqueue_balance_empirical_analysis_job(filters)
        return JSONResponse(status_code=202, content=jsonable_encoder(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BalanceEmpiricalAnalysisJobConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_already_running",
                "active_job_id": exc.active_job_id,
            },
        ) from exc


@router.get("/balance-v5/empirical/analysis/jobs/{job_id}")
def balance_empirical_analysis_jobs_get(job_id: str):
    from app.services.cecchino.cecchino_balance_v5_empirical_analysis_jobs import (
        BalanceEmpiricalAnalysisJobNotFound,
        get_balance_empirical_analysis_job,
    )

    try:
        return JSONResponse(
            content=jsonable_encoder(get_balance_empirical_analysis_job(job_id))
        )
    except BalanceEmpiricalAnalysisJobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _readiness_filters(
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
):
    return {
        "date_from": date_from,
        "date_to": date_to,
        "competition_id": competition_id,
    }


@router.get("/balance-v5/readiness/overview")
def balance_readiness_overview(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        build_balance_readiness_overview,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_readiness_overview(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
        )
    )


@router.get("/balance-v5/readiness/gates")
def balance_readiness_gates(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        build_balance_scientific_gates,
        build_balance_technical_gates,
    )

    filters = _readiness_filters(date_from, date_to, competition_id)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "technical": build_balance_technical_gates(db, filters=filters),
                "scientific": build_balance_scientific_gates(db, filters=filters),
            }
        )
    )


@router.get("/balance-v5/readiness/pillars")
def balance_readiness_pillars(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        build_balance_pillar_readiness,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_pillar_readiness(
                db, filters=_readiness_filters(date_from, date_to, competition_id)
            )
        )
    )


@router.get("/balance-v5/readiness/prospective-progress")
def balance_readiness_prospective_progress(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        build_balance_prospective_progress,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_prospective_progress(
                db, filters=_readiness_filters(date_from, date_to, competition_id)
            )
        )
    )


@router.get("/balance-v5/readiness/history")
def balance_readiness_history(
    competition_id: int | None = Query(None),
    limit: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        list_balance_readiness_history,
    )

    return JSONResponse(
        content=jsonable_encoder(
            list_balance_readiness_history(
                db, competition_id=competition_id, limit=limit
            )
        )
    )


@router.get("/balance-v5/readiness/decision-contract")
def balance_readiness_decision_contract():
    from app.services.cecchino.cecchino_balance_v5_readiness import (
        build_balance_decision_contract,
    )

    return JSONResponse(content=jsonable_encoder(build_balance_decision_contract()))


@router.get("/balance-v5/readiness/export")
def balance_readiness_export(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Dossier readiness ZIP (non sostituisce forensic)."""
    import io
    import logging
    import time
    import zipfile

    from fastapi.responses import StreamingResponse

    from app.services.cecchino.cecchino_balance_v5_readiness import (
        build_balance_readiness_dossier_files,
    )

    log = logging.getLogger(__name__)
    started = time.perf_counter()
    log.info(
        "balance_readiness_dossier_started date_from=%s date_to=%s competition_id=%s",
        date_from,
        date_to,
        competition_id,
    )
    try:
        files = build_balance_readiness_dossier_files(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in files.items():
                zf.writestr(name, data)
        buf.seek(0)
        archive_size = buf.getbuffer().nbytes
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.info(
            "balance_readiness_dossier_completed date_from=%s date_to=%s "
            "competition_id=%s file_count=%s archive_size=%s elapsed_ms=%s",
            date_from,
            date_to,
            competition_id,
            len(files),
            archive_size,
            elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.exception(
            "balance_readiness_dossier_failed date_from=%s date_to=%s "
            "competition_id=%s error_type=%s elapsed_ms=%s",
            date_from,
            date_to,
            competition_id,
            type(exc).__name__,
            elapsed_ms,
        )
        raise

    df = (date_from or date.today()).isoformat()
    dt = (date_to or date.today()).isoformat()
    filename = f"SOT_BALANCE_V5_READINESS_{df}_{dt}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{module_key}/analysis-pack-audit")
def module_monitoring_analysis_pack_audit(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        payload = build_module_analysis_pack_audit(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            include_debug=include_debug,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/{module_key}/export-status")
def module_monitoring_export_status(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        payload = build_module_export_status(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/{module_key}/analysis-pack.zip")
def module_monitoring_analysis_pack(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        data, filename = build_module_analysis_pack_zip(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            include_debug=include_debug,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{module_key}/summary.json")
def module_monitoring_summary_json(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        payload = build_module_summary_payload(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    raw = jsonable_encoder(payload)
    body = __import__("json").dumps(raw, ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="SOT_MONITOR_{module_key}_summary.json"'
            )
        },
    )


@router.get("/{module_key}/rows.csv")
def module_monitoring_rows_csv(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    _ = include_rows, include_debug
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        data, filename = build_module_rows_csv(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
