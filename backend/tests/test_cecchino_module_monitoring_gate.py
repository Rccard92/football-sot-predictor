"""Gate Fase 1/3 — coorti, backfill token, export v3 audit."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino.cecchino_balance_v5_monitoring import (
    resolve_balance_v5_monitoring_snapshot,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    build_module_analysis_pack_zip,
)
from app.services.cecchino.cecchino_module_monitoring_historical_backfill import (
    MODULE_HISTORICAL_BACKFILL_CONFIRM_TOKEN,
    run_module_historical_backfill,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
    normalize_cohort,
)


def test_export_version_is_v3():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v3"


def test_cohort_aliases_normalize():
    assert normalize_cohort("legacy_persisted_backfill") == "historical_persisted_verified"
    assert normalize_cohort("legacy_derived_diagnostic") == "historical_diagnostic"
    assert normalize_cohort("prospective_persisted") == "prospective_persisted"


def test_legacy_balance_v5_never_prospective(monkeypatch):
    from app.services.cecchino import cecchino_balance_v5_monitoring as mon

    monkeypatch.setattr(mon, "_odds_meta_verified_pre_kickoff", lambda row: False)
    row = SimpleNamespace(
        cecchino_output_json={
            "balance_v5": {
                "status": "ok",
                "inputs": {"prob_1_norm": 1},
                "pillars": {
                    "f36": {"index": 1},
                    "dominance": {},
                    "draw_credibility": {},
                    "gap_coherence": {},
                },
            }
        },
        kpi_panel_json={},
        odds_snapshot_json={},
        scan_date=date(2026, 6, 20),
        kickoff=None,
    )
    resolved = resolve_balance_v5_monitoring_snapshot(row)
    assert resolved["source_cohort"] != "prospective_persisted"
    assert resolved["source_cohort"] == COHORT_HISTORICAL_DIAGNOSTIC


def test_backfill_requires_confirm_token():
    with pytest.raises(ValueError):
        run_module_historical_backfill(
            MagicMock(),
            module_keys=["balance-v5"],
            date_from=date(2026, 6, 19),
            date_to=date(2026, 6, 20),
            confirm="WRONG",
        )


def test_zip_contains_forensic_files(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "_build_balance_files",
        lambda *a, **k: (
            {
                "balance_rows.csv": b"\xef\xbb\xbftoday_fixture_id\n",
                "health.json": b"{}",
                "summary.json": b"{}",
                "warnings.json": b'{"warnings":[]}',
                "f36_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
                "dominance_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
                "draw_credibility_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
                "gap_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
                "monthly_timeseries.csv": b"\xef\xbb\xbfmonth\n",
                "snapshot_health.json": b"{}",
                "source_cohort_distribution.json": b"{}",
                "version_definition.json": b"{}",
                "draw_credibility_research.json": b"{}",
            },
            {
                "versions": {"balance": "v"},
                "source_cohorts": {COHORT_HISTORICAL_DIAGNOSTIC: 0},
                "primary_rows": 0,
                "completeness": "empty",
                "blocking_reasons": [],
                "warnings": [],
                "include_rows_effective": True,
                "module_version": "v",
                "source_total_rows": 0,
                "exported_total_rows": 0,
                "truncated": False,
            },
        ),
    )
    data, _ = build_module_analysis_pack_zip(
        MagicMock(),
        module_key="balance-v5",
        date_from=date(2026, 6, 19),
        date_to=date(2026, 6, 20),
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "schema_contract.json" in names or "export_audit.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert "v3" in str(manifest.get("export_version") or manifest.get("schema_version") or "")
        assert "secret" not in json.dumps(manifest).lower()


def test_confirm_token_constant():
    assert MODULE_HISTORICAL_BACKFILL_CONFIRM_TOKEN == "IMPORT_CECCHINO_HISTORICAL_MONITORING"


def test_reconstructed_cohort_when_verified(monkeypatch):
    from app.services.cecchino import cecchino_balance_v5_monitoring as mon

    monkeypatch.setattr(mon, "_odds_meta_verified_pre_kickoff", lambda row: True)
    monkeypatch.setattr(
        mon,
        "build_cecchino_balance_v5",
        lambda **kw: {
            "status": "ok",
            "version": "cecchino_balance_v5_v2",
            "inputs": {"prob_1_norm": 40, "prob_x_norm": 30, "prob_2_norm": 30},
            "pillars": {
                "f36": {"index": 1, "class_label": "A"},
                "dominance": {"index": 1, "class_label": "B", "direction": "1"},
                "draw_credibility": {"index": 1, "class_label": "C"},
                "gap_coherence": {"index": 1, "class_label": "D"},
            },
            "warnings": [],
        },
    )
    row = SimpleNamespace(
        cecchino_output_json={"final": {"quota_1": 2.0}},
        kpi_panel_json={},
        odds_snapshot_json={},
        scan_date=date(2026, 6, 20),
        kickoff=None,
    )
    resolved = resolve_balance_v5_monitoring_snapshot(row)
    assert resolved["source_cohort"] == COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED
