"""Route read-only per cataloghi dati (consultazione / pianificazione)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.api_football_direct_catalog_io import load_direct_catalog_cache

router = APIRouter(prefix="/data-catalog", tags=["data-catalog"])

DIRECT_VERSION = "api_football_direct_catalog_v0_1"


def _empty_direct_payload() -> dict[str, Any]:
    return {
        "version": DIRECT_VERSION,
        "season": get_settings().default_season,
        "provider": "API-Football / API-Sports",
        "last_scan_at": None,
        "message": "Nessuno scan eseguito. Avvia scan API per costruire il catalogo diretto.",
        "summary": {
            "endpoints_scanned": 0,
            "endpoints_errors": 0,
            "direct_fields_found": 0,
            "fields_used_by_v04": 0,
            "fields_saved_in_db": 0,
            "fields_raw_json_only": 0,
        },
        "areas": [],
    }


@router.get("/api-football/direct")
def get_api_football_direct_catalog() -> dict[str, Any]:
    """
    Ultimo catalogo campi diretti da scan API-Football (cache file).
    Non include la diagnostica dettagliata degli endpoint (solo nel POST scan).
    """
    data = load_direct_catalog_cache()
    if not data:
        return _empty_direct_payload()
    out = {k: v for k, v in data.items() if k != "diagnostics"}
    return out
