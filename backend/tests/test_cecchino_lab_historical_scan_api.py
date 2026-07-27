"""Test API e job scansione storica Cecchino Lab."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.constants import HISTORICAL_SCAN_CONFIRM_TOKEN
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_scan_service import start_historical_scan


def _app() -> tuple[TestClient, MagicMock]:
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    app.include_router(cecchino_lab.admin_router, prefix="/api")
    db = MagicMock()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app), db


def test_preflight_endpoint():
    client, _db = _app()
    with patch(
        "app.routes.cecchino_lab.run_historical_scan_preflight",
        return_value={"season_label": "2021/2022", "status": "ready", "matches_total": 0},
    ):
        res = client.post(
            "/api/admin/cecchino-lab/historical-scans/preflight",
            json={"season_label": "2021/2022"},
        )
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


def test_start_requires_confirm():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as ei:
        start_historical_scan(db, season_label="2021/2022", confirm="WRONG", background=False)
    assert ei.value.code == "confirm_required"


def test_start_endpoint_with_confirm_mocked():
    client, _db = _app()
    fake_run = {
        "id": 1,
        "season_label": "2021/2022",
        "status": "pending",
        "scan_version": "v1",
        "requested_at": None,
        "started_at": None,
        "completed_at": None,
        "current_dataset_id": None,
        "current_match_id": None,
        "current_competition": None,
        "matches_total": 10,
        "matches_processed": 0,
        "matches_eligible_core": 0,
        "matches_excluded": 0,
        "matches_error": 0,
        "progress_pct": 0,
    }
    with patch(
        "app.routes.cecchino_lab.start_historical_scan",
        return_value=fake_run,
    ):
        res = client.post(
            "/api/admin/cecchino-lab/historical-scans",
            json={
                "season_label": "2021/2022",
                "confirm": HISTORICAL_SCAN_CONFIRM_TOKEN,
            },
        )
    assert res.status_code == 202
    assert res.json()["id"] == 1


def test_list_scans_endpoint():
    client, _db = _app()
    with patch("app.routes.cecchino_lab.list_historical_scans", return_value=[]):
        res = client.get("/api/cecchino-lab/historical-scans")
    assert res.status_code == 200
    assert res.json() == []


def test_duplicate_lock():
    db = MagicMock()
    with patch(
        "app.services.cecchino_data_lab.historical_scan_service.run_historical_scan_preflight",
        return_value={"status": "ready"},
    ):
        active = SimpleNamespace(id=99, status="running")
        db.scalars.return_value.first.return_value = active
        with pytest.raises(CecchinoLabImportError) as ei:
            start_historical_scan(
                db,
                season_label="2021/2022",
                confirm=HISTORICAL_SCAN_CONFIRM_TOKEN,
                background=False,
            )
        assert ei.value.code == "duplicate_active_run"


def test_start_endpoint_with_max_matches_pilot():
    client, _db = _app()
    fake_run = {
        "id": 2,
        "season_label": "2021/2022",
        "status": "pending",
        "scan_version": "v2",
        "requested_at": None,
        "started_at": None,
        "completed_at": None,
        "current_dataset_id": None,
        "current_match_id": None,
        "current_competition": None,
        "matches_total": 200,
        "matches_processed": 0,
        "matches_eligible_core": 0,
        "matches_excluded": 0,
        "matches_error": 0,
        "progress_pct": 0,
        "is_partial_run": True,
        "run_scope": "pilot",
        "max_matches": 200,
    }
    with patch(
        "app.routes.cecchino_lab.start_historical_scan",
        return_value=fake_run,
    ) as mocked:
        res = client.post(
            "/api/admin/cecchino-lab/historical-scans",
            json={
                "season_label": "2021/2022",
                "confirm": HISTORICAL_SCAN_CONFIRM_TOKEN,
                "max_matches": 200,
            },
        )
    assert res.status_code == 202
    assert res.json()["is_partial_run"] is True
    mocked.assert_called_once()
    assert mocked.call_args.kwargs.get("max_matches") == 200


def test_ai_report_zip_structure():
    import io
    import json
    import zipfile

    from app.services.cecchino_data_lab.historical_ai_report import build_ai_report_zip_bytes

    run = SimpleNamespace(
        id=7,
        season_label="2021/2022",
        scan_version="cecchino_lab_historical_scan_v2",
        source_git_commit="abc",
        preflight_json={"status": "ready"},
        module_policy_json={
            "run_scope": "pilot",
            "is_partial_run": True,
            "max_matches": 200,
        },
    )
    eligible = SimpleNamespace(
        id=1,
        dataset_id=10,
        lab_match_id=100,
        competition_name="Serie A",
        season_label="2021/2022",
        kickoff_at=None,
        chronological_order=0,
        home_team="A",
        away_team="B",
        historical_eligibility_status="eligible_core",
        historical_eligibility_reason=None,
        blocking_reasons_json=[],
        input_snapshot_json={"prior_count": 40},
        cecchino_output_json={"final": {}, "picchetti": {}, "status": "available"},
        signals_json={"rows": []},
        balance_v5_json={"structural_summary": {"class": "balance"}},
        goal_intensity_compatibility_json={"raw_features_available": True},
        purchasability_compatibility_json={"inputs_available": True},
        module_availability_json={},
        quote_sources_json={"family_1x2": {"family_snapshot_type": "closing"}},
        pre_match_payload_sha256="abc",
        pre_match_locked_at=None,
        result_json={"fulltime": {"home": 1, "away": 0}},
        settlement_status="settled",
        settlement_summary_json={"markets_analyzed": 14},
        historical_kpi_json={"rows": []},
        error_json=None,
    )
    excluded = SimpleNamespace(
        id=2,
        dataset_id=10,
        lab_match_id=101,
        competition_name="Serie A",
        season_label="2021/2022",
        kickoff_at=None,
        chronological_order=1,
        home_team="C",
        away_team="D",
        historical_eligibility_status="excluded_insufficient_history",
        historical_eligibility_reason="insufficient_history",
        blocking_reasons_json=["insufficient_history"],
        input_snapshot_json={"prior_count": 1},
        cecchino_output_json={},
        signals_json={},
        balance_v5_json={},
        goal_intensity_compatibility_json={},
        purchasability_compatibility_json={},
        module_availability_json={},
        quote_sources_json={},
        pre_match_payload_sha256="def",
        pre_match_locked_at=None,
        result_json={"fulltime": {"home": 0, "away": 0}},
        settlement_status="excluded",
        settlement_summary_json={"markets_analyzed": 0},
        historical_kpi_json=None,
        error_json=None,
    )
    market = SimpleNamespace(
        run_id=7,
        match_snapshot_id=1,
        lab_match_id=100,
        market_key="HOME",
        market_label="1",
        period="FT",
        line=None,
        quota_cecchino=2.1,
        prob_cecchino=0.4,
        quota_book=2.0,
        prob_book_raw=0.5,
        prob_book_fair=0.48,
        quote_source_type="closing",
        is_real_book_quote=True,
        is_derived_quote=False,
        derivation_method=None,
        edge_pct=5.0,
        vantaggio_prob=0.02,
        rating=62,
        signal_active=True,
        signal_sources_json={
            "sources": [{"signal_family": "HOME", "source_column": "EXCEL_D", "column_key": "excel_d", "signal_group": "HOME"}],
            "signal_family": "HOME",
            "signal_families": ["HOME"],
            "active_signal_count": 1,
        },
        evaluation_status="won",
        won=True,
        profit_1u_real=1.0,
        profit_1u_synthetic=None,
        profit_category="actual_bet365",
        result_reason="ok",
    )
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [[eligible, excluded], [market]]
    filename, data = build_ai_report_zip_bytes(db, 7)
    assert "pilot" in filename
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        summary = json.loads(zf.read("summary.json"))
        manifest = json.loads(zf.read("manifest.json"))
        markets_lines = zf.read("markets.jsonl").decode("utf-8").strip().splitlines()
        patterns = json.loads(zf.read("patterns.json"))
    assert "manifest.json" in names
    assert "matches.jsonl" in names
    assert "markets.jsonl" in names
    assert "AI_INSTRUCTIONS.md" in names
    assert "SCHEMA.md" in names
    assert "eligible_analysis" in summary
    assert "excluded_diagnostics" in summary
    assert "errors" in summary
    assert "data_coverage" in summary
    assert summary["excluded_diagnostics"]["count"] == 1
    assert manifest["is_partial_run"] is True
    assert manifest["performance_universe"] == "eligible_core_only"
    assert len(markets_lines) == 1
    mrow = json.loads(markets_lines[0])
    assert mrow["eligibility_status"] == "eligible_core"
    assert mrow["competition_name"] == "Serie A"
    assert mrow["signal_family"] == "HOME"
    assert patterns["patterns"]
    assert "status_thresholds" in patterns
