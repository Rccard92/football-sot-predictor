from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.competition import CompetitionRead
from app.services.competition_service import CompetitionService

router = APIRouter(prefix="/competitions", tags=["competitions"])


@router.get("")
def list_competitions(db: Session = Depends(get_db)):
    svc = CompetitionService()
    rows = svc.list_active(db)
    return jsonable_encoder([CompetitionRead.model_validate(r).model_dump() for r in rows])


DEFAULT_COMPETITION_MISSING_MESSAGE = (
    "Nessuna competition configurata. Esegui backfill Serie A."
)


@router.get("/default")
def get_default_competition(db: Session = Depends(get_db)):
    svc = CompetitionService()
    row = svc.get_default(db)
    if row is None:
        return jsonable_encoder(
            {
                "competition": None,
                "message": DEFAULT_COMPETITION_MISSING_MESSAGE,
            }
        )
    return jsonable_encoder(
        {
            "competition": CompetitionRead.model_validate(row).model_dump(),
            "message": None,
        }
    )


@router.get("/{competition_id}")
def get_competition(competition_id: int, db: Session = Depends(get_db)):
    svc = CompetitionService()
    row = svc.get_by_id_or_raise(db, competition_id)
    return jsonable_encoder(CompetitionRead.model_validate(row).model_dump())
