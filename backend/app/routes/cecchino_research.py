"""Route admin ricerca Cecchino — audit e dataset Credibilità X (offline)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_draw_credibility_research import (
    CecchinoDrawCredibilityAuditBody,
    CecchinoDrawCredibilityDatasetBody,
    CecchinoDrawCredibilityDatasetExportBody,
    CecchinoDrawCredibilityModelComparisonBody,
    CecchinoDrawCredibilityStatisticsBody,
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
