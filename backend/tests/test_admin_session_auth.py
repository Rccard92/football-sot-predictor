"""Sessione admin: login, cookie firmato e protezione del control plane RUN V2."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import admin_session
from app.core.admin_session import SESSION_COOKIE_NAME
from app.core.config import Settings
from app.core.database import get_db
from app.routes import admin_session_auth
from app.routes import cecchino_run_v2 as routes_v2

PASSWORD = "password-admin-di-prova"
SECRET = "segreto-di-firma-molto-lungo-per-i-test"


def _settings(**overrides) -> Settings:
    base = {
        "database_url": "postgresql://user:pass@localhost:5432/test",
        "admin_password": PASSWORD,
        "admin_session_secret": SECRET,
        "app_env": "production",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _clean_throttle():
    admin_session._failed_attempts.clear()
    yield
    admin_session._failed_attempts.clear()


def _client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.include_router(admin_session_auth.router, prefix="/api")
    app.include_router(routes_v2.router, prefix="/api")
    app.include_router(routes_v2.admin_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[admin_session.get_settings] = lambda: settings
    # https obbligatorio fuori da development: un cookie Secure non verrebbe
    # nemmeno memorizzato dal client su http, esattamente come nel browser.
    scheme = "http" if settings.app_env == "development" else "https"
    return TestClient(app, base_url=f"{scheme}://testserver")


def test_endpoint_admin_rifiutato_senza_sessione():
    res = _client(_settings()).post("/api/admin/cecchino-run-v2", json={"confirm": "x"})

    assert res.status_code == 401


def test_get_list_run_v2_rifiutato_senza_sessione():
    res = _client(_settings()).get("/api/cecchino-run-v2")

    assert res.status_code == 401


def test_get_export_run_v2_rifiutato_senza_sessione():
    client = _client(_settings())

    assert client.get("/api/cecchino-run-v2/1/export").status_code == 401
    assert client.get("/api/cecchino-run-v2/1/export/manifest").status_code == 401

def test_endpoint_admin_503_se_autenticazione_non_configurata():
    """Fail-closed: senza password configurata non si passa, non si apre."""
    res = _client(_settings(admin_password="", admin_session_secret="")).post(
        "/api/admin/cecchino-run-v2", json={"confirm": "x"}
    )

    assert res.status_code == 503
    assert "non configurata" in res.json()["detail"]


def test_login_con_password_giusta_imposta_cookie_httponly():
    client = _client(_settings())

    res = client.post("/api/admin/auth/login", json={"password": PASSWORD})

    assert res.status_code == 200
    assert res.json()["authenticated"] is True
    cookie = res.headers["set-cookie"]
    assert SESSION_COOKIE_NAME in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "samesite=none" in cookie.lower()
    # La password non deve mai tornare indietro.
    assert PASSWORD not in res.text


def test_login_sbagliato_401_e_nessun_cookie():
    client = _client(_settings())

    res = client.post("/api/admin/auth/login", json={"password": "sbagliata"})

    assert res.status_code == 401
    assert res.json()["error"] == "invalid_credentials"
    assert "set-cookie" not in {k.lower() for k in res.headers}


def test_sessione_valida_sblocca_il_control_plane():
    client = _client(_settings())
    client.post("/api/admin/auth/login", json={"password": PASSWORD})

    res = client.post("/api/admin/cecchino-run-v2", json={})

    # Passata l'autorizzazione, risponde la logica RUN V2 (token di conferma).
    assert res.status_code == 400
    assert res.json()["error"] == "confirm_required"


def test_logout_invalida_il_cookie():
    client = _client(_settings())
    client.post("/api/admin/auth/login", json={"password": PASSWORD})

    client.post("/api/admin/auth/logout")

    assert client.post("/api/admin/cecchino-run-v2", json={}).status_code == 401


def test_stato_sessione_prima_e_dopo_il_login():
    client = _client(_settings())

    assert client.get("/api/admin/auth/session").json() == {
        "authenticated": False,
        "expires_in": 0,
    }

    client.post("/api/admin/auth/login", json={"password": PASSWORD})
    body = client.get("/api/admin/auth/session").json()

    assert body["authenticated"] is True
    assert body["expires_in"] > 0


def test_cookie_manomesso_rifiutato():
    settings = _settings()
    client = _client(settings)
    token, _ = admin_session.create_session_token(settings)
    payload, signature = token.split(".", 1)

    client.cookies.set(SESSION_COOKIE_NAME, f"{payload}.{signature[:-2]}xx")

    assert client.post("/api/admin/cecchino-run-v2", json={}).status_code == 401


def test_cookie_firmato_con_altro_segreto_rifiutato():
    altro, _ = admin_session.create_session_token(_settings(admin_session_secret="altro-segreto"))
    client = _client(_settings())

    client.cookies.set(SESSION_COOKIE_NAME, altro)

    assert client.post("/api/admin/cecchino-run-v2", json={}).status_code == 401


def test_token_scaduto_rifiutato():
    settings = _settings(admin_session_ttl_minutes=0)
    token, expires_at = admin_session.create_session_token(settings)

    assert expires_at <= int(time.time())
    assert admin_session.verify_session_token(token, settings) is None


def test_lockout_dopo_troppi_tentativi_falliti():
    client = _client(_settings())

    for _ in range(admin_session.MAX_FAILED_ATTEMPTS):
        assert client.post("/api/admin/auth/login", json={"password": "no"}).status_code == 401

    bloccato = client.post("/api/admin/auth/login", json={"password": PASSWORD})

    assert bloccato.status_code == 429
    assert bloccato.json()["error"] == "too_many_attempts"


def test_cookie_lax_e_non_secure_in_sviluppo_locale():
    """In locale frontend e backend sono same-site: Secure su http non passerebbe."""
    client = _client(_settings(app_env="development"))

    res = client.post("/api/admin/auth/login", json={"password": PASSWORD})

    cookie = res.headers["set-cookie"]
    assert "samesite=lax" in cookie.lower()
    assert "Secure" not in cookie
