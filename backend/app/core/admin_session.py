"""Sessione admin per gli endpoint di controllo RUN V2.

Il token di conferma `RUN_CECCHINO_RUN_V2` e' una costante pubblica (sta nel
bundle frontend) e serve solo a evitare il click accidentale: non e' un
meccanismo di sicurezza. Qui c'e' l'autorizzazione vera.

Modello: password amministrativa che vive solo server-side, scambiata una volta
con un cookie di sessione HttpOnly firmato in HMAC-SHA256. Il cookie e' opaco e
autoverificante (contiene solo la scadenza), quindi non serve nessuna tabella e
funziona anche con piu' repliche.

Fail-closed: se la password o il segreto di firma non sono configurati, gli
endpoint protetti rispondono 503 in ogni ambiente. Nessun bypass in development:
e' esattamente il tipo di scorciatoia che lascia aperti gli endpoint admin.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "cecchino_admin_session"
TOKEN_VERSION = "v1"

# Throttle dei tentativi falliti, per processo. Best-effort con piu' repliche,
# ma alza comunque il costo di un attacco a dizionario sulla password.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

_failed_attempts: dict[str, tuple[int, float]] = {}


class AdminAuthNotConfigured(Exception):
    """Password o segreto di firma mancanti: si risponde 503, mai 200."""


@dataclass(frozen=True)
class AdminSession:
    expires_at: int

    @property
    def expires_in(self) -> int:
        return max(0, self.expires_at - int(time.time()))


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _require_config(settings: Settings) -> tuple[str, str]:
    password = (settings.admin_password or "").strip()
    secret = (settings.admin_session_secret or "").strip()
    if not password or not secret:
        raise AdminAuthNotConfigured
    return password, secret


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256)
    return _b64encode(digest.digest())


def create_session_token(settings: Settings | None = None) -> tuple[str, int]:
    """Token firmato e istante di scadenza (epoch)."""
    settings = settings or get_settings()
    _, secret = _require_config(settings)
    expires_at = int(time.time()) + settings.admin_session_ttl_minutes * 60
    payload_b64 = _b64encode(
        json.dumps({"v": TOKEN_VERSION, "exp": expires_at}, separators=(",", ":")).encode("utf-8")
    )
    return f"{payload_b64}.{_sign(payload_b64, secret)}", expires_at


def verify_session_token(token: str, settings: Settings | None = None) -> AdminSession | None:
    """Sessione valida, oppure None se il token e' assente, alterato o scaduto."""
    settings = settings or get_settings()
    _, secret = _require_config(settings)
    if not token or token.count(".") != 1:
        return None

    payload_b64, signature = token.split(".", 1)
    if not hmac.compare_digest(signature, _sign(payload_b64, secret)):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    if payload.get("v") != TOKEN_VERSION:
        return None
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at <= int(time.time()):
        return None
    return AdminSession(expires_at=expires_at)


def verify_password(candidate: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    password, _ = _require_config(settings)
    return hmac.compare_digest(candidate.encode("utf-8"), password.encode("utf-8"))


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def lockout_remaining(key: str) -> int:
    attempts, blocked_until = _failed_attempts.get(key, (0, 0.0))
    if attempts < MAX_FAILED_ATTEMPTS:
        return 0
    return max(0, int(blocked_until - time.time()))


def register_failed_attempt(key: str) -> None:
    attempts, _ = _failed_attempts.get(key, (0, 0.0))
    attempts += 1
    _failed_attempts[key] = (attempts, time.time() + LOCKOUT_SECONDS)


def reset_attempts(key: str) -> None:
    _failed_attempts.pop(key, None)


def set_session_cookie(response: Response, token: str, settings: Settings | None = None) -> None:
    """Cookie HttpOnly. Cross-site in deploy (frontend e backend hanno domini
    diversi), quindi SameSite=None+Secure; in locale Lax, perche' porte diverse
    dello stesso host restano same-site e Secure non passa su http."""
    settings = settings or get_settings()
    cross_site = settings.app_env != "development"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.admin_session_ttl_minutes * 60,
        httponly=True,
        secure=cross_site,
        samesite="none" if cross_site else "lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    cross_site = settings.app_env != "development"
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=cross_site,
        samesite="none" if cross_site else "lax",
        path="/",
    )


def current_session(request: Request, settings: Settings | None = None) -> AdminSession | None:
    """Sessione corrente senza sollevare: usata dall'endpoint di stato."""
    try:
        return verify_session_token(request.cookies.get(SESSION_COOKIE_NAME) or "", settings)
    except AdminAuthNotConfigured:
        return None


def require_admin_session(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AdminSession:
    """Dipendenza dei router admin RUN V2: 503 se non configurata, 401 se assente."""
    try:
        session = verify_session_token(request.cookies.get(SESSION_COOKIE_NAME) or "", settings)
    except AdminAuthNotConfigured:
        logger.error("ADMIN_PASSWORD/ADMIN_SESSION_SECRET non configurati: accesso admin negato")
        raise HTTPException(
            status_code=503,
            detail=(
                "Autenticazione admin non configurata sul server "
                "(ADMIN_PASSWORD e ADMIN_SESSION_SECRET)."
            ),
        ) from None
    if session is None:
        raise HTTPException(status_code=401, detail="Sessione admin assente o scaduta")
    return session
