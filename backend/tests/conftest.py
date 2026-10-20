"""Fixture comuni dei test backend.

Dal 20/10/2026 i router /admin chiedono la sessione admin per POST/PUT/PATCH/DELETE
(`require_admin_session_for_writes`) e alcuni endpoint singoli chiedono `require_admin_session`.
Nei test che usano l'app vera (`app.main.app`) la sessione viene simulata, cosi' i test esistenti non
cambiano. I test che verificano proprio il 401/503 (RUN V2, V4, auth) restano intatti: per loro
`require_admin_session` non viene simulata.
"""

from __future__ import annotations

import sys

import pytest

# moduli di test che chiamano endpoint diventati protetti singolarmente il 20/10/2026
_NEEDS_FULL_SESSION = {
    "test_api_football_fixture_raw_odds",
    "test_cecchino_api_raw_inspector",
    "test_cecchino_balance_v5_empirical_analysis_jobs",
    "test_cecchino_purchasability_validation",
    "test_cecchino_purchasability_validation_jobs",
}


@pytest.fixture(autouse=True)
def _admin_session_override(request):
    if "app.main" not in sys.modules:
        yield
        return
    from app.core.admin_session import AdminSession, require_admin_session, require_admin_session_for_writes
    from app.main import app

    fake = AdminSession(expires_at=4102444800)
    module = getattr(request.module, "__name__", "").rsplit(".", 1)[-1]
    overrides = [require_admin_session_for_writes]
    if module in _NEEDS_FULL_SESSION:
        overrides.append(require_admin_session)
    for dep in overrides:
        app.dependency_overrides[dep] = lambda: fake
    try:
        yield
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)
