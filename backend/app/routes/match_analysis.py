import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.constants import FINISHED_STATUSES, fixture_eligible_for_upcoming_sot
from app.models import Fixture, League, Season, Team
from app.schemas.match_analysis import (
    AuditErrorResponse,
    AuditFixturesListResponse,
    MatchVariablesAuditResponse,
)
from app.services.match_variable_audit_service import MatchVariableAuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/match-analysis", tags=["match-analysis"])


@router.get("/fixture/{fixture_id}/variables", response_model=None)
def get_match_variables_audit(
    fixture_id: int,
    db: Session = Depends(get_db),
    market: str = Query(default="shots_on_target"),
    mode: str = Query(default="pre_match"),
):
    if market != "shots_on_target":
        payload = AuditErrorResponse(
            status="error",
            message="Mercato non supportato in questa versione.",
            failed_step="validate_market",
            details=f"market={market}",
        )
        return JSONResponse(status_code=400, content=jsonable_encoder(payload))
    if mode not in ("pre_match", "post_match"):
        payload = AuditErrorResponse(
            status="error",
            message="Mode non supportato. Usare pre_match o post_match.",
            failed_step="validate_mode",
            details=f"mode={mode}",
        )
        return JSONResponse(status_code=400, content=jsonable_encoder(payload))

    try:
        svc = MatchVariableAuditService()
        data: MatchVariablesAuditResponse = svc.build_fixture_variables_shots_on_target(
            db,
            fixture_id,
            mode=mode,  # type: ignore[arg-type]
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET match-analysis variables: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except ValueError as exc:
        payload = AuditErrorResponse(
            status="error",
            message=str(exc),
            failed_step="load_fixture",
        )
        return JSONResponse(status_code=404, content=jsonable_encoder(payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET match-analysis variables: errore inatteso")
        payload = AuditErrorResponse(
            status="error",
            message="Errore inatteso durante audit variabili.",
            failed_step="unexpected_error",
            details=str(exc),
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(payload))
    return jsonable_encoder(data)


@router.get("/fixtures", response_model=AuditFixturesListResponse)
def list_audit_fixtures(
    db: Session = Depends(get_db),
    season: int | None = Query(default=None),
    scope: str = Query(default="upcoming"),
    limit: int = Query(default=50, ge=1, le=200),
) -> AuditFixturesListResponse:
    if scope not in ("upcoming", "completed", "all"):
        raise HTTPException(status_code=400, detail="scope deve essere upcoming|completed|all")

    try:
        settings = get_settings()
        target_season = int(season or settings.default_season)
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError("Lega di default non trovata")
        season_row = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == target_season))
        if season_row is None:
            raise ValueError(f"Stagione non trovata per year={target_season}")

        base_q = (
            select(Fixture)
            .where(Fixture.season_id == season_row.id)
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
        )

        rows = db.scalars(base_q).all()

        if scope == "upcoming":
            rows = [f for f in rows if fixture_eligible_for_upcoming_sot(f.status, f.kickoff_at)]
        elif scope == "completed":
            rows = [f for f in rows if (f.status or "").upper() in FINISHED_STATUSES]
        else:
            rows = list(rows)

        rows = rows[: max(1, min(limit, 200))]

        fixtures_payload = []
        for f in rows:
            home = db.get(Team, f.home_team_id)
            away = db.get(Team, f.away_team_id)
            fixtures_payload.append(
                {
                    "fixture_id": int(f.id),
                    "api_fixture_id": int(f.api_fixture_id),
                    "round": f.round,
                    "kickoff_at": f.kickoff_at,
                    "status_short": f.status,
                    "home_team": {"id": int(f.home_team_id), "name": home.name if home else "", "logo_url": home.logo_url if home else None},
                    "away_team": {"id": int(f.away_team_id), "name": away.name if away else "", "logo_url": away.logo_url if away else None},
                }
            )
        return AuditFixturesListResponse(season=target_season, scope=scope, fixtures=fixtures_payload)  # type: ignore[arg-type]
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET match-analysis fixtures: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except ValueError as exc:
        payload = AuditErrorResponse(status="error", message=str(exc), failed_step="load_season")
        return JSONResponse(status_code=404, content=jsonable_encoder(payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET match-analysis fixtures: errore inatteso")
        payload = AuditErrorResponse(
            status="error",
            message="Errore durante il caricamento delle fixture per audit.",
            failed_step="unexpected_error",
            details=f"{exc.__class__.__name__}: {exc!s}"[:800],
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(payload))

