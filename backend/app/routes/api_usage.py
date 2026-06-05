"""Admin API usage tracking."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api_usage import ApiUsageSummaryResponse
from app.services.api_usage_service import get_api_usage_summary

router = APIRouter(prefix="/admin/api-usage", tags=["admin-api-usage"])


@router.get("/summary", response_model=ApiUsageSummaryResponse)
def api_usage_summary(
    date: date = Query(..., description="Data YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> dict:
    return get_api_usage_summary(db, usage_date=date)
