"""Test audit v5 — NameError import, fail-soft globale, endpoint HTTP 200."""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    BALANCE_MONITORING_KEY,
    BALANCE_MONITORING_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    build_module_analysis_pack_audit,
    build_modules_analysis_packs_audit,
    clear_module_audit_cache,
)

DATE_FROM = date(2026, 6, 19)
DATE_TO = date(2026, 7, 20)


@pytest.fixture(autouse=True)
def _clear_audit_cache():
    clear_module_audit_cache()
    yield
    clear_module_audit_cache()


def _eligible_balance_fixture(**overrides):
    payload = {
        "id": 1,
        "provider_fixture_id": 100,
        "local_fixture_id": 10,
        "competition_id": 1,
        "league_name": "Serie A",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "scan_date": date(2026, 6, 20),
        "kickoff": datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc),
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "score_fulltime_home": 1,
        "score_fulltime_away": 0,
        "score_halftime_home": None,
        "score_halftime_away": None,
        "cecchino_output_json": {
            BALANCE_MONITORING_KEY: {
                "status": "ok",
                "snapshot_version": BALANCE_MONITORING_SNAPSHOT_VERSION,
                "f36_index": 1.0,
                "f36_class": "A",
                "dominance_index": 2.0,
                "dominance_class": "B",
                "dominance_selection": "1",
                "draw_credibility_index": 30.0,
                "draw_credibility_class": "C",
                "gap_index": 3.0,
                "gap_class": "D",
                "prob_1_norm": 45.0,
                "prob_x_norm": 25.0,
                "prob_2_norm": 30.0,
                "pre_match_verified": True,
                "snapshot_timestamp": "2026-06-20T10:00:00+00:00",
            }
        },
        "kpi_panel_json": {},
        "odds_snapshot_json": {
            "meta": {"snapshot_at": "2026-06-20T10:00:00+00:00"},
        },
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _balance_audit_db():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [_eligible_balance_fixture()]
    return db


def _patch_draw_credibility(monkeypatch):
    import app.services.cecchino.cecchino_draw_credibility_research as draw_research

    monkeypatch.setattr(
        draw_research,
        "build_draw_credibility_coverage_audit",
        lambda *a, **k: {"status": "unavailable", "counts": {}},
    )


def test_balance_module_analysis_pack_audit_no_name_error(monkeypatch):
    """Attraversa _build_balance_files senza mockare build_balance_monitoring_rows."""
    _patch_draw_credibility(monkeypatch)
    db = _balance_audit_db()
    payload = build_module_analysis_pack_audit(
        db,
        module_key="balance-v5",
        date_from=DATE_FROM,
        date_to=DATE_TO,
        include_rows=True,
        source_cohort_filter="all",
    )
    audit = payload.get("export_audit") or {}
    assert audit.get("source_row_count") is not None
    assert audit.get("source_row_count") >= 0
    assert audit.get("technical_status")
    assert audit.get("scientific_status")
    assert audit.get("actual_files")
    assert len(audit["actual_files"]) > 0
    json.dumps(payload)


def test_global_analysis_packs_audit_four_modules(monkeypatch):
    _patch_draw_credibility(monkeypatch)
    db = _balance_audit_db()
    payload = build_modules_analysis_packs_audit(
        db,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        include_rows=False,
        source_cohort_filter="all",
    )
    modules = payload.get("modules") or []
    assert len(modules) == 4
    keys = {m.get("module_key") for m in modules}
    assert keys == {
        "purchasability",
        "balance-v5",
        "goal-intensity-v5",
        "signals",
    }
    balance = next(m for m in modules if m.get("module_key") == "balance-v5")
    assert balance.get("status") != "failed"
    audit = balance.get("export_audit") or {}
    assert audit.get("technical_status")
    assert audit.get("scientific_status")
    json.dumps(payload)


def test_global_audit_fail_soft_isolates_balance_failure(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    def _raise_balance(*a, **k):
        raise RuntimeError("simulated_balance_builder_failure")

    def _ok_purch(*a, **k):
        return (
            {"health.json": b"{}", "summary.json": b"{}", "warnings.json": b"{}"},
            {
                "module_version": "v",
                "versions": {},
                "source_cohorts": [],
                "warnings": [],
                "completeness": "empty",
                "blocking_reasons": [],
                "include_rows_effective": False,
                "primary_rows": 0,
                "source_total_rows": 0,
                "exported_total_rows": 0,
                "truncated": False,
            },
        )

    monkeypatch.setattr(mon, "_build_balance_files", _raise_balance)
    monkeypatch.setattr(mon, "_build_purchasability_files", _ok_purch)
    monkeypatch.setattr(
        mon,
        "_build_goal_files",
        lambda *a, **k: (
            {"preview_summary.json": b"{}", "health.json": b"{}", "summary.json": b"{}"},
            {
                "module_version": None,
                "versions": {},
                "source_cohorts": [],
                "warnings": ["bundle missing"],
                "completeness": "empty",
                "blocking_reasons": ["bundle_missing"],
                "include_rows_effective": False,
                "primary_rows": 0,
                "source_total_rows": 0,
                "exported_total_rows": 0,
                "truncated": False,
                "completed_count": 0,
            },
        ),
    )
    monkeypatch.setattr(
        mon,
        "_build_signals_files",
        lambda *a, **k: (
            {"activations_all_models.csv": b"\xef\xbb\xbfid\n"},
            {
                "module_version": "signals",
                "versions": {},
                "source_cohorts": [],
                "warnings": [],
                "completeness": "empty",
                "blocking_reasons": [],
                "include_rows_effective": False,
                "primary_rows": 0,
                "source_total_rows": 0,
                "exported_total_rows": 0,
                "truncated": False,
                "all_models_exported": True,
            },
        ),
    )

    payload = build_modules_analysis_packs_audit(
        MagicMock(),
        date_from=DATE_FROM,
        date_to=DATE_TO,
        include_rows=False,
    )
    modules = payload.get("modules") or []
    assert len(modules) == 4
    balance = next(m for m in modules if m.get("module_key") == "balance-v5")
    assert balance.get("status") == "failed"
    assert balance.get("error_code") == "module_audit_failed"
    assert balance.get("error_type") == "RuntimeError"
    purch = next(m for m in modules if m.get("module_key") == "purchasability")
    assert purch.get("status") != "failed"


def test_balance_module_analysis_pack_audit_propagates_builder_error(monkeypatch):
    """Il test dedicato Balance deve ancora fallire se il builder è rotto."""
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "_build_balance_files",
        lambda *a, **k: (_ for _ in ()).throw(NameError("build_balance_monitoring_rows")),
    )
    with pytest.raises(NameError):
        build_module_analysis_pack_audit(
            MagicMock(),
            module_key="balance-v5",
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )


def test_analysis_packs_audit_endpoint_http_200(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    db = _balance_audit_db()
    _patch_draw_credibility(monkeypatch)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/cecchino/module-monitoring/analysis-packs-audit",
            params={
                "date_from": DATE_FROM.isoformat(),
                "date_to": DATE_TO.isoformat(),
                "source_cohort": "all",
                "include_rows": "false",
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload.get("modules") or []) == 4
        raw = json.dumps(payload)
        assert "Traceback" not in raw
        assert "NaN" not in raw
        decoded = json.loads(raw)

        def _no_nan(obj):
            if isinstance(obj, float) and math.isnan(obj):
                raise AssertionError("NaN in response")
            if isinstance(obj, dict):
                for v in obj.values():
                    _no_nan(v)
            elif isinstance(obj, list):
                for v in obj:
                    _no_nan(v)

        _no_nan(decoded)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_balance_single_module_audit_endpoint_http_200(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    db = _balance_audit_db()
    _patch_draw_credibility(monkeypatch)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/cecchino/module-monitoring/balance-v5/analysis-pack-audit",
            params={
                "date_from": DATE_FROM.isoformat(),
                "date_to": DATE_TO.isoformat(),
                "include_rows": "false",
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload.get("module_key") == "balance-v5"
        audit = payload.get("export_audit") or {}
        assert audit.get("technical_status")
        assert audit.get("scientific_status")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_module_audit_cache_miss_then_hit(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    calls = {"n": 0}
    real = mon.build_module_analysis_pack_audit

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mon, "build_module_analysis_pack_audit", _counting)
    _patch_draw_credibility(monkeypatch)
    db = _balance_audit_db()

    first = build_modules_analysis_packs_audit(
        db,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        include_rows=False,
        source_cohort_filter="all",
    )
    n_after_miss = calls["n"]
    assert n_after_miss == 4
    assert len(first.get("modules") or []) == 4

    second = build_modules_analysis_packs_audit(
        db,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        include_rows=False,
        source_cohort_filter="all",
    )
    assert calls["n"] == n_after_miss
    assert len(second.get("modules") or []) == 4
    assert second.get("export_version") == first.get("export_version")


def test_module_audit_cache_miss_on_different_filter(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    calls = {"n": 0}

    def _counting(*a, **k):
        calls["n"] += 1
        return {
            "module_key": k.get("module_key") or "purchasability",
            "status": "pass",
            "export_audit": {"technical_status": "pass", "scientific_status": "partial"},
        }

    monkeypatch.setattr(mon, "build_module_analysis_pack_audit", _counting)
    db = MagicMock()

    build_modules_analysis_packs_audit(
        db, date_from=DATE_FROM, date_to=DATE_TO, include_rows=False, source_cohort_filter="all"
    )
    assert calls["n"] == 4
    build_modules_analysis_packs_audit(
        db,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        include_rows=False,
        source_cohort_filter="prospective_persisted",
    )
    assert calls["n"] == 8


def test_module_audit_cache_invalidated_by_export_version(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    calls = {"n": 0}

    def _ok(*a, **k):
        calls["n"] += 1
        return {
            "module_key": k.get("module_key", "purchasability"),
            "status": "pass",
            "export_audit": {"technical_status": "pass"},
        }

    monkeypatch.setattr(mon, "build_module_analysis_pack_audit", _ok)
    db = MagicMock()
    build_modules_analysis_packs_audit(
        db, date_from=DATE_FROM, date_to=DATE_TO, include_rows=False
    )
    assert calls["n"] == 4
    monkeypatch.setattr(
        mon, "MONITORING_EXPORT_VERSION", "cecchino_module_monitoring_exports_v5_test"
    )
    build_modules_analysis_packs_audit(
        db, date_from=DATE_FROM, date_to=DATE_TO, include_rows=False
    )
    assert calls["n"] == 8


def test_module_audit_errors_not_cached(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    calls = {"n": 0}

    def _fail(*a, **k):
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(mon, "build_module_analysis_pack_audit", _fail)
    db = MagicMock()
    first = build_modules_analysis_packs_audit(
        db, date_from=DATE_FROM, date_to=DATE_TO, include_rows=False
    )
    assert calls["n"] == 4
    assert all(m.get("status") == "failed" for m in first["modules"])
    second = build_modules_analysis_packs_audit(
        db, date_from=DATE_FROM, date_to=DATE_TO, include_rows=False
    )
    assert calls["n"] == 8
    assert len(second["modules"]) == 4
