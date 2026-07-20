"""Test API Monitoraggio Segno 1."""

from __future__ import annotations

import io
import os
import zipfile
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.services.cecchino.cecchino_home_wins_monitoring import SELECTION_CONTRACT


def _client(db: MagicMock | None = None) -> TestClient:
    mock_db = db or MagicMock()

    def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def teardown_module(_module=None):
    app.dependency_overrides.pop(get_db, None)


def test_list_endpoint_ok():
    client = _client()
    payload = {
        "status": "ok",
        "dataset_version": "cecchino_home_wins_monitoring_v1_1",
        "selection_contract": SELECTION_CONTRACT,
        "total": 1,
        "page": 1,
        "page_size": 50,
        "summary": {},
        "available_filters": {},
        "items": [{"today_fixture_id": 1, "outcome_1x2": "1"}],
    }
    with patch(
        "app.routes.cecchino_home_wins.list_home_wins", return_value=payload
    ) as mocked:
        res = client.get("/api/cecchino/home-wins?page=1&page_size=50&country=Italy")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["selection_contract"]["signal_1_used_for_selection"] is False
    assert body["selection_contract"]["eligible_only"] is True
    mocked.assert_called_once()
    kwargs = mocked.call_args.kwargs
    assert kwargs["country"] == "Italy"
    assert kwargs["page"] == 1


def test_detail_endpoint_ok_and_404():
    client = _client()
    ok = {
        "status": "ok",
        "dataset_version": "cecchino_home_wins_monitoring_v1_1",
        "selection_contract": SELECTION_CONTRACT,
        "identity": {"today_fixture_id": 9},
        "post_match_outcome": {"outcome_1x2": "1"},
        "source_integrity": {"signal_1_used_for_selection": False},
        "pre_match_snapshot": {},
        "observational": {"signal_1_used_for_selection": False},
        "warnings": [],
    }
    with patch("app.routes.cecchino_home_wins.get_home_win_detail", return_value=ok):
        res = client.get("/api/cecchino/home-wins/9")
    assert res.status_code == 200
    assert res.json()["post_match_outcome"]["outcome_1x2"] == "1"

    with patch(
        "app.routes.cecchino_home_wins.get_home_win_detail",
        return_value={"status": "error", "reason": "not_in_home_wins_cohort"},
    ):
        res404 = client.get("/api/cecchino/home-wins/99")
    assert res404.status_code == 404


def test_detail_non_eligible_returns_404():
    """Dettaglio di fixture non eligible → 404 not_in_home_wins_cohort."""
    client = _client()
    with patch(
        "app.routes.cecchino_home_wins.get_home_win_detail",
        return_value={
            "status": "error",
            "reason": "not_in_home_wins_cohort",
            "selection_contract": SELECTION_CONTRACT,
        },
    ):
        res = client.get("/api/cecchino/home-wins/88")
    assert res.status_code == 404
    assert res.json()["reason"] == "not_in_home_wins_cohort"
    assert SELECTION_CONTRACT["eligible_only"] is True


def test_export_endpoint_zip():
    client = _client()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", b'{"record_count":1}')
        zf.writestr("schema.json", b"{}")
        zf.writestr("quality_report.json", b"{}")
        zf.writestr("home_wins_features.csv", b"today_fixture_id\n1\n")
        zf.writestr("home_wins_full.jsonl", b"{}\n")
    content = buf.getvalue()
    with patch(
        "app.routes.cecchino_home_wins.build_home_wins_export_zip",
        return_value=(content, "SOT_CECCHINO_HOME_WINS_DATASET_TEST.zip"),
    ):
        res = client.get("/api/cecchino/home-wins/export")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "SOT_CECCHINO_HOME_WINS_DATASET_TEST.zip" in res.headers.get(
        "content-disposition", ""
    )
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        assert "manifest.json" in zf.namelist()


def test_no_rebuild_via_api_monkeypatch():
    client = _client()
    with (
        patch(
            "app.services.cecchino.cecchino_balance_v5.build_cecchino_balance_v5",
            side_effect=RuntimeError("no rebuild"),
        ),
        patch(
            "app.routes.cecchino_home_wins.list_home_wins",
            return_value={
                "status": "ok",
                "dataset_version": "cecchino_home_wins_monitoring_v1_1",
                "selection_contract": SELECTION_CONTRACT,
                "total": 0,
                "page": 1,
                "page_size": 50,
                "summary": {},
                "available_filters": {},
                "items": [],
            },
        ),
        patch(
            "app.routes.cecchino_home_wins.get_home_win_detail",
            return_value={
                "status": "ok",
                "selection_contract": SELECTION_CONTRACT,
                "identity": {},
                "post_match_outcome": {"outcome_1x2": "1"},
                "source_integrity": {},
                "pre_match_snapshot": {
                    "balance_v5_monitoring": {
                        "status": "unavailable",
                        "reason": "persisted_balance_snapshot_missing",
                    }
                },
                "observational": {"signal_1_used_for_selection": False},
                "warnings": [],
            },
        ),
        patch(
            "app.routes.cecchino_home_wins.build_home_wins_export_zip",
            return_value=(b"PK\x05\x06" + b"\x00" * 18, "empty.zip"),
        ),
    ):
        assert client.get("/api/cecchino/home-wins").status_code == 200
        assert client.get("/api/cecchino/home-wins/1").status_code == 200
        assert client.get("/api/cecchino/home-wins/export").status_code == 200
