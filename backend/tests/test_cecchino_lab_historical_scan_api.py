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
    filename, data = build_ai_report_zip_bytes(db, 7, mode="full_archive")
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


def _snap_base(**overrides):
    base = dict(
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
    base.update(overrides)
    return SimpleNamespace(**base)


def _market_row(*, snap_id: int, lab_match_id: int, market_key: str, run_id: int = 1):
    return SimpleNamespace(
        run_id=run_id,
        match_snapshot_id=snap_id,
        lab_match_id=lab_match_id,
        market_key=market_key,
        market_label=market_key,
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
        signal_active=False,
        signal_sources_json={"sources": [], "signal_family": None, "active_signal_count": 0},
        evaluation_status="won",
        won=True,
        profit_1u_real=1.0,
        profit_1u_synthetic=None,
        profit_category="actual_bet365",
        result_reason="ok",
    )


@pytest.mark.parametrize(
    "balance_v5_json,expected_class,expect_warning_substr",
    [
        ({"structural_summary": {"class": "balance"}}, "balance", None),
        ({"structural_summary": {"class_key": "imbalance"}}, "imbalance", None),
        (
            {"structural_summary": "Dati cecchino_final non disponibili."},
            "Dati cecchino_final non disponibili.",
            None,
        ),
        ({"structural_summary": None}, "unknown", None),
        ({"structural_summary": ["x"]}, "unknown", "unexpected_structural_summary_type:list"),
        ({"structural_summary": 42}, "unknown", "unexpected_structural_summary_type:int"),
        ({}, "unknown", None),
    ],
)
def test_ai_report_structural_summary_shapes(balance_v5_json, expected_class, expect_warning_substr):
    import io
    import json
    import zipfile

    from app.services.cecchino_data_lab.historical_ai_report import (
        _structural_class,
        build_ai_report_zip_bytes,
    )

    structural = (
        balance_v5_json.get("structural_summary") if isinstance(balance_v5_json, dict) else None
    )
    cls, warn = _structural_class(structural)
    assert cls == expected_class
    if expect_warning_substr:
        assert warn and expect_warning_substr in warn
    else:
        assert warn is None or warn == "empty_structural_summary_string"

    run = SimpleNamespace(
        id=1,
        season_label="2021/2022",
        scan_version="v2",
        source_git_commit="abc",
        preflight_json={"status": "ready"},
        module_policy_json={"run_scope": "pilot", "is_partial_run": True, "max_matches": 200},
    )
    snap = _snap_base(balance_v5_json=balance_v5_json)
    market = _market_row(snap_id=1, lab_match_id=100, market_key="HOME")
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [[snap], [market]]
    filename, data = build_ai_report_zip_bytes(db, 1, mode="full_archive")
    assert filename.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        summary = json.loads(zf.read("summary.json"))
        patterns = json.loads(zf.read("patterns.json"))
        markets_lines = [
            ln for ln in zf.read("markets.jsonl").decode("utf-8").splitlines() if ln.strip()
        ]
    expected_files = {
        "manifest.json",
        "summary.json",
        "data_quality.json",
        "eligibility.json",
        "module_coverage.json",
        "patterns.json",
        "matches.jsonl",
        "markets.jsonl",
        "AI_INSTRUCTIONS.md",
        "SCHEMA.md",
    }
    assert expected_files <= names
    assert len(markets_lines) == 1
    balance_agg = summary["eligible_analysis"]["aggregations"].get("balance_class") or {}
    assert expected_class in balance_agg
    bal_patterns = [
        p
        for p in patterns["patterns"]
        if p["conditions"].get("balance_class") == expected_class
        and p["conditions"].get("market_key") == "HOME"
        and "rating_band" not in p["conditions"]
        and "signal" not in p["conditions"]
    ]
    assert bal_patterns
    if expect_warning_substr:
        warnings = summary["data_coverage"].get("warnings") or []
        assert any(expect_warning_substr in w for w in warnings)


def test_ai_report_1582_markets_excludes_non_eligible():
    import io
    import zipfile

    from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
    from app.services.cecchino_data_lab.historical_ai_report import build_ai_report_zip_bytes

    market_keys = [k for k, _ in KPI_V2_ROW_DEFS]
    assert len(market_keys) == 14

    run = SimpleNamespace(
        id=1,
        season_label="2021/2022",
        scan_version="v2",
        source_git_commit="abc",
        preflight_json={"status": "ready"},
        module_policy_json={"run_scope": "pilot", "is_partial_run": True, "max_matches": 200},
    )
    eligible_snaps = []
    excluded_snaps = []
    markets = []
    for i in range(113):
        snap_id = i + 1
        eligible_snaps.append(
            _snap_base(
                id=snap_id,
                lab_match_id=1000 + i,
                chronological_order=i,
                # string structural_summary reproduces production crash shape
                balance_v5_json={
                    "structural_summary": "Analisi non disponibile per mismatch di identità fixture."
                },
            )
        )
        for mk in market_keys:
            markets.append(
                _market_row(snap_id=snap_id, lab_match_id=1000 + i, market_key=mk, run_id=1)
            )
    for j in range(87):
        excluded_snaps.append(
            _snap_base(
                id=1000 + j,
                lab_match_id=5000 + j,
                chronological_order=200 + j,
                historical_eligibility_status="excluded_insufficient_history",
                historical_eligibility_reason="insufficient_history",
                settlement_status="excluded",
                settlement_summary_json={"markets_analyzed": 0},
                balance_v5_json={"structural_summary": ["bad"]},
            )
        )

    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [
        eligible_snaps + excluded_snaps,
        markets,  # only eligible market rows persisted in real run
    ]
    _filename, data = build_ai_report_zip_bytes(db, 1, mode="full_archive")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        import json

        summary = json.loads(zf.read("summary.json"))
        markets_lines = [
            ln for ln in zf.read("markets.jsonl").decode("utf-8").splitlines() if ln.strip()
        ]
    assert len(markets_lines) == 1582
    assert summary["data_coverage"]["eligible_core"] == 113
    assert summary["data_coverage"]["excluded"] == 87
    assert summary["excluded_diagnostics"]["count"] == 87
    # excluded must not inflate eligible market metrics
    assert summary["data_coverage"]["eligible_market_rows"] == 1582
    home_bucket = summary["eligible_analysis"]["aggregations"]["market"]["HOME"]
    assert home_bucket["sample_size"] == 113


def test_structural_class_unit_helpers():
    from app.services.cecchino_data_lab.historical_ai_report import (
        _as_dict,
        _as_list,
        _structural_class,
    )

    assert _as_dict({"a": 1}) == {"a": 1}
    assert _as_dict("x") == {}
    assert _as_dict(None) == {}
    assert _as_list([1]) == [1]
    assert _as_list("x") == []
    assert _structural_class({"class": "a"})[0] == "a"
    assert _structural_class({"class_key": "b"})[0] == "b"
    assert _structural_class("hello")[0] == "hello"
    assert _structural_class(None)[0] == "unknown"
    assert _structural_class([])[0] == "unknown"
    assert _structural_class(3)[0] == "unknown"
