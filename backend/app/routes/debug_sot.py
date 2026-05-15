import logging

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.debug_sot_model_comparison import (
    build_model_comparison_for_fixture,
    build_model_comparison_for_upcoming,
)
from app.services.predictions_v10.v10_features_debug import build_fixture_features_debug
from app.services.sot_fixture_explanation_service import build_fixture_sot_explanation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug/sot", tags=["debug"])


@router.get("/fixture/{fixture_id}/explanation", response_model=None)
def debug_sot_fixture_explanation(
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str | None = Query(default=None),
):
    """
    Read-only: spiegazione audit previsione SOT per fixture (dati già salvati, nessuna rigenerazione).
    """
    try:
        payload = build_fixture_sot_explanation(db, int(fixture_id), model_version=model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET debug fixture explanation: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore database durante la lettura della spiegazione.",
                    "failed_step": "database_operation",
                    "details": f"{exc.__class__.__name__}",
                    "fixture_id": int(fixture_id),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug fixture explanation: errore inatteso")
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante l'assemblaggio della spiegazione (dettaglio in note).",
                    "failed_step": "unexpected_error",
                    "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
                    "fixture_id": int(fixture_id),
                }
            ),
        )

    if isinstance(payload, dict) and payload.get("status") == "missing":
        return JSONResponse(status_code=404, content=jsonable_encoder(payload))

    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/fixture/{fixture_id}/features", response_model=None)
def debug_sot_fixture_features(
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str | None = Query(default="baseline_v1_0_sot"),
):
    """Risoluzione read-only feature registry per casa/trasferta (nessuna persistenza)."""
    try:
        payload = build_fixture_features_debug(db, int(fixture_id), model_version=model_version or "baseline_v1_0_sot")
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET debug fixture features: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return JSONResponse(status_code=503, content=jsonable_encoder({"status": "error", "message": "Database error"}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug fixture features")
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"status": "error", "message": str(exc)[:500], "fixture_id": int(fixture_id)}),
        )
    if payload.get("status") == "missing":
        return JSONResponse(status_code=404, content=jsonable_encoder(payload))
    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/fixture/{fixture_id}/model-comparison", response_model=None)
def debug_sot_fixture_model_comparison(
    fixture_id: int,
    db: Session = Depends(get_db),
    season: int | None = Query(default=None),
    include_raw: bool = Query(default=False),
):
    try:
        payload = build_model_comparison_for_fixture(db, int(fixture_id), season=season, include_raw=bool(include_raw))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET debug fixture model-comparison: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il confronto modelli per la fixture.",
                    "failed_step": "database_operation",
                    "details": f"{exc.__class__.__name__}",
                    "fixture_id": int(fixture_id),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug fixture model-comparison: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il confronto modelli per la fixture.",
                    "failed_step": "unexpected_error",
                    "details": f"{exc.__class__.__name__}",
                    "fixture_id": int(fixture_id),
                }
            ),
        )

    if isinstance(payload, dict) and payload.get("status") == "error":
        # 404/409 a seconda dello step: qui usiamo 404 per fixture mancante, 409 per mismatch
        step = str(payload.get("failed_step") or "")
        code = 404 if step in ("load_fixture",) else 409 if step in ("season_mismatch",) else 400
        return JSONResponse(status_code=code, content=jsonable_encoder(payload))

    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/serie-a/{season}/model-comparison/upcoming", response_model=None)
def debug_sot_upcoming_model_comparison(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=500),
):
    try:
        payload = build_model_comparison_for_upcoming(db, int(season), limit=int(limit))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET debug upcoming model-comparison: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il confronto modelli per la prossima giornata.",
                    "failed_step": "database_operation",
                    "details": f"{exc.__class__.__name__}",
                    "season": int(season),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug upcoming model-comparison: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il confronto modelli per la prossima giornata.",
                    "failed_step": "unexpected_error",
                    "details": f"{exc.__class__.__name__}",
                    "season": int(season),
                }
            ),
        )

    if isinstance(payload, dict) and payload.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(payload))

    return JSONResponse(status_code=200, content=jsonable_encoder(payload))

