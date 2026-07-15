import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.routes import api_router

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Serie A SOT Predictor API",
    version="0.1.0",
    description="API per analisi statistiche e previsioni tiri in porta (MVP).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(api_router)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_unhandled_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Log degli errori SQLAlchemy non gestiti a livello di route (senza URL/credenziali)."""
    logger.error(
        "SQLAlchemy non gestito su %s: %s",
        request.url.path,
        exc.__class__.__name__,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "detail": "Errore database interno.",
            "message": "Errore database interno.",
            "failed_step": "database_operation",
        },
    )


@app.exception_handler(Exception)
async def global_unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: risposta JSON (con header CORS dal middleware) invece di crash senza body."""
    logger.exception("Eccezione non gestita su %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "detail": "Errore interno del server.",
            "message": "Errore interno del server.",
            "failed_step": "unexpected_error",
            "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
        },
    )
