"""Protezione endpoint admin invocati da cron esterno."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException

from app.core.config import get_settings


def resolve_cron_secret() -> str:
    """CRON_SECRET principale; fallback ADMIN_CRON_SECRET per retrocompatibilità."""
    settings = get_settings()
    from_settings = (settings.cron_secret or "").strip()
    if from_settings:
        return from_settings
    return (os.getenv("CRON_SECRET") or os.getenv("ADMIN_CRON_SECRET") or "").strip()


def _extract_cron_token(
    x_admin_cron_secret: str | None,
    authorization: str | None,
) -> str:
    token = (x_admin_cron_secret or "").strip()
    if not token and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    return token


def require_admin_cron_secret(
    x_admin_cron_secret: str | None = Header(default=None, alias="X-Admin-Cron-Secret"),
    authorization: str | None = Header(default=None),
) -> None:
    """Solo chiamate cron esterne: header obbligatorio e valido."""
    settings = get_settings()
    expected = resolve_cron_secret()
    token = _extract_cron_token(x_admin_cron_secret, authorization)
    if not expected:
        if settings.app_env == "development":
            return
        raise HTTPException(
            status_code=503,
            detail="CRON_SECRET non configurato sul server",
        )
    if token != expected:
        raise HTTPException(status_code=401, detail="Credenziali job non valide")


def require_pre_match_job_access(
    x_admin_cron_secret: str | None = Header(default=None, alias="X-Admin-Cron-Secret"),
    authorization: str | None = Header(default=None),
) -> None:
    """
    A) Cron esterno: header X-Admin-Cron-Secret valido (CRON_SECRET / ADMIN_CRON_SECRET).
    B) Admin UI: nessun header cron — stesso accesso implicito degli altri endpoint /api/admin/*.
    """
    token = _extract_cron_token(x_admin_cron_secret, authorization)
    if not token:
        return

    settings = get_settings()
    expected = resolve_cron_secret()
    if not expected:
        if settings.app_env == "development":
            return
        raise HTTPException(
            status_code=503,
            detail="CRON_SECRET non configurato sul server",
        )
    if token != expected:
        raise HTTPException(status_code=401, detail="Credenziali job non valide")
