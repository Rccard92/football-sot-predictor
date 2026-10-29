"""Accesso degli utenti (dal 29/10/2026): login con email, uscita, chi sono, cambio password.

Punto d'ingresso: questi indirizzi non richiedono la sessione (il controllo d'accesso li salta).
La password viaggia solo nel body e non viene mai scritta nei log.
Accesso di emergenza: l'email del proprietario (EMERGENCY_ADMIN_EMAIL) + password admin storica
(ADMIN_PASSWORD) = amministratore. Se esiste anche un account con quella email, vale prima la sua password.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import admin_session
from app.core.access_control import allowed_tab_keys
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.user_auth import (
    USER_SESSION_COOKIE,
    clear_user_session_cookie,
    client_ip,
    create_user_session,
    hash_password,
    login_lockout_remaining,
    normalize_email,
    password_problem,
    register_failed_login,
    reset_failed_logins,
    resolve_principal,
    resolve_user_session,
    revoke_user_sessions,
    set_user_session_cookie,
    user_agent,
    verify_password_hash,
)
from app.models.app_user import AppLoginEvent, AppUser

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

EMERGENCY_LOGIN_FALLBACK = "admin"  # solo finche' EMERGENCY_ADMIN_EMAIL non e' impostata


def _emergency_login(settings: Settings) -> str:
    return normalize_email(settings.emergency_admin_email) or EMERGENCY_LOGIN_FALLBACK


def _emergency_ok(password: str, settings: Settings) -> bool:
    try:
        return admin_session.verify_password(password, settings)
    except admin_session.AdminAuthNotConfigured:
        return False


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"status": "error", "error": code, "message": message})


def _me(principal, settings: Settings) -> dict[str, Any]:
    if principal is None:
        return {"enforced": bool(settings.auth_enforced), "authenticated": False}
    return {
        "enforced": bool(settings.auth_enforced),
        "authenticated": True,
        **principal.payload(),
        "allowed_tabs": allowed_tab_keys(principal),
    }


def _log_event(db: Session, request: Request, *, email: str, success: bool, reason: str, user: AppUser | None) -> None:
    db.add(
        AppLoginEvent(
            user_id=user.id if user else None,
            email=email[:255] or None,
            success=success,
            reason=reason,
            ip=client_ip(request),
            user_agent=user_agent(request),
            created_at=datetime.now(timezone.utc),
        )
    )


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Stato dell'accesso: serve al frontend per decidere tra pagina di login, cambio password e tool."""
    return _me(resolve_principal(request, db, settings), settings)


@router.post("/login")
def login(
    request: Request,
    body: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    email = normalize_email((body or {}).get("email"))
    password = str((body or {}).get("password") or "")
    ip = client_ip(request)
    keys = (f"ip:{ip}", f"email:{email}")
    remaining = login_lockout_remaining(*keys)
    if remaining > 0:
        return _error(429, "too_many_attempts", f"Troppi tentativi falliti. Riprova fra {remaining} secondi.")
    if not email or not password:
        return _error(400, "missing_credentials", "Inserisci email e password.")

    user = db.execute(select(AppUser).where(AppUser.email == email)).scalar_one_or_none()
    account_ok = user is not None and verify_password_hash(password, user.password_hash)
    if not account_ok and email == _emergency_login(settings) and _emergency_ok(password, settings):
        reset_failed_logins(*keys)
        _log_event(db, request, email=email, success=True, reason="emergenza", user=user)
        db.commit()
        token, _ = admin_session.create_session_token(settings)
        response = JSONResponse(content={"authenticated": True, "kind": "emergency_admin"})
        admin_session.set_session_cookie(response, token, settings)
        return response

    if not account_ok:
        register_failed_login(*keys)
        reason = "utente_sconosciuto" if user is None else "password_errata"
        _log_event(db, request, email=email, success=False, reason=reason, user=user)
        db.commit()
        return _error(401, "invalid_credentials", "Email o password non corrette.")
    if not user.is_active:
        _log_event(db, request, email=email, success=False, reason="disattivato", user=user)
        db.commit()
        return _error(403, "account_disabled", "Account disattivato. Contatta l'amministratore.")

    reset_failed_logins(*keys)
    token = create_user_session(db, user, ip=ip, agent=user_agent(request), settings=settings)
    user.last_login_at = datetime.now(timezone.utc)
    _log_event(db, request, email=email, success=True, reason="ok", user=user)
    db.commit()
    response = JSONResponse(content={"authenticated": True, "must_change_password": bool(user.must_change_password)})
    set_user_session_cookie(response, token, settings)
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> JSONResponse:
    token = request.cookies.get(USER_SESSION_COOKIE) or ""
    found = resolve_user_session(db, token) if token else None
    if found is not None:
        _, session = found
        session.revoked_at = datetime.now(timezone.utc)
        session.revoke_reason = "logout"
        db.commit()
    response = JSONResponse(content={"authenticated": False})
    clear_user_session_cookie(response, settings)
    admin_session.clear_session_cookie(response, settings)
    return response


@router.post("/change-password")
def change_password(
    request: Request,
    body: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    principal = resolve_principal(request, db, settings)
    if principal is None or principal.user is None:
        return _error(401, "login_required", "Accedi per cambiare la password.")
    user = principal.user
    current = str((body or {}).get("current_password") or "")
    new = str((body or {}).get("new_password") or "")
    if not verify_password_hash(current, user.password_hash):
        return _error(400, "wrong_current_password", "La password attuale non e' corretta.")
    problem = password_problem(new)
    if problem:
        return _error(400, "weak_password", problem)
    if new == current:
        return _error(400, "same_password", "La nuova password deve essere diversa da quella attuale.")
    user.password_hash = hash_password(new)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    # gli altri dispositivi devono rientrare con la password nuova
    revoke_user_sessions(db, user.id, "password", keep_session_id=principal.session_id)
    db.commit()
    return JSONResponse(content=_me(resolve_principal(request, db, settings), settings))
