"""Account utenti (dal 29/10/2026): password, sessioni e "chi sta chiamando" per ogni richiesta.

- Password: hash scrypt con sale casuale; la password generata dall'admin vale fino al primo accesso,
  poi il cambio e' obbligatorio (`must_change_password`).
- Sessione: token casuale nel cookie HttpOnly `cecchino_session`; nel database solo lo SHA-256, cosi' una
  copia del database non basta per entrare. Scade dopo `user_session_days` giorni; al massimo
  `user_max_devices` sessioni attive per account (la piu' vecchia viene scollegata).
- Chi chiama (`Principal`): utente con sessione, accesso di emergenza con la password admin storica
  (cookie `cecchino_admin_session`, vale come amministratore), oppure la chiave di audit dell'MCP (solo GET).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.app_user import ROLE_ADMIN, AppUser, AppUserSession

logger = logging.getLogger(__name__)

USER_SESSION_COOKIE = "cecchino_session"
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_TOUCH_EVERY = timedelta(minutes=5)  # ultimo utilizzo aggiornato al massimo ogni 5 minuti
# alfabeto senza caratteri che si confondono (0/O, 1/l/I) per la password da mandare su WhatsApp
_PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MIN_PASSWORD_LENGTH = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    # SQLite restituisce datetime senza fuso: si considerano UTC
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


# --- password ---------------------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    b64 = lambda raw: base64.b64encode(raw).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password_hash(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        got = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


def generate_password(length: int = 12) -> str:
    """Password casuale con almeno una minuscola, una maiuscola e una cifra."""
    while True:
        pw = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def password_problem(password: str) -> str | None:
    """Messaggio d'errore se la nuova password non va bene, altrimenti None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "La password deve contenere almeno una lettera e un numero."
    return None


# --- sessioni ---------------------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:300]


def active_sessions(db: Session, user_id: int, now: datetime | None = None) -> list[AppUserSession]:
    now = now or _now()
    rows = db.execute(
        select(AppUserSession)
        .where(AppUserSession.user_id == user_id, AppUserSession.revoked_at.is_(None))
        .order_by(AppUserSession.last_seen_at.asc())
    ).scalars().all()
    return [s for s in rows if _aware(s.expires_at) > now]


def create_user_session(
    db: Session, user: AppUser, *, ip: str | None, agent: str | None, settings: Settings | None = None
) -> str:
    """Nuova sessione; se l'account ha gia' il massimo di dispositivi, si scollega il meno usato di recente."""
    settings = settings or get_settings()
    now = _now()
    current = active_sessions(db, user.id, now)
    max_devices = max(1, int(settings.user_max_devices))
    while len(current) >= max_devices:
        oldest = current.pop(0)
        oldest.revoked_at = now
        oldest.revoke_reason = "limite_dispositivi"
    token = secrets.token_urlsafe(32)
    db.add(
        AppUserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=int(settings.user_session_days)),
            ip=ip,
            user_agent=agent,
        )
    )
    return token


def revoke_user_sessions(db: Session, user_id: int, reason: str, *, keep_session_id: int | None = None) -> int:
    now = _now()
    n = 0
    for s in active_sessions(db, user_id, now):
        if keep_session_id is not None and s.id == keep_session_id:
            continue
        s.revoked_at = now
        s.revoke_reason = reason
        n += 1
    return n


def resolve_user_session(db: Session, token: str) -> tuple[AppUser, AppUserSession] | None:
    if not token:
        return None
    row = db.execute(
        select(AppUserSession, AppUser)
        .join(AppUser, AppUser.id == AppUserSession.user_id)
        .where(AppUserSession.token_hash == _token_hash(token))
    ).first()
    if row is None:
        return None
    session, user = row
    now = _now()
    if session.revoked_at is not None or _aware(session.expires_at) <= now or not user.is_active:
        return None
    if now - _aware(session.last_seen_at) > _TOUCH_EVERY:
        session.last_seen_at = now
        try:
            db.commit()
        except Exception:  # noqa: BLE001 - l'ultimo utilizzo e' solo informativo
            db.rollback()
    return user, session


def _cross_site(settings: Settings) -> bool:
    return settings.app_env != "development"


def set_user_session_cookie(response: Response, token: str, settings: Settings | None = None) -> None:
    """Come il cookie admin: SameSite=None+Secure in deploy (vale sia dal dominio del frontend tramite
    proxy sia da dominio diverso), Lax in locale."""
    settings = settings or get_settings()
    cross = _cross_site(settings)
    response.set_cookie(
        key=USER_SESSION_COOKIE,
        value=token,
        max_age=int(settings.user_session_days) * 86400,
        httponly=True,
        secure=cross,
        samesite="none" if cross else "lax",
        path="/",
    )


def clear_user_session_cookie(response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    cross = _cross_site(settings)
    response.delete_cookie(key=USER_SESSION_COOKIE, httponly=True, secure=cross, samesite="none" if cross else "lax", path="/")


# --- chi sta chiamando ------------------------------------------------------------------------------

KIND_USER = "user"
KIND_EMERGENCY_ADMIN = "emergency_admin"
KIND_AUDIT = "audit"


@dataclass
class Principal:
    kind: str
    is_admin: bool
    tabs: frozenset[str] = field(default_factory=frozenset)
    user: AppUser | None = None
    session_id: int | None = None
    must_change_password: bool = False

    def payload(self) -> dict:
        from app.models.app_user import user_payload

        return {
            "kind": self.kind,
            "is_admin": self.is_admin,
            "tabs": sorted(self.tabs),
            "must_change_password": self.must_change_password,
            "user": user_payload(self.user) if self.user else None,
        }


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def resolve_principal(request: Request, db: Session | None, settings: Settings | None = None) -> Principal | None:
    """Chi sta chiamando, oppure None. Il database si apre solo se c'e' un cookie di sessione utente."""
    settings = settings or get_settings()
    token = request.cookies.get(USER_SESSION_COOKIE) or ""
    if token and db is not None:
        found = resolve_user_session(db, token)
        if found is not None:
            user, session = found
            is_admin = user.role == ROLE_ADMIN
            return Principal(
                kind=KIND_USER,
                is_admin=is_admin,
                tabs=frozenset(user.tabs_json or []),
                user=user,
                session_id=session.id,
                must_change_password=bool(user.must_change_password),
            )

    from app.core.admin_session import current_session  # accesso di emergenza con la password admin storica

    if current_session(request, settings) is not None:
        return Principal(kind=KIND_EMERGENCY_ADMIN, is_admin=True)

    audit = (settings.audit_api_token or "").strip()
    given = _bearer(request)
    if audit and given and request.method.upper() in ("GET", "HEAD") and hmac.compare_digest(given.encode(), audit.encode()):
        return Principal(kind=KIND_AUDIT, is_admin=False)
    return None


# --- tentativi di accesso ---------------------------------------------------------------------------

MAX_FAILED_LOGINS = 5
LOGIN_LOCKOUT_SECONDS = 300
_failed: dict[str, tuple[int, float]] = {}


def login_lockout_remaining(*keys: str) -> int:
    import time

    now = time.time()
    worst = 0
    for k in keys:
        attempts, until = _failed.get(k, (0, 0.0))
        if attempts >= MAX_FAILED_LOGINS:
            worst = max(worst, int(until - now))
    return max(0, worst)


def register_failed_login(*keys: str) -> None:
    import time

    for k in keys:
        attempts, _ = _failed.get(k, (0, 0.0))
        _failed[k] = (attempts + 1, time.time() + LOGIN_LOCKOUT_SECONDS)


def reset_failed_logins(*keys: str) -> None:
    for k in keys:
        _failed.pop(k, None)
