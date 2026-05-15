from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionLocal

router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    """Liveness minimale per probe container (nessun DB, nessun servizio modello)."""
    return {"status": "ok"}


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    api_football_configured = bool(settings.api_football_key.strip())
    api_football_base_url_configured = bool(settings.api_football_base_url.strip())

    database = "error"
    database_message: str | None = None
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            database = "connected"
        except Exception as exc:
            database_message = str(exc)
        finally:
            db.close()
    except Exception as exc:
        database_message = str(exc)

    status = "ok" if database == "connected" else "degraded"
    body: dict = {
        "status": status,
        "database": database,
        "api_football_configured": api_football_configured,
        "api_football_base_url_configured": api_football_base_url_configured,
        "environment": settings.app_env,
    }
    if database_message is not None:
        body["database_message"] = database_message
    return body
