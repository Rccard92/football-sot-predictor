"""Protezione endpoint admin invocati da cron esterno."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_admin_cron_secret(
    x_admin_cron_secret: str | None = Header(default=None, alias="X-Admin-Cron-Secret"),
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    expected = (settings.admin_cron_secret or "").strip()
    if not expected:
        if settings.app_env == "development":
            return
        raise HTTPException(
            status_code=503,
            detail="ADMIN_CRON_SECRET non configurato sul server",
        )
    token = (x_admin_cron_secret or "").strip()
    if not token and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Credenziali job non valide")
