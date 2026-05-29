from __future__ import annotations

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.competition_service import CompetitionService


def require_competition_id(
    competition_id: int | None = Query(None, description="ID campionato"),
    db: Session = Depends(get_db),
):
    svc = CompetitionService()
    return svc.resolve_or_raise(db, competition_id=competition_id, allow_default=True)


def require_competition_id_strict(
    competition_id: int,
    db: Session = Depends(get_db),
):
    if competition_id is None:
        raise HTTPException(status_code=400, detail="competition_id richiesto")
    svc = CompetitionService()
    return svc.get_by_id_or_raise(db, competition_id)
