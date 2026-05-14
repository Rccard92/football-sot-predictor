"""Route read-only per cataloghi dati (consultazione / pianificazione)."""

from __future__ import annotations

from fastapi import APIRouter

from app.data.api_football_catalog import build_api_football_catalog_payload

router = APIRouter(prefix="/data-catalog", tags=["data-catalog"])


@router.get("/api-football")
def get_api_football_catalog() -> dict:
    """
    Catalogo statico parametri API-Football con stato progetto e riferimenti manifest v0.4.
    Nessuna query database.
    """
    return build_api_football_catalog_payload()
