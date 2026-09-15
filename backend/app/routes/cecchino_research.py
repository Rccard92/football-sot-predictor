"""Route admin ricerca Cecchino — audit Credibilità X / Intensità Goal v5 (offline)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_pattern_discovery import (
    CecchinoPatternDiscoveryStartBody,
    CecchinoPatternGridStartBody,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.schemas.cecchino_draw_credibility_research import (
    CecchinoDrawCredibilityAuditBody,
    CecchinoDrawCredibilityDatasetBody,
    CecchinoDrawCredibilityDatasetExportBody,
    CecchinoDrawCredibilityModelComparisonBody,
    CecchinoDrawCredibilityStatisticsBody,
)
from app.schemas.cecchino_goal_intensity_v5_research import (
    CecchinoGoalIntensityV5PreviewFreezeBody,
    CecchinoGoalIntensityV5PreviewRefreshBody,
)
from app.services.cecchino.cecchino_draw_credibility_dataset import (
    build_draw_credibility_historical_dataset,
    dataset_csv_filename,
    stream_draw_credibility_dataset_csv,
)
from app.services.cecchino.cecchino_draw_credibility_model_comparison import (
    build_draw_credibility_model_comparison,
)
from app.services.cecchino.cecchino_draw_credibility_research import (
    build_draw_credibility_coverage_audit,
)
from app.services.cecchino.cecchino_draw_credibility_statistics import (
    build_draw_credibility_statistical_analysis,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    build_prospective_monitoring,
    freeze_preview_bundle,
    get_preview_detail,
    list_preview_snapshots,
    preview_export_filename,
    refresh_preview,
    stream_preview_export,
)
from app.services.cecchino.cecchino_purchasability_audit import (
    EXPORT_KINDS as PURCHASABILITY_EXPORT_KINDS,
    build_purchasability_audit,
    build_purchasability_dataset,
    build_purchasability_markets_payload,
    purchasability_export_filename,
    stream_purchasability_export,
)
from app.services.cecchino.cecchino_purchasability_statistical_research import (
    EXPORT_KINDS as PURCHASABILITY_STAT_EXPORT_KINDS,
    build_purchasability_statistical_research,
    build_statistical_candidates_payload,
    build_statistical_features_payload,
    build_statistical_markets_payload,
    statistical_export_filename,
    stream_statistical_export,
)
from app.services.cecchino.cecchino_purchasability_residual_reliability import (
    EXPORT_KINDS as PURCHASABILITY_RESIDUAL_EXPORT_KINDS,
    build_purchasability_residual_reliability,
    residual_export_filename,
    stream_residual_export,
)
from app.services.cecchino.cecchino_purchasability_research_jobs import (
    PurchasabilityResearchJobConflict,
    PurchasabilityResearchJobNotFound,
    enqueue_purchasability_research_job,
    get_active_job,
    get_job,
)
from app.schemas.cecchino_purchasability_research import (
    CecchinoPurchasabilityStatisticalJobBody,
)

router = APIRouter(prefix="/admin/cecchino/research", tags=["admin-cecchino-research"])


@router.post("/draw-credibility/audit")
def post_draw_credibility_audit(
    body: CecchinoDrawCredibilityAuditBody,
    db: Session = Depends(get_db),
):
    payload = build_draw_credibility_coverage_audit(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        only_eligible=body.only_eligible,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/draw-credibility/dataset")
def post_draw_credibility_dataset(
    body: CecchinoDrawCredibilityDatasetBody,
    db: Session = Depends(get_db),
):
    payload = build_draw_credibility_historical_dataset(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        cohort=body.cohort,
        page=body.page,
        page_size=body.page_size,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/draw-credibility/dataset/export.csv")
def post_draw_credibility_dataset_export_csv(
    body: CecchinoDrawCredibilityDatasetExportBody,
    db: Session = Depends(get_db),
):
    filename = dataset_csv_filename(
        cohort=body.cohort,
        date_from=body.date_from,
        date_to=body.date_to,
    )
    stream = stream_draw_credibility_dataset_csv(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        cohort=body.cohort,
    )

    def _iter():
        for chunk in stream:
            yield chunk

    return StreamingResponse(
        _iter(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/draw-credibility/statistical-analysis")
def post_draw_credibility_statistical_analysis(
    body: CecchinoDrawCredibilityStatisticsBody,
    db: Session = Depends(get_db),
):
    payload = build_draw_credibility_statistical_analysis(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        bin_count=body.bin_count,
        min_group_size=body.min_group_size,
        bootstrap_iterations=body.bootstrap_iterations,
        random_seed=body.random_seed,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/draw-credibility/model-comparison")
def post_draw_credibility_model_comparison(
    body: CecchinoDrawCredibilityModelComparisonBody,
    db: Session = Depends(get_db),
):
    payload = build_draw_credibility_model_comparison(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        final_holdout_pct=body.final_holdout_pct,
        inner_splits=body.inner_splits,
        bootstrap_iterations=body.bootstrap_iterations,
        random_seed=body.random_seed,
    )
    return JSONResponse(content=jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Preview Fase 2A
# ---------------------------------------------------------------------------


@router.post("/goal-intensity-v5/preview/freeze")
def post_goal_intensity_v5_preview_freeze(
    body: CecchinoGoalIntensityV5PreviewFreezeBody,
    db: Session = Depends(get_db),
):
    payload = freeze_preview_bundle(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        minimum_history_sample=body.minimum_history_sample,
        bootstrap_iterations=body.bootstrap_iterations,
        random_seed=body.random_seed,
        enforce_expected_hashes=True,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/goal-intensity-v5/preview/refresh")
def post_goal_intensity_v5_preview_refresh(
    body: CecchinoGoalIntensityV5PreviewRefreshBody,
    db: Session = Depends(get_db),
):
    payload = refresh_preview(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/goal-intensity-v5/preview")
def get_goal_intensity_v5_preview(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    payload = list_preview_snapshots(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/goal-intensity-v5/preview/monitoring")
def get_goal_intensity_v5_preview_monitoring(db: Session = Depends(get_db)):
    payload = build_prospective_monitoring(db)
    return JSONResponse(content=jsonable_encoder(payload))


def _goal_intensity_preview_export(kind: str, db: Session):
    filename = preview_export_filename(kind)  # type: ignore[arg-type]
    stream = stream_preview_export(db, kind=kind)  # type: ignore[arg-type]
    media = "application/json" if filename.endswith(".json") else "text/csv; charset=utf-8"

    def _iter():
        for chunk in stream:
            yield chunk

    return StreamingResponse(
        _iter(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/goal-intensity-v5/preview/export/summary")
def get_goal_intensity_v5_preview_export_summary(db: Session = Depends(get_db)):
    return _goal_intensity_preview_export("preview_summary", db)


@router.get("/goal-intensity-v5/preview/export/snapshots")
def get_goal_intensity_v5_preview_export_snapshots(db: Session = Depends(get_db)):
    return _goal_intensity_preview_export("preview_snapshots", db)


@router.get("/goal-intensity-v5/preview/export/completed-results")
def get_goal_intensity_v5_preview_export_completed(db: Session = Depends(get_db)):
    return _goal_intensity_preview_export("preview_completed_results", db)


@router.get("/goal-intensity-v5/preview/export/candidate-monitoring")
def get_goal_intensity_v5_preview_export_monitoring(db: Session = Depends(get_db)):
    return _goal_intensity_preview_export("preview_candidate_monitoring", db)


@router.get("/goal-intensity-v5/preview/export/calibration")
def get_goal_intensity_v5_preview_export_calibration(db: Session = Depends(get_db)):
    return _goal_intensity_preview_export("preview_calibration", db)


@router.get("/goal-intensity-v5/preview/export/bundle-definition")
def get_goal_intensity_v5_preview_export_bundle(db: Session = Depends(get_db)):
    return _goal_intensity_preview_export("preview_bundle_definition", db)


@router.get("/goal-intensity-v5/preview/{today_fixture_id}")
def get_goal_intensity_v5_preview_detail(
    today_fixture_id: int,
    db: Session = Depends(get_db),
):
    payload = get_preview_detail(db, today_fixture_id)
    return JSONResponse(content=jsonable_encoder(payload))


# --- Indice di Acquistabilità Fase 1 (read-only) ---


@router.get("/purchasability/audit")
def get_purchasability_audit(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    market_family: str | None = Query(default=None),
    book_source: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_audit(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        book_source=book_source,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability/dataset")
def get_purchasability_dataset(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    market_family: str | None = Query(default=None),
    book_source: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_dataset(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        book_source=book_source,
        status=status,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability/markets")
def get_purchasability_markets(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_markets_payload(
        db, date_from=date_from, date_to=date_to
    )
    return JSONResponse(content=jsonable_encoder(payload))


def _purchasability_export_response(
    kind: str,
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
    market_family: str | None,
    book_source: str | None,
):
    if kind not in PURCHASABILITY_EXPORT_KINDS:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "unknown_export_kind", "kind": kind},
        )
    filename = purchasability_export_filename(kind)
    media = "application/json" if filename.endswith(".json") else "text/csv; charset=utf-8"
    stream = stream_purchasability_export(
        db,
        kind,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        book_source=book_source,
    )

    def _iter():
        for chunk in stream:
            yield chunk

    return StreamingResponse(
        _iter(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/purchasability/export/{kind}")
def get_purchasability_export(
    kind: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    market_family: str | None = Query(default=None),
    book_source: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return _purchasability_export_response(
        kind,
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        book_source=book_source,
    )


# --- Indice di Acquistabilità Fase 2A (read-only statistical research) ---


@router.get("/purchasability/statistical-research")
def get_purchasability_statistical_research(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    market_family: str | None = Query(default=None),
    selection: str | None = Query(default=None),
    bootstrap_iterations: int = Query(default=200, ge=10, le=2000),
    seed: int = Query(default=42),
    db: Session = Depends(get_db),
):
    """Sincrono — solo Console/debug. Preferire POST .../jobs dal frontend."""
    payload = build_purchasability_statistical_research(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"X-Research-Execution-Mode": "synchronous-debug"},
    )


# --- Fase 2A.3 async jobs (process-local; persi su restart) ---


@router.post("/purchasability/statistical-research/jobs", status_code=202)
def post_purchasability_statistical_research_job(
    body: CecchinoPurchasabilityStatisticalJobBody,
):
    try:
        out = enqueue_purchasability_research_job(
            date_from=body.date_from,
            date_to=body.date_to,
            competition_id=body.competition_id,
            market_family=body.market_family,
            selection=body.selection,
            bootstrap_iterations=body.bootstrap_iterations,
            seed=body.seed,
            research_mode=body.research_mode or "phase2a_statistical",
        )
        return JSONResponse(status_code=202, content=out)
    except PurchasabilityResearchJobConflict as e:
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "error": "purchasability_research_job_already_running",
                "active_job_id": e.active_job_id,
                "active_filters": e.active_filters,
            },
        )


@router.get("/purchasability/statistical-research/jobs/active")
def get_purchasability_statistical_research_job_active():
    job = get_active_job()
    if job is None:
        return JSONResponse(content={"status": "ok", "job": None})
    return JSONResponse(content={"status": "ok", "job": job.to_status_dict()})


@router.get("/purchasability/statistical-research/jobs/{job_id}")
def get_purchasability_statistical_research_job(job_id: str):
    try:
        job = get_job(job_id)
    except PurchasabilityResearchJobNotFound:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": "research_job_not_found_or_expired",
            },
        )
    return JSONResponse(content=job.to_status_dict())


def _stream_job_json_file(path: str, download_name: str):
    def _iter():
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'inline; filename="{download_name}"',
            "X-Research-Execution-Mode": "async-job",
        },
    )


@router.get("/purchasability/statistical-research/jobs/{job_id}/summary")
def get_purchasability_statistical_research_job_summary(job_id: str):
    try:
        job = get_job(job_id)
    except PurchasabilityResearchJobNotFound:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": "research_job_not_found_or_expired",
            },
        )
    if job.status != "completed" or not job.summary_file_path:
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "error": "research_job_result_not_ready",
                "job_status": job.status,
            },
        )
    from pathlib import Path

    if not Path(job.summary_file_path).is_file():
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": "research_job_not_found_or_expired",
            },
        )
    return FileResponse(
        job.summary_file_path,
        media_type="application/json; charset=utf-8",
        filename=f"{job_id}.summary.json",
        headers={"X-Research-Execution-Mode": "async-job"},
    )


@router.get("/purchasability/statistical-research/jobs/{job_id}/result")
def get_purchasability_statistical_research_job_result(job_id: str):
    try:
        job = get_job(job_id)
    except PurchasabilityResearchJobNotFound:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": "research_job_not_found_or_expired",
            },
        )
    if job.status != "completed" or not job.result_file_path:
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "error": "research_job_result_not_ready",
                "job_status": job.status,
            },
        )
    from pathlib import Path

    if not Path(job.result_file_path).is_file():
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": "research_job_not_found_or_expired",
            },
        )
    return _stream_job_json_file(job.result_file_path, f"{job_id}.result.json")


@router.get("/purchasability/statistical-research/markets")
def get_purchasability_statistical_markets(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    bootstrap_iterations: int = Query(default=50, ge=10, le=2000),
    seed: int = Query(default=42),
    db: Session = Depends(get_db),
):
    payload = build_statistical_markets_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability/statistical-research/features")
def get_purchasability_statistical_features(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    bootstrap_iterations: int = Query(default=50, ge=10, le=2000),
    seed: int = Query(default=42),
    db: Session = Depends(get_db),
):
    payload = build_statistical_features_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/purchasability/statistical-research/candidates")
def get_purchasability_statistical_candidates(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    bootstrap_iterations: int = Query(default=50, ge=10, le=2000),
    seed: int = Query(default=42),
    db: Session = Depends(get_db),
):
    payload = build_statistical_candidates_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return JSONResponse(content=jsonable_encoder(payload))


def _purchasability_stat_export_response(
    kind: str,
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
    market_family: str | None,
    selection: str | None,
    bootstrap_iterations: int,
    seed: int,
):
    if kind not in PURCHASABILITY_STAT_EXPORT_KINDS:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "unknown_export_kind", "kind": kind},
        )
    filename = statistical_export_filename(kind)
    media = "application/json" if filename.endswith(".json") else "text/csv; charset=utf-8"
    stream = stream_statistical_export(
        db,
        kind,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )

    def _iter():
        for chunk in stream:
            yield chunk

    return StreamingResponse(
        _iter(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/purchasability/statistical-research/export/{kind}")
def get_purchasability_statistical_export(
    kind: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    market_family: str | None = Query(default=None),
    selection: str | None = Query(default=None),
    bootstrap_iterations: int = Query(default=200, ge=10, le=2000),
    seed: int = Query(default=42),
    db: Session = Depends(get_db),
):
    return _purchasability_stat_export_response(
        kind,
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )


# --- Fase 2A.4 residual reliability (sync debug + export; jobs via research_mode) ---


@router.get("/purchasability/residual-reliability")
def get_purchasability_residual_reliability(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    market_family: str | None = Query(default=None),
    selection: str | None = Query(default=None),
    bootstrap_iterations: int = Query(default=200, ge=10, le=2000),
    seed: int = Query(default=42),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_residual_reliability(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"X-Research-Execution-Mode": "synchronous-debug"},
    )


def _purchasability_residual_export_response(
    kind: str,
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
    market_family: str | None,
    selection: str | None,
    bootstrap_iterations: int,
    seed: int,
):
    if kind not in PURCHASABILITY_RESIDUAL_EXPORT_KINDS:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "unknown_export_kind", "kind": kind},
        )
    filename = residual_export_filename(kind)
    media = (
        "application/json; charset=utf-8"
        if kind in ("summary", "cohort", "fair-book-audit", "readiness", "economic")
        else "text/csv; charset=utf-8"
    )
    stream = stream_residual_export(
        db,
        kind,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )

    def _iter():
        for chunk in stream:
            if isinstance(chunk, str):
                yield chunk.encode("utf-8")
            else:
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/purchasability/residual-reliability/export/{kind}")
def get_purchasability_residual_export(
    kind: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    market_family: str | None = Query(default=None),
    selection: str | None = Query(default=None),
    bootstrap_iterations: int = Query(default=200, ge=10, le=2000),
    seed: int = Query(default=42),
    db: Session = Depends(get_db),
):
    return _purchasability_residual_export_response(
        kind,
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )


@router.post("/pattern-discovery/runs")
def post_pattern_discovery_run(
    body: CecchinoPatternDiscoveryStartBody,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Avvia (in background) la scoperta Pattern walk-forward per un market_key.

    Albero decisionale poco profondo per fold di training (finestra
    espandibile sulle stagioni indicate da run_ids), validato out-of-sample
    sulla stagione successiva. Nessuna formula esistente viene letta o
    modificata: produce esclusivamente righe candidate persistite.
    """
    from app.services.cecchino_data_lab.pattern_discovery_service import start_pattern_discovery

    try:
        out = start_pattern_discovery(
            db, market_key=body.market_key, run_ids=body.run_ids, competition=body.competition
        )
        return JSONResponse(status_code=202, content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/pattern-discovery/runs/{run_id}")
def get_pattern_discovery_run_status(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.services.cecchino_data_lab.pattern_discovery_service import get_pattern_discovery_run

    try:
        out = get_pattern_discovery_run(db, run_id)
        return JSONResponse(content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/pattern-discovery/runs/{run_id}/patterns")
def get_pattern_discovery_run_patterns(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.services.cecchino_data_lab.pattern_discovery_service import list_discovered_patterns

    try:
        out = list_discovered_patterns(db, run_id)
        return JSONResponse(content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/pattern-discovery/runs/{run_id}/cancel")
def post_pattern_discovery_run_cancel(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.services.cecchino_data_lab.pattern_discovery_service import cancel_pattern_discovery

    try:
        out = cancel_pattern_discovery(db, run_id)
        return JSONResponse(content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/pattern-grid/leaderboard")
def get_pattern_grid_leaderboard_route(db: Session = Depends(get_db)) -> JSONResponse:
    """Vista consolidata: ultimo run completato per ciascun mercato (scope
    globale), con tutti i candidati a profitto totale positivo sui 4 anni —
    mercati mischiati in un'unica lista, non filtrata per singolo segno."""
    from app.services.cecchino_data_lab.pattern_grid_service import get_leaderboard

    out = get_leaderboard(db)
    return JSONResponse(content=jsonable_encoder(out))


@router.post("/pattern-grid/runs")
def post_pattern_grid_run(
    body: CecchinoPatternGridStartBody,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Avvia (in background) il motore Pattern Grid: ricerca esaustiva di
    combinazioni di filtri, eseguita in sequenza sui pacchetti stagionali
    indicati da run_ids (stadio 1 → valida+scopre → stadio 2 → ... ), con
    lignaggio completo per candidato. Nessuna formula esistente viene letta
    o modificata.
    """
    from app.services.cecchino_data_lab.pattern_grid_service import start_pattern_grid

    try:
        out = start_pattern_grid(
            db, market_key=body.market_key, run_ids=body.run_ids, competition=body.competition
        )
        return JSONResponse(status_code=202, content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/pattern-grid/runs/{run_id}")
def get_pattern_grid_run_status(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.services.cecchino_data_lab.pattern_grid_service import get_pattern_grid_run

    try:
        out = get_pattern_grid_run(db, run_id)
        return JSONResponse(content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/pattern-grid/runs/{run_id}/candidates")
def get_pattern_grid_run_candidates(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.services.cecchino_data_lab.pattern_grid_service import list_pattern_grid_candidates

    try:
        out = list_pattern_grid_candidates(db, run_id)
        return JSONResponse(content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/pattern-grid/runs/{run_id}/cancel")
def post_pattern_grid_run_cancel(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.services.cecchino_data_lab.pattern_grid_service import cancel_pattern_grid

    try:
        out = cancel_pattern_grid(db, run_id)
        return JSONResponse(content=jsonable_encoder(out))
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
