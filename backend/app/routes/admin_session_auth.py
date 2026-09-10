"""Login/logout della sessione admin (RUN V2).

Questi tre endpoint sono volutamente non protetti: sono il punto di ingresso.
La password viaggia una volta sola nel body e non viene mai restituita ne'
scritta nei log; quello che torna al browser e' solo un cookie HttpOnly.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.admin_session import (
    AdminAuthNotConfigured,
    clear_session_cookie,
    client_key,
    create_session_token,
    current_session,
    lockout_remaining,
    register_failed_attempt,
    reset_attempts,
    set_session_cookie,
    verify_password,
)
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
logger = logging.getLogger(__name__)

_NOT_CONFIGURED = {
    "status": "error",
    "error": "admin_auth_not_configured",
    "message": (
        "Autenticazione admin non configurata sul server "
        "(ADMIN_PASSWORD e ADMIN_SESSION_SECRET)."
    ),
}


@router.get("/session")
def read_session(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Stato della sessione, per decidere se mostrare il form di login."""
    session = current_session(request, settings)
    if session is None:
        return JSONResponse(content={"authenticated": False, "expires_in": 0})
    return JSONResponse(
        content={"authenticated": True, "expires_in": session.expires_in}
    )


@router.post("/login")
def login(
    request: Request,
    body: dict[str, Any] | None = None,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    key = client_key(request)
    remaining = lockout_remaining(key)
    if remaining > 0:
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "error": "too_many_attempts",
                "message": f"Troppi tentativi falliti. Riprovare fra {remaining} secondi.",
            },
        )

    password = str((body or {}).get("password") or "")
    try:
        ok = verify_password(password, settings)
    except AdminAuthNotConfigured:
        logger.error("Login admin richiesto ma ADMIN_PASSWORD/ADMIN_SESSION_SECRET mancanti")
        return JSONResponse(status_code=503, content=_NOT_CONFIGURED)

    if not ok:
        register_failed_attempt(key)
        logger.warning("Login admin fallito da %s", key)
        return JSONResponse(
            status_code=401,
            content={
                "status": "error",
                "error": "invalid_credentials",
                "message": "Password non valida.",
            },
        )

    reset_attempts(key)
    token, expires_at = create_session_token(settings)
    response = JSONResponse(content={"authenticated": True, "expires_at": expires_at})
    set_session_cookie(response, token, settings)
    return response


@router.post("/logout")
def logout(settings: Settings = Depends(get_settings)) -> JSONResponse:
    response = JSONResponse(content={"authenticated": False})
    clear_session_cookie(response, settings)
    return response
