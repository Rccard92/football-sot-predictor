"""Test classificazione quota provider API-Football e no-op budget guard in scan."""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

import httpx
import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.services.api_football_client import (
    ApiFootballClient,
    ApiFootballError,
    ApiFootballQuotaExhausted,
    is_provider_quota_exhausted,
)
from app.services.api_usage_service import (
    check_api_budget_before_scan,
    check_api_budget_during_scan,
)
from app.services.cecchino.cecchino_today_service import run_scan
from app.models.cecchino_today_scan_job import (
    JOB_STATUS_FAILED_BUDGET_GUARD,
    JOB_STATUS_PARTIAL_STOPPED_BUDGET,
    JOB_STATUS_PROVIDER_QUOTA_EXHAUSTED,
    JOB_TERMINAL_STATUSES,
)


TARGET = date(2026, 8, 8)


def test_is_provider_quota_exhausted_on_errors_requests():
    assert is_provider_quota_exhausted(
        status_code=200,
        errors={"requests": "You have reached the request limit for the day"},
    )


def test_is_provider_quota_exhausted_remaining_zero_with_429():
    assert is_provider_quota_exhausted(
        status_code=429,
        headers={"x-ratelimit-requests-remaining": "0"},
    )


def test_generic_429_not_quota_exhausted():
    assert not is_provider_quota_exhausted(status_code=429, headers={})
    assert not is_provider_quota_exhausted(status_code=429, errors=None)


def test_5xx_not_quota_exhausted():
    assert not is_provider_quota_exhausted(status_code=500)
    assert not is_provider_quota_exhausted(status_code=503, errors={"server": "busy"})


def test_empty_errors_not_quota():
    assert not is_provider_quota_exhausted(status_code=200, errors={})
    assert not is_provider_quota_exhausted(status_code=200, errors=None)


def test_client_raises_quota_exhausted_no_retry():
    client = ApiFootballClient(api_key="test-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = httpx.Headers(
        {"content-type": "application/json", "x-ratelimit-requests-remaining": "0"}
    )
    mock_resp.json.return_value = {
        "errors": {"requests": "You have reached the request limit for the day"},
        "response": [],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.api_football_client.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.return_value = mock_resp
        with pytest.raises(ApiFootballQuotaExhausted) as exc:
            client.get("odds", {"fixture": 1})
    assert exc.value.endpoint == "odds"
    # Una sola chiamata: nessun retry su quota.
    assert mock_cls.return_value.__enter__.return_value.get.call_count == 1


def test_client_429_transient_retries():
    client = ApiFootballClient(api_key="test-key")
    resp_429 = MagicMock(spec=httpx.Response)
    resp_429.status_code = 429
    resp_429.headers = httpx.Headers({"content-type": "application/json", "Retry-After": "0"})
    resp_429.json.return_value = {"errors": {}, "response": []}
    resp_429.raise_for_status.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=resp_429
    )

    resp_ok = MagicMock(spec=httpx.Response)
    resp_ok.status_code = 200
    resp_ok.headers = httpx.Headers({"content-type": "application/json"})
    resp_ok.json.return_value = {"errors": {}, "response": [{"ok": True}]}
    resp_ok.raise_for_status = MagicMock()

    with patch("app.services.api_football_client.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.side_effect = [resp_429, resp_ok]
        with patch("app.services.api_football_client.time.sleep"):
            data = client.get("fixtures", {"date": "2026-08-08"})
    assert data["response"][0]["ok"] is True
    assert mock_cls.return_value.__enter__.return_value.get.call_count == 2


def test_local_budget_guards_never_raise():
    db = MagicMock()
    check_api_budget_before_scan(db, usage_date=TARGET)
    check_api_budget_during_scan(db, job_id="j", usage_date=TARGET, job_calls=10_000)


def test_historical_budget_statuses_still_terminal():
    assert JOB_STATUS_PARTIAL_STOPPED_BUDGET in JOB_TERMINAL_STATUSES
    assert JOB_STATUS_FAILED_BUDGET_GUARD in JOB_TERMINAL_STATUSES
    assert JOB_STATUS_PROVIDER_QUOTA_EXHAUSTED in JOB_TERMINAL_STATUSES


def test_run_scan_provider_quota_on_fixtures_fetch():
    db = MagicMock()
    client = MagicMock()
    client.get_fixtures_by_date.side_effect = ApiFootballQuotaExhausted(
        "API-Football ha confermato che non sono disponibili altre richieste.",
        endpoint="fixtures",
    )
    report = run_scan(db, scan_date=TARGET, client=client, force_rescan=True)
    assert report["status"] == "provider_quota_exhausted"
    assert report["diagnostic_code"] == "provider_quota_exhausted"
    assert report["stopped_at_endpoint"] == "fixtures"
    assert report["fixtures_processed"] == 0
    assert report["execution_date"]
    assert "errors" in report


def test_cecchino_today_service_has_no_budget_during_scan_import():
    import app.services.cecchino.cecchino_today_service as mod

    assert not hasattr(mod, "check_api_budget_during_scan")
    assert not hasattr(mod, "BudgetGuardStop")
    source = open(mod.__file__, encoding="utf-8-sig").read()
    assert "check_api_budget_during_scan" not in source
    assert "check_api_budget_before_scan" not in source


def test_start_scan_job_has_no_budget_guard_call():
    import app.services.cecchino.cecchino_today_scan_job_service as mod

    source = open(mod.__file__, encoding="utf-8-sig").read()
    assert "check_api_budget_before_scan" not in source
    assert "BudgetGuardStop" not in source
