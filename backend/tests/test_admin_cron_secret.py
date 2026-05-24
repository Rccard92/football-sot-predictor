"""Test configurazione secret job pre-match (CRON_SECRET / ADMIN_CRON_SECRET)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core.admin_auth import (
    require_admin_cron_secret,
    require_pre_match_job_access,
    resolve_cron_secret,
)
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resolve_cron_secret_prefers_cron_secret_env(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "from-cron")
    monkeypatch.setenv("ADMIN_CRON_SECRET", "from-admin")
    get_settings.cache_clear()
    assert resolve_cron_secret() == "from-cron"


def test_resolve_cron_secret_fallback_admin_cron_secret(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.setenv("ADMIN_CRON_SECRET", "legacy-admin")
    get_settings.cache_clear()
    assert resolve_cron_secret() == "legacy-admin"


def test_require_admin_cron_secret_missing_in_production():
    with patch("app.core.admin_auth.resolve_cron_secret", return_value=""):
        with patch("app.core.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.app_env = "production"
            with pytest.raises(HTTPException) as exc:
                require_admin_cron_secret("any", None)
    assert exc.value.status_code == 503
    assert exc.value.detail == "CRON_SECRET non configurato sul server"


def test_require_admin_cron_secret_valid_header():
    with patch("app.core.admin_auth.resolve_cron_secret", return_value="test-secret"):
        with patch("app.core.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.app_env = "production"
            require_admin_cron_secret("test-secret", None)


def test_require_admin_cron_secret_invalid_header():
    with patch("app.core.admin_auth.resolve_cron_secret", return_value="test-secret"):
        with patch("app.core.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.app_env = "production"
            with pytest.raises(HTTPException) as exc:
                require_admin_cron_secret("wrong", None)
    assert exc.value.status_code == 401


def test_require_pre_match_job_access_admin_ui_without_header():
    """Admin UI: nessun header cron → consentito."""
    require_pre_match_job_access(None, None)


def test_require_pre_match_job_access_cron_valid_header():
    with patch("app.core.admin_auth.resolve_cron_secret", return_value="cron-ok"):
        with patch("app.core.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.app_env = "production"
            require_pre_match_job_access("cron-ok", None)


def test_require_pre_match_job_access_cron_invalid_header():
    with patch("app.core.admin_auth.resolve_cron_secret", return_value="cron-ok"):
        with patch("app.core.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.app_env = "production"
            with pytest.raises(HTTPException) as exc:
                require_pre_match_job_access("bad", None)
    assert exc.value.status_code == 401
    assert "Credenziali job non valide" in str(exc.value.detail)
