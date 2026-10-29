"""Gestione utenti dal pannello Admin (dal 29/10/2026): solo amministratori, anche in lettura.

Gli account non si cancellano mai: si disattivano (la persona esce subito da tutti i dispositivi) e si
possono riattivare; lo storico degli accessi resta.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_control import TAB_CATALOG, require_admin_principal
from app.core.database import get_db
from app.core.user_auth import (
    Principal,
    _aware,
    active_sessions,
    generate_password,
    hash_password,
    normalize_email,
    revoke_user_sessions,
)
from app.models.app_user import ROLE_ADMIN, ROLE_USER, AppLoginEvent, AppUser, AppUserSession, user_payload

router = APIRouter(prefix="/admin/users", tags=["admin-users"], dependencies=[Depends(require_admin_principal)])

_TAB_KEYS = {t["key"] for t in TAB_CATALOG}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_user(db: Session, user_id: int) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return user


def _is_self(request: Request, user: AppUser) -> bool:
    principal: Principal | None = getattr(request.state, "principal", None)
    return bool(principal and principal.user and principal.user.id == user.id)


def _clean_fields(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, limit in (("first_name", 80), ("last_name", 80), ("phone", 32)):
        if key in body or not partial:
            value = str(body.get(key) or "").strip()
            if key != "phone" and not value:
                raise HTTPException(status_code=400, detail="Nome e cognome sono obbligatori")
            out[key] = (value[:limit] or None) if key == "phone" else value[:limit]
    if "email" in body or not partial:
        email = normalize_email(body.get("email"))
        if "@" not in email or "." not in email.split("@")[-1] or email == "admin":
            raise HTTPException(status_code=400, detail="Email non valida")
        out["email"] = email
    if "role" in body or not partial:
        role = str(body.get("role") or ROLE_USER)
        if role not in (ROLE_ADMIN, ROLE_USER):
            raise HTTPException(status_code=400, detail="Ruolo non valido")
        out["role"] = role
    if "tabs" in body or not partial:
        tabs = body.get("tabs") or []
        if not isinstance(tabs, list):
            raise HTTPException(status_code=400, detail="Schede non valide")
        unknown = [t for t in tabs if t not in _TAB_KEYS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Schede sconosciute: {', '.join(map(str, unknown))}")
        out["tabs_json"] = sorted(set(tabs))
    return out


def _with_activity(db: Session, user: AppUser) -> dict[str, Any]:
    sessions = active_sessions(db, user.id)
    return {
        **user_payload(user),
        "active_devices": len(sessions),
        "last_seen_at": max((_aware(s.last_seen_at) for s in sessions), default=None),
    }


@router.get("/tabs")
def list_tabs() -> dict[str, Any]:
    """Schede assegnabili a un utente (l'Admin resta solo per gli amministratori)."""
    return {"tabs": TAB_CATALOG}


@router.get("")
def list_users(db: Session = Depends(get_db)) -> dict[str, Any]:
    users = db.execute(select(AppUser).order_by(AppUser.is_active.desc(), AppUser.last_name, AppUser.first_name)).scalars().all()
    return {"users": [_with_activity(db, u) for u in users]}


@router.post("")
def create_user(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    fields = _clean_fields(body or {}, partial=False)
    if db.execute(select(AppUser.id).where(AppUser.email == fields["email"])).first():
        raise HTTPException(status_code=409, detail="Esiste gia' un utente con questa email")
    password = generate_password()
    user = AppUser(**fields, password_hash=hash_password(password), must_change_password=True, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    # la password si vede solo qui: nel database resta l'hash
    return {"user": _with_activity(db, user), "password": password}


@router.patch("/{user_id}")
def update_user(user_id: int, body: dict[str, Any], request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _get_user(db, user_id)
    fields = _clean_fields(body or {}, partial=True)
    if _is_self(request, user) and fields.get("role", ROLE_ADMIN) != ROLE_ADMIN:
        raise HTTPException(status_code=400, detail="Non puoi togliere a te stesso il ruolo di amministratore")
    if "email" in fields and fields["email"] != user.email:
        if db.execute(select(AppUser.id).where(AppUser.email == fields["email"], AppUser.id != user.id)).first():
            raise HTTPException(status_code=409, detail="Esiste gia' un utente con questa email")
    for key, value in fields.items():
        setattr(user, key, value)
    db.commit()
    return {"user": _with_activity(db, user)}


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _get_user(db, user_id)
    if _is_self(request, user):
        raise HTTPException(status_code=400, detail="Per la tua password usa 'Cambia password'")
    password = generate_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    revoke_user_sessions(db, user.id, "password")
    db.commit()
    return {"user": _with_activity(db, user), "password": password}


@router.post("/{user_id}/deactivate")
def deactivate_user(user_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _get_user(db, user_id)
    if _is_self(request, user):
        raise HTTPException(status_code=400, detail="Non puoi disattivare il tuo account")
    user.is_active = False
    user.deactivated_at = _now()
    revoke_user_sessions(db, user.id, "revoca")
    db.commit()
    return {"user": _with_activity(db, user)}


@router.post("/{user_id}/activate")
def activate_user(user_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _get_user(db, user_id)
    user.is_active = True
    user.deactivated_at = None
    db.commit()
    return {"user": _with_activity(db, user)}


@router.post("/{user_id}/revoke-sessions")
def revoke_sessions(user_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _get_user(db, user_id)
    principal: Principal | None = getattr(request.state, "principal", None)
    keep = principal.session_id if _is_self(request, user) and principal else None
    n = revoke_user_sessions(db, user.id, "revoca", keep_session_id=keep)
    db.commit()
    return {"user": _with_activity(db, user), "revoked": n}


@router.get("/{user_id}/sessions")
def user_sessions(user_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    _get_user(db, user_id)
    rows = db.execute(
        select(AppUserSession).where(AppUserSession.user_id == user_id).order_by(AppUserSession.created_at.desc()).limit(50)
    ).scalars().all()
    now = _now()
    return {
        "sessions": [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat(),
                "last_seen_at": s.last_seen_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
                "active": s.revoked_at is None and _aware(s.expires_at) > now,
                "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
                "revoke_reason": s.revoke_reason,
                "ip": s.ip,
                "user_agent": s.user_agent,
            }
            for s in rows
        ]
    }


@router.get("/login-events")
def login_events(user_id: int | None = None, limit: int = 100, db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(AppLoginEvent).order_by(AppLoginEvent.created_at.desc()).limit(max(1, min(limit, 500)))
    if user_id is not None:
        q = q.where(AppLoginEvent.user_id == user_id)
    rows = db.execute(q).scalars().all()
    failed_24h = db.execute(
        select(func.count(AppLoginEvent.id)).where(
            AppLoginEvent.success.is_(False),
            AppLoginEvent.created_at >= datetime.fromtimestamp(_now().timestamp() - 86400, tz=timezone.utc),
        )
    ).scalar_one()
    return {
        "failed_last_24h": int(failed_24h or 0),
        "events": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "email": e.email,
                "success": e.success,
                "reason": e.reason,
                "ip": e.ip,
                "user_agent": e.user_agent,
                "created_at": e.created_at.isoformat(),
            }
            for e in rows
        ],
    }
