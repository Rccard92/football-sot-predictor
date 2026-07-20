"""Test forensic v4 — coorti export, schema, signals split, scientific audit."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from unittest.mock import MagicMock

from app.services.cecchino.cecchino_balance_v5_monitoring import BALANCE_ROW_FIELDS
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    _PURCHASABILITY_ROW_FIELDS,
    _SIGNALS_ROW_FIELDS,
    _build_export_audit,
    build_module_analysis_pack_zip,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    analysis_query_flags,
    parse_export_cohort_filter,
)


def test_export_version_is_v4():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v5"


def test_purchasability_schema_is_forensic_complete():
    assert "result_home_ht" in _PURCHASABILITY_ROW_FIELDS
    assert "promotion_eligible" in _PURCHASABILITY_ROW_FIELDS
    assert "created_at" in _PURCHASABILITY_ROW_FIELDS
    assert len(_PURCHASABILITY_ROW_FIELDS) >= 40


def test_balance_outcome_columns_present():
    for col in (
        "ht_home",
        "ht_away",
        "outcome_1x2",
        "result_available",
        "dominance_selection_hit",
    ):
        assert col in BALANCE_ROW_FIELDS


def test_signals_schema_includes_activation_timestamp():
    assert "activation_timestamp" in _SIGNALS_ROW_FIELDS
    assert "weights_version" in _SIGNALS_ROW_FIELDS
    assert "result_home_ft" in _SIGNALS_ROW_FIELDS


def test_cohort_filter_all_disables_promotion_only():
    flags = analysis_query_flags(parse_export_cohort_filter("all"))
    assert flags["promotion_eligible_only"] is False
    assert flags["source_cohorts"] is None


def test_cohort_filter_prospective_is_promotion_only():
    flags = analysis_query_flags(parse_export_cohort_filter("prospective"))
    assert flags["promotion_eligible_only"] is True


def test_export_audit_scientific_statuses(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "_build_goal_files",
        lambda *a, **k: (
            {
                "preview_snapshots.csv": b"\xef\xbb\xbfid\n",
                "preview_completed_results.csv": b"\xef\xbb\xbfid\n",
                "preview_summary.json": b"{}",
                "preview_candidate_monitoring.csv": b"\xef\xbb\xbfsection\n",
                "preview_calibration.json": b"{}",
                "preview_bundle_definition.json": b"{}",
                "prospective_progress.json": b"{}",
                "data_health.json": b"{}",
                "historical_availability.json": b'{"completed_count":0}',
                "health.json": b"{}",
                "summary.json": b"{}",
                "warnings.json": b'{"warnings":[]}',
            },
            {
                "versions": {},
                "source_cohorts": ["prospective_frozen_bundle"],
                "primary_rows": 0,
                "completeness": "empty",
                "blocking_reasons": [],
                "warnings": [],
                "include_rows_effective": True,
                "module_version": "v",
                "source_total_rows": 0,
                "exported_total_rows": 0,
                "truncated": False,
                "completed_count": 0,
            },
        ),
    )
    data, _ = build_module_analysis_pack_zip(
        MagicMock(),
        module_key="goal-intensity-v5",
        date_from=date(2026, 6, 19),
        date_to=date(2026, 7, 20),
        source_cohort_filter="all",
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert "historical_availability.json" in zf.namelist()
        audit = json.loads(zf.read("export_audit.json"))
        assert "technical_status" in audit
        assert "scientific_status" in audit


def test_purchasability_partial_not_blocked_when_rows(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    files = {
        "rows.csv": mon._csv_bom(
            [{"id": 1, "source_cohort": "historical_reconstructed_verified"}],
            ["id", "source_cohort"],
        ),
        "health.json": b"{}",
        "summary.json": b"{}",
        "warnings.json": b'{"warnings":["Persistenza bloccata"]}',
    }
    schema = {
        "primary_rows_file": "rows.csv",
        "required_columns": ["id", "source_cohort"],
        "required_files": list(files),
    }
    audit = _build_export_audit(
        files,
        {
            "source_total_rows": 1,
            "primary_rows": 1,
            "warnings": ["Persistenza bloccata: only_legacy_derived_available"],
            "blocking_reasons": ["only_legacy_derived_available"],
            "completeness": "partial",
            "settled_count": 1,
        },
        "purchasability",
        list(files),
        schema,
    )
    assert audit["technical_status"] in {"pass", "partial"}
    assert audit["scientific_status"] != "fail"
    assert audit.get("reconciliation", {}).get("exported_rows") == 1
