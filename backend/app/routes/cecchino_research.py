"""Route admin ricerca Cecchino — audit Credibilità X (offline)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_draw_credibility_research import CecchinoDrawCredibilityAuditBody
from app.services.cecchino.cecchino_draw_credibility_research import (
    build_draw_credibility_coverage_audit,
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
