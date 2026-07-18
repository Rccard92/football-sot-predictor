"""Route admin ricerca Cecchino — audit Credibilità X / Intensità Goal v5 (offline)."""

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
from app.schemas.cecchino_goal_intensity_v5_research import (
    CecchinoGoalIntensityV5AuditBody,
    CecchinoGoalIntensityV5CandidateIndicesBody,
    CecchinoGoalIntensityV5DatasetBody,
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
from app.services.cecchino.cecchino_goal_intensity_v5_statistics import (
    build_goal_intensity_v5_statistics,
    statistics_export_filename,
    stream_goal_intensity_v5_statistics_export,
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
