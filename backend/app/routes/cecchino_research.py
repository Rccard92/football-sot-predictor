"""Route admin ricerca Cecchino — audit Credibilità X / Intensità Goal v5 (offline)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
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
from app.schemas.cecchino_goal_intensity_v5_research import (
    CecchinoGoalIntensityV5AuditBody,
    CecchinoGoalIntensityV5CandidateIndicesBody,
    CecchinoGoalIntensityV5DatasetBody,
    CecchinoGoalIntensityV5PreviewFreezeBody,
    CecchinoGoalIntensityV5PreviewRefreshBody,
    CecchinoGoalIntensityV5StatisticsBody,
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
from app.services.cecchino.cecchino_goal_intensity_v5_audit import build_goal_intensity_v5_audit
from app.services.cecchino.cecchino_goal_intensity_v5_availability import (
    build_goal_intensity_v5_availability,
)
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import (
    build_goal_intensity_v5_dataset,
    dataset_export_filename,
    stream_goal_intensity_v5_dataset_csv,
    stream_goal_intensity_v5_dataset_summary_json,
)
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    build_goal_intensity_v5_candidate_indices,
    candidate_indices_export_filename,
    stream_goal_intensity_v5_candidate_indices_export,
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
from app.services.cecchino.cecchino_goal_intensity_v5_statistics import (
    build_goal_intensity_v5_statistics,
    statistics_export_filename,
    stream_goal_intensity_v5_statistics_export,
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


@router.get("/goal-intensity-v5/availability")
def get_goal_intensity_v5_availability(
    db: Session = Depends(get_db),
):
    payload = build_goal_intensity_v5_availability(db)
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/goal-intensity-v5/audit")
def post_goal_intensity_v5_audit(
    body: CecchinoGoalIntensityV5AuditBody,
    db: Session = Depends(get_db),
):
    payload = build_goal_intensity_v5_audit(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.post("/goal-intensity-v5/dataset")
def post_goal_intensity_v5_dataset(
    body: CecchinoGoalIntensityV5DatasetBody,
    db: Session = Depends(get_db),
):
    payload = build_goal_intensity_v5_dataset(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


def _goal_intensity_dataset_csv_export(kind: str, body: CecchinoGoalIntensityV5DatasetBody, db):
    filename = dataset_export_filename(
        kind=kind,  # type: ignore[arg-type]
        date_from=body.date_from,
        date_to=body.date_to,
    )
    stream = stream_goal_intensity_v5_dataset_csv(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        kind=kind,  # type: ignore[arg-type]
    )
    return StreamingResponse(
        stream,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/goal-intensity-v5/dataset/export/all")
def post_goal_intensity_v5_dataset_export_all(
    body: CecchinoGoalIntensityV5DatasetBody,
    db: Session = Depends(get_db),
):
    return _goal_intensity_dataset_csv_export("all", body, db)


@router.post("/goal-intensity-v5/dataset/export/core-min5")
def post_goal_intensity_v5_dataset_export_core_min5(
    body: CecchinoGoalIntensityV5DatasetBody,
    db: Session = Depends(get_db),
):
    return _goal_intensity_dataset_csv_export("core_min5", body, db)


@router.post("/goal-intensity-v5/dataset/export/core-min10")
def post_goal_intensity_v5_dataset_export_core_min10(
    body: CecchinoGoalIntensityV5DatasetBody,
    db: Session = Depends(get_db),
):
    return _goal_intensity_dataset_csv_export("core_min10", body, db)


@router.post("/goal-intensity-v5/dataset/export/xg-paired")
def post_goal_intensity_v5_dataset_export_xg_paired(
    body: CecchinoGoalIntensityV5DatasetBody,
    db: Session = Depends(get_db),
):
    return _goal_intensity_dataset_csv_export("xg_paired", body, db)


@router.post("/goal-intensity-v5/dataset/export/ineligible-diagnostics")
def post_goal_intensity_v5_dataset_export_ineligible(
    body: CecchinoGoalIntensityV5DatasetBody,
    db: Session = Depends(get_db),
):
    return _goal_intensity_dataset_csv_export("ineligible_diagnostics", body, db)


@router.post("/goal-intensity-v5/dataset/export/summary")
def post_goal_intensity_v5_dataset_export_summary(
    body: CecchinoGoalIntensityV5DatasetBody,
    db: Session = Depends(get_db),
):
    filename = dataset_export_filename(
        kind="summary",
        date_from=body.date_from,
        date_to=body.date_to,
    )
    stream = stream_goal_intensity_v5_dataset_summary_json(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
    )
    return StreamingResponse(
        stream,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/goal-intensity-v5/statistics")
def post_goal_intensity_v5_statistics(
    body: CecchinoGoalIntensityV5StatisticsBody,
    db: Session = Depends(get_db),
):
    payload = build_goal_intensity_v5_statistics(
        db, date_from=body.date_from, date_to=body.date_to,
        competition_id=body.competition_id, minimum_history_sample=body.minimum_history_sample,
        bootstrap_iterations=body.bootstrap_iterations, random_seed=body.random_seed,
    )
    return JSONResponse(content=jsonable_encoder(payload))


def _goal_intensity_statistics_export(kind: str, body: CecchinoGoalIntensityV5StatisticsBody, db):
    filename = statistics_export_filename(
        kind=kind, date_from=body.date_from, date_to=body.date_to,  # type: ignore[arg-type]
    )
    stream = stream_goal_intensity_v5_statistics_export(
        db, kind=kind, date_from=body.date_from, date_to=body.date_to,  # type: ignore[arg-type]
        competition_id=body.competition_id, minimum_history_sample=body.minimum_history_sample,
        bootstrap_iterations=body.bootstrap_iterations, random_seed=body.random_seed,
    )
    media = "application/json; charset=utf-8" if kind == "summary" else "text/csv; charset=utf-8"
    return StreamingResponse(
        stream, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/goal-intensity-v5/statistics/export/summary")
def post_goal_intensity_v5_statistics_export_summary(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("summary", body, db)


@router.post("/goal-intensity-v5/statistics/export/feature-signal")
def post_goal_intensity_v5_statistics_export_feature_signal(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("feature_signal", body, db)


@router.post("/goal-intensity-v5/statistics/export/redundancy-matrix")
def post_goal_intensity_v5_statistics_export_redundancy_matrix(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("redundancy_matrix", body, db)


@router.post("/goal-intensity-v5/statistics/export/redundancy-clusters")
def post_goal_intensity_v5_statistics_export_redundancy_clusters(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("redundancy_clusters", body, db)


@router.post("/goal-intensity-v5/statistics/export/temporal-stability")
def post_goal_intensity_v5_statistics_export_temporal_stability(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("temporal_stability", body, db)


@router.post("/goal-intensity-v5/statistics/export/rolling-comparison")
def post_goal_intensity_v5_statistics_export_rolling_comparison(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("rolling_comparison", body, db)


@router.post("/goal-intensity-v5/statistics/export/stability-metrics")
def post_goal_intensity_v5_statistics_export_stability_metrics(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("stability_metrics", body, db)


@router.post("/goal-intensity-v5/statistics/export/xg-value")
def post_goal_intensity_v5_statistics_export_xg_value(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("xg_value", body, db)


@router.post("/goal-intensity-v5/statistics/export/feature-recommendations")
def post_goal_intensity_v5_statistics_export_feature_recommendations(body: CecchinoGoalIntensityV5StatisticsBody, db: Session = Depends(get_db)):
    return _goal_intensity_statistics_export("feature_recommendations", body, db)


@router.post("/goal-intensity-v5/candidate-indices")
def post_goal_intensity_v5_candidate_indices(
    body: CecchinoGoalIntensityV5CandidateIndicesBody,
    db: Session = Depends(get_db),
):
    payload = build_goal_intensity_v5_candidate_indices(
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        minimum_history_sample=body.minimum_history_sample,
        bootstrap_iterations=body.bootstrap_iterations,
        random_seed=body.random_seed,
    )
    return JSONResponse(content=jsonable_encoder(payload))


def _goal_intensity_candidate_indices_export(
    kind: str, body: CecchinoGoalIntensityV5CandidateIndicesBody, db
):
    filename = candidate_indices_export_filename(
        kind=kind,  # type: ignore[arg-type]
        date_from=body.date_from,
        date_to=body.date_to,
    )
    stream = stream_goal_intensity_v5_candidate_indices_export(
        db,
        kind=kind,  # type: ignore[arg-type]
        date_from=body.date_from,
        date_to=body.date_to,
        competition_id=body.competition_id,
        minimum_history_sample=body.minimum_history_sample,
        bootstrap_iterations=body.bootstrap_iterations,
        random_seed=body.random_seed,
    )
    media = (
        "application/json; charset=utf-8"
        if kind in ("summary", "candidate_definitions", "prospective_validation_protocol")
        else "text/csv; charset=utf-8"
    )
    return StreamingResponse(
        stream,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/goal-intensity-v5/candidate-indices/export/summary")
def post_goal_intensity_v5_candidate_indices_export_summary(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("summary", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/candidate-definitions")
def post_goal_intensity_v5_candidate_indices_export_definitions(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("candidate_definitions", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/candidate-scores")
def post_goal_intensity_v5_candidate_indices_export_scores(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("candidate_scores", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/pillar-metrics")
def post_goal_intensity_v5_candidate_indices_export_pillar_metrics(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("pillar_metrics", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/composite-metrics")
def post_goal_intensity_v5_candidate_indices_export_composite_metrics(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("composite_metrics", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/temporal-metrics")
def post_goal_intensity_v5_candidate_indices_export_temporal_metrics(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("temporal_metrics", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/decile-calibration")
def post_goal_intensity_v5_candidate_indices_export_decile_calibration(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("decile_calibration", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/ablation-analysis")
def post_goal_intensity_v5_candidate_indices_export_ablation(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("ablation_analysis", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/paired-candidate-comparison")
def post_goal_intensity_v5_candidate_indices_export_paired(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("paired_candidate_comparison", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/pillar-redundancy")
def post_goal_intensity_v5_candidate_indices_export_pillar_redundancy(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("pillar_redundancy", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/xg-optional-enrichment")
def post_goal_intensity_v5_candidate_indices_export_xg(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("xg_optional_enrichment", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/prospective-validation-protocol")
def post_goal_intensity_v5_candidate_indices_export_prospective(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("prospective_validation_protocol", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/calibrated-predictions")
def post_goal_intensity_v5_candidate_indices_export_calibrated_predictions(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("calibrated_predictions", body, db)


@router.post("/goal-intensity-v5/candidate-indices/export/temporal-fold-metrics")
def post_goal_intensity_v5_candidate_indices_export_temporal_fold_metrics(
    body: CecchinoGoalIntensityV5CandidateIndicesBody, db: Session = Depends(get_db)
):
    return _goal_intensity_candidate_indices_export("temporal_fold_metrics", body, db)


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
    return JSONResponse(content=jsonable_encoder(payload))


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
