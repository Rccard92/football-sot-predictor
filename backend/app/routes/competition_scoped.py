from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.core.database import get_db
from app.services.competition_service import CompetitionService
from app.services.next_round_model_comparison_service import (
    build_next_round_model_comparison_for_competition,
)
from app.services.next_round_quick_report_service import (
    build_next_round_quick_report_for_competition,
    build_upcoming_fixture_detail_for_competition,
)
from app.services.prediction_readiness import (
    build_competition_audit_fixtures_list,
    build_competition_fixture_explanation,
    build_model_status_for_competition,
    _safe_details,
)
from app.services.tracked_monitoring_dashboard_service import list_tracked_dashboard_for_competition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/competitions", tags=["competitions-scoped"])


@router.get("/{competition_id}/model-status")
def competition_model_status(
    competition_id: int,
    model_version: str | None = Query(None),
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    payload, code = build_model_status_for_competition(
        db,
        comp,
        selected_model_version=model_version,
    )
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))


@router.get("/{competition_id}/next-round/model-comparison")
def competition_next_round_model_comparison(
    competition_id: int,
    base_model: str = Query(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT),
    compare_model: str = Query(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS),
    limit: int = Query(20, ge=1, le=100),
    only_next_round: bool = Query(True),
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    payload, code = build_next_round_model_comparison_for_competition(
        db,
        comp,
        base_model=base_model,
        compare_model=compare_model,
        limit=limit,
        only_next_round=only_next_round,
    )
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))


@router.get("/{competition_id}/next-round/quick-report")
def competition_next_round_quick_report(
    competition_id: int,
    limit: int = Query(20, ge=1, le=100),
    only_next_round: bool = Query(True),
    model_version: str | None = Query(None),
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    payload = build_next_round_quick_report_for_competition(
        db,
        comp,
        limit=limit,
        only_next_round=only_next_round,
        model_version=model_version,
    )
    return jsonable_encoder(payload)


@router.get("/{competition_id}/betting-picks/tracked")
def competition_tracked_betting_picks(
    competition_id: int,
    db: Session = Depends(get_db),
    model_version: str | None = Query(None),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    return jsonable_encoder(
        list_tracked_dashboard_for_competition(db, comp, model_version=model_version)
    )


@router.get("/{competition_id}/predictions/sot/upcoming-fixture/{fixture_id}/detail")
def competition_upcoming_fixture_detail(
    competition_id: int,
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str | None = Query(None),
):
    """Dettaglio/audit singola fixture upcoming scoped per competition."""
    try:
        comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "competition_not_found",
                    "message": str(exc.detail),
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                    "step": "load_competition",
                }
            ),
        )
    try:
        payload, code = build_upcoming_fixture_detail_for_competition(
            db,
            comp,
            int(fixture_id),
            model_version=model_version,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "competition fixture detail: DB error competition=%s fixture=%s",
            competition_id,
            fixture_id,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "database_error",
                    "message": "Database error",
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                    "step": "build_payload",
                    "details": _safe_details(exc),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "competition fixture detail: errore inatteso competition=%s fixture=%s",
            competition_id,
            fixture_id,
        )
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "unexpected_error",
                    "message": "Errore inatteso durante il caricamento del dettaglio.",
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                    "step": "build_payload",
                    "details": _safe_details(exc),
                }
            ),
        )
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))


@router.get("/{competition_id}/predictions/sot/fixtures")
def competition_audit_fixtures_list(
    competition_id: int,
    db: Session = Depends(get_db),
    scope: str = Query("next_round"),
    model_version: str | None = Query(None),
    limit: int = Query(40, ge=1, le=200),
):
    """Lista fixture per dropdown audit/spiegazione, scoped per competition."""
    try:
        comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "competition_not_found",
                    "message": str(exc.detail),
                    "competition_id": int(competition_id),
                    "step": "load_competition",
                }
            ),
        )
    payload, code = build_competition_audit_fixtures_list(
        db,
        comp,
        scope=scope,
        model_version=model_version,
        limit=limit,
    )
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))


@router.get("/{competition_id}/predictions/sot/fixture/{fixture_id}/explanation")
def competition_fixture_explanation(
    competition_id: int,
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str | None = Query(None),
):
    """Spiegazione audit fixture scoped per competition."""
    try:
        comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "competition_not_found",
                    "message": str(exc.detail),
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                    "step": "load_competition",
                }
            ),
        )
    payload, code = build_competition_fixture_explanation(
        db,
        comp,
        int(fixture_id),
        model_version=model_version,
    )
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))


@router.get("/{competition_id}/fixtures/{fixture_id}/lineup-player-mapping-debug")
def competition_lineup_player_mapping_debug(
    competition_id: int,
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Debug mapping giocatori SportAPI ↔ player_season_profiles per singola fixture."""
    from app.services.prediction_readiness import _validate_fixture_for_competition
    from app.services.sportapi.lineup_player_profile_lookup import build_lineup_player_mapping_debug

    try:
        comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "competition_not_found",
                    "message": str(exc.detail),
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                }
            ),
        )

    fx, err, code = _validate_fixture_for_competition(db, comp, int(fixture_id))
    if err is not None:
        return JSONResponse(status_code=code or 404, content=jsonable_encoder(err))

    payload = build_lineup_player_mapping_debug(db, fx)
    payload["status"] = "success"
    return jsonable_encoder(payload)
