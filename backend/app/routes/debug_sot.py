import logging

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.core.database import get_db
from app.services.debug_sot_model_comparison import (
    build_model_comparison_for_fixture,
    build_model_comparison_for_upcoming,
)
from app.services.predictions_v10.v10_features_debug import build_fixture_features_debug
from app.services.availability.availability_debug import build_fixture_availability_debug
from app.services.lineups.lineup_debug import build_fixture_lineups_debug
from app.services.player_data.player_profiles_debug import (
    PROFILE_LIMIT_MAX,
    build_fixture_player_profiles_debug,
)


def _resolve_player_profiles_limit(limit: str) -> int:
    """limit numerico 1..100 oppure 'all' (max profili per squadra)."""
    raw = (limit or "15").strip().lower()
    if raw == "all":
        return PROFILE_LIMIT_MAX
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(f"limit non valido: {limit}") from exc
    if n < 1 or n > PROFILE_LIMIT_MAX:
        raise ValueError(f"limit deve essere tra 1 e {PROFILE_LIMIT_MAX}, oppure 'all'")
    return n
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
                    "model_version": model_version,
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
                    "message": "Errore durante la costruzione della spiegazione.",
                    "failed_step": "build_explanation",
                    "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
                    "fixture_id": int(fixture_id),
                    "model_version": model_version,
                }
            ),
        )

    if isinstance(payload, dict) and payload.get("status") == "error":
        return JSONResponse(status_code=422, content=jsonable_encoder(payload))

    if isinstance(payload, dict) and payload.get("status") == "missing":
        return JSONResponse(status_code=404, content=jsonable_encoder(payload))

    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/fixture/{fixture_id}/player-profiles", response_model=None)
def debug_sot_fixture_player_profiles(
    fixture_id: int,
    db: Session = Depends(get_db),
    season: int | None = Query(default=None),
    limit: str = Query(
        default="15",
        description="Numero profili per squadra (1-100) oppure 'all' (= max 100).",
    ),
    sort: str = Query(default="shooting_impact_score_desc"),
):
    """Read-only: profili Player DB per casa/trasferta (nessuna API esterna)."""
    try:
        resolved_limit = _resolve_player_profiles_limit(limit)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": str(exc),
                    "fixture_id": int(fixture_id),
                },
            ),
        )
    try:
        payload = build_fixture_player_profiles_debug(
            db,
            int(fixture_id),
            season_year=season,
            limit=resolved_limit,
            sort=sort,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "GET debug fixture player-profiles: DB error (%s)",
            exc.__class__.__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore database durante la lettura dei profili giocatori.",
                    "failed_step": "database_operation",
                    "details": f"{exc.__class__.__name__}",
                    "fixture_id": int(fixture_id),
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug fixture player-profiles: errore inatteso")
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante la lettura dei profili giocatori.",
                    "failed_step": "build_player_profiles",
                    "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
                    "fixture_id": int(fixture_id),
                },
            ),
        )

    if isinstance(payload, dict) and payload.get("status") == "error":
        msg = str(payload.get("message") or "")
        code = 404 if "non trovata" in msg.lower() or "not found" in msg.lower() else 400
        return JSONResponse(status_code=code, content=jsonable_encoder(payload))

    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/fixture/{fixture_id}/lineups", response_model=None)
def debug_sot_fixture_lineups(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Read-only: formazioni ufficiali da DB (nessuna API esterna)."""
    try:
        payload = build_fixture_lineups_debug(db, int(fixture_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "GET debug fixture lineups: DB error (%s)",
            exc.__class__.__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore database durante la lettura delle formazioni.",
                    "failed_step": "database_operation",
                    "details": f"{exc.__class__.__name__}",
                    "fixture_id": int(fixture_id),
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug fixture lineups: errore inatteso")
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante la lettura delle formazioni.",
                    "failed_step": "build_lineups",
                    "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
                    "fixture_id": int(fixture_id),
                },
            ),
        )

    if isinstance(payload, dict) and payload.get("status") == "error":
        msg = str(payload.get("message") or "")
        code = 404 if "non trovata" in msg.lower() else 400
        return JSONResponse(status_code=code, content=jsonable_encoder(payload))
    if isinstance(payload, dict) and payload.get("status") == "not_available_yet":
        return JSONResponse(status_code=200, content=jsonable_encoder(payload))

    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/fixture/{fixture_id}/availability", response_model=None)
def debug_sot_fixture_availability(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Read-only: indisponibili da player_availability (nessuna API esterna)."""
    try:
        payload = build_fixture_availability_debug(db, int(fixture_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "GET debug fixture availability: DB error (%s)",
            exc.__class__.__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore database durante la lettura delle indisponibilità.",
                    "failed_step": "database_operation",
                    "details": f"{exc.__class__.__name__}",
                    "fixture_id": int(fixture_id),
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug fixture availability: errore inatteso")
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante la lettura delle indisponibilità.",
                    "failed_step": "build_availability",
                    "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
                    "fixture_id": int(fixture_id),
                },
            ),
        )

    if isinstance(payload, dict) and payload.get("status") == "error":
        msg = str(payload.get("message") or "")
        code = 404 if "non trovata" in msg.lower() else 400
        return JSONResponse(status_code=code, content=jsonable_encoder(payload))
    if isinstance(payload, dict) and payload.get("status") == "not_available_yet":
        return JSONResponse(status_code=200, content=jsonable_encoder(payload))

    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/fixture/{fixture_id}/features", response_model=None)
def debug_sot_fixture_features(
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str | None = Query(default="baseline_v1_0_sot"),
):
    """Risoluzione read-only feature per casa/trasferta (nessuna persistenza)."""
    mv = model_version or "baseline_v1_0_sot"
    try:
        if mv == BASELINE_SOT_MODEL_VERSION_V11_SOT:
            from app.services.predictions_v11.v11_features_debug import build_fixture_features_debug_v11

            payload = build_fixture_features_debug_v11(db, int(fixture_id), model_version=mv)
        else:
            payload = build_fixture_features_debug(db, int(fixture_id), model_version=mv)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET debug fixture features: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore database durante la lettura delle feature.",
                    "failed_step": "database_operation",
                    "details": f"{exc.__class__.__name__}",
                    "fixture_id": int(fixture_id),
                    "model_version": model_version,
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET debug fixture features")
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante la risoluzione delle feature.",
                    "failed_step": "build_features",
                    "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
                    "fixture_id": int(fixture_id),
                    "model_version": model_version,
                }
            ),
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

