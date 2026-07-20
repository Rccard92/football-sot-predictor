"""Test forensic v5 — stabilizzazione export monitoraggio moduli."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.cecchino_purchasability_evaluation import (
    EVAL_LOST,
    EVAL_PENDING,
    EVAL_WON,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    BALANCE_ROW_FIELDS,
    compact_balance_v5_monitoring_snapshot,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    _PURCHASABILITY_ROW_FIELDS,
    _SIGNALS_ROW_FIELDS,
    _build_export_audit,
    _count_csv_rows,
    _goal_effective_date_range,
    _is_verified_pre_match,
    build_module_analysis_pack_zip,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    analysis_query_flags,
    parse_export_cohort_filter,
)
from app.services.cecchino.cecchino_purchasability_validation import (
    _source_mode_for_cohort,
)
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    _analysis_settled_rows,
    _settled_rows,
)
from app.services.cecchino.cecchino_signal_aggregation import _activation_source_cohort


def _eval(**kwargs):
    defaults = dict(
        evaluation_status=EVAL_WON,
        quota_book=Decimal("2.10"),
        snapshot_timestamp_verified=True,
        snapshot_before_kickoff=True,
        promotion_eligible=False,
        purchasability_score=50,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_export_version_is_v5():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v6"


def test_analysis_settled_ignores_promotion_gate():
    rows = [
        _eval(promotion_eligible=False, evaluation_status=EVAL_WON),
        _eval(promotion_eligible=False, evaluation_status=EVAL_LOST),
        _eval(promotion_eligible=False, evaluation_status=EVAL_PENDING),
    ]
    assert len(_analysis_settled_rows(rows)) == 2
    assert len(_settled_rows(rows, require_promotion_eligible=True)) == 0


def test_source_mode_mapping():
    assert _source_mode_for_cohort("historical_reconstructed_verified") == (
        "historical_reconstruction"
    )
    assert _source_mode_for_cohort("prospective_persisted") == "prospective_scan"


def test_balance_snapshot_timestamp_not_generated_at():
    snap = compact_balance_v5_monitoring_snapshot(
        {
            "status": "ok",
            "version": "balance_v5",
            "pillars": {
                "f36": {"index": 1},
                "dominance": {"index": 1},
                "draw_credibility": {"index": 1},
                "gap_coherence": {"index": 1},
            },
            "inputs": {"prob_1_norm": 0.4, "prob_x_norm": 0.3, "prob_2_norm": 0.3},
        },
        scan_date=date(2026, 6, 1),
        kickoff=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc),
        snapshot_timestamp="2026-06-01T10:00:00+00:00",
        generated_at="2026-07-20T10:00:00+00:00",
    )
    assert snap["snapshot_timestamp"] == "2026-06-01T10:00:00+00:00"
    assert snap.get("generated_at") == "2026-07-20T10:00:00+00:00"
    assert snap["snapshot_timestamp"] != snap.get("generated_at")


def test_goal_csv_empty_header_only_not_counted():
    content = (
        "\ufeffid,scan_date\n".encode("utf-8")
    )
    assert _count_csv_rows(content) == 0


def test_goal_effective_date_range_from_exported_rows():
    content = "\ufeffscan_date\n2026-06-19\n2026-07-10\n".encode("utf-8")
    assert _goal_effective_date_range(content) == {
        "from": "2026-06-19",
        "to": "2026-07-10",
    }


def test_signals_source_cohort_pre_match():
    cohort = _activation_source_cohort(
        "2026-06-01T10:00:00+00:00",
        "2026-06-01T18:00:00+00:00",
    )
    assert cohort == "historical_persisted_verified"


def test_signals_schema_includes_selection_source():
    assert "selection_source" in _SIGNALS_ROW_FIELDS
    assert "source_cohort" in _SIGNALS_ROW_FIELDS


def test_purchasability_schema_includes_source_mode():
    assert "source_mode" in _PURCHASABILITY_ROW_FIELDS


def test_export_audit_purchasability_partial_with_historical_rows():
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    files = {
        "rows.csv": mon._csv_bom(
            [{"id": 1, "source_cohort": "historical_reconstructed_verified", "evaluation_status": "won"}],
            ["id", "source_cohort", "evaluation_status"],
        ),
    }
    schema = {
        "primary_rows_file": "rows.csv",
        "required_columns": ["id", "source_cohort", "evaluation_status"],
        "required_files": list(files),
    }
    audit = _build_export_audit(
        files,
        {
            "source_total_rows": 1,
            "primary_rows": 1,
            "warnings": ["Persistenza bloccata"],
            "blocking_reasons": ["only_legacy_derived_available"],
            "completeness": "partial",
            "settled_count": 1,
        },
        "purchasability",
        list(files),
        schema,
    )
    assert audit["scientific_status"] == "partial"
    assert audit["technical_status"] in {"pass", "partial"}


def test_export_audit_goal_partial_collecting():
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    files = {
        "preview_snapshots.csv": b"\xef\xbb\xbfid,scan_date\n1,2026-06-19\n",
        "preview_completed_results.csv": b"\xef\xbb\xbfid\n",
    }
    schema = {
        "primary_rows_file": "preview_snapshots.csv",
        "required_columns": ["id", "scan_date"],
        "required_files": list(files.keys()),
    }
    audit = _build_export_audit(
        files,
        {
            "source_total_rows": 1,
            "primary_rows": 1,
            "completeness": "partial",
            "blocking_reasons": [],
            "warnings": [],
            "completed_count": 0,
        },
        "goal-intensity-v5",
        list(files),
        schema,
    )
    assert audit["scientific_status"] == "partial_collecting"


def test_goal_stream_preview_export_filters_scan_date(monkeypatch):
    from app.services.cecchino import cecchino_goal_intensity_v5_preview as preview

    bundle = SimpleNamespace(id=1, version="test_bundle", calibration_payload={})
    snap_in = SimpleNamespace(
        scan_date=date(2026, 6, 19),
        result_attached_at=None,
        kickoff=None,
        id=1,
    )
    snap_out = SimpleNamespace(
        scan_date=date(2026, 7, 21),
        result_attached_at=None,
        kickoff=None,
        id=2,
    )

    monkeypatch.setattr(preview, "get_active_bundle", lambda db: bundle)
    monkeypatch.setattr(
        preview,
        "_snapshot_list_item",
        lambda s, b: {"id": s.id, "scan_date": s.scan_date.isoformat()},
    )

    db = MagicMock()
    db.scalars.return_value.all.return_value = [snap_in, snap_out]

    raw = "".join(
        preview.stream_preview_export(
            db,
            kind="preview_snapshots",
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 20),
        )
    )
    rows = list(csv.DictReader(io.StringIO(raw.lstrip("\ufeff"))))
    assert len(rows) == 1
    assert rows[0]["scan_date"] == "2026-06-19"
