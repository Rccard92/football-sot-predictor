"""Test consolidamento Goal Intensity v5 — facade, Today alias, readiness, export v10."""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_goal_intensity_v5 import (
    BUNDLE_VERSION,
    MINIMUM_PROSPECTIVE_MATCHES,
    attach_results_for_rows,
    build_today_payload,
)
from app.services.cecchino.cecchino_goal_intensity_v5_readiness import (
    build_goal_intensity_v5_dossier_files,
    build_goal_intensity_v5_readiness,
    clear_goal_intensity_v5_readiness_cache,
)
from app.services.cecchino.cecchino_goal_intensity_v5_readiness_policy import (
    GOAL_INTENSITY_V5_EXPORT_VERSION,
    GOAL_INTENSITY_V5_MONITORING_VERSION,
    GOAL_INTENSITY_V5_READINESS_POLICY_VERSION,
    GOAL_INTENSITY_V5_READINESS_VERSION,
    MIN_PROSPECTIVE_COMPLETED,
    build_goal_intensity_v5_readiness_policy_payload,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    SCHEMA_CONTRACTS,
)


def test_export_version_is_v11():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v11"
    assert "v11" in MONITORING_EXPORT_VERSION


def test_goal_schema_contract_includes_canonical_files():
    required = SCHEMA_CONTRACTS["goal-intensity-v5"]["required_files"]
    for name in (
        "goal_overview.json",
        "goal_readiness.json",
        "goal_readiness_policy.json",
        "goal_prospective_progress.json",
        "goal_dimensions_summary.json",
        "goal_candidates_summary.json",
        "goal_versions.json",
    ):
        assert name in required


def test_policy_immutable_and_aligned_to_preview():
    policy = build_goal_intensity_v5_readiness_policy_payload()
    assert policy["immutable"] is True
    assert policy["MINIMUM_PROSPECTIVE_MATCHES"] == MINIMUM_PROSPECTIVE_MATCHES == 200
    assert MIN_PROSPECTIVE_COMPLETED == 200
    assert policy["signals_integration_default"] == "blocked"
    assert policy["default_decision"] == "continue_monitoring"
    assert policy["version"] == GOAL_INTENSITY_V5_READINESS_POLICY_VERSION
    assert GOAL_INTENSITY_V5_MONITORING_VERSION.endswith("_v1")
    assert GOAL_INTENSITY_V5_READINESS_VERSION.endswith("_v1")
    assert GOAL_INTENSITY_V5_EXPORT_VERSION.endswith("_v1")


def test_build_today_payload_unavailable_when_bundle_missing():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.get_preview_detail",
        return_value={"status": "error", "error": "bundle_missing"},
    ):
        payload = build_today_payload(db, 42)
    assert payload["status"] == "unavailable"
    assert payload["operational_status"] == "preview_monitored"
    assert payload["signals_integration_status"] == "blocked"
    assert payload["version"] == BUNDLE_VERSION
    assert payload["no_betting_signals"] is True


def test_attach_results_for_rows_fail_soft_no_commit_when_empty():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.get_active_bundle",
        return_value=None,
    ):
        out = attach_results_for_rows(db, [], commit=False)
    assert out["status"] == "skipped"
    assert out["attached"] == 0
    db.commit.assert_not_called()


def test_readiness_zero_snapshots_prospective_not_started():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.get_active_bundle",
            return_value=None,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_prospective_monitoring",
            return_value={"phase_2b_readiness": {"blocking_issues": []}, "bundle": {}},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_data_health",
            return_value={"issues": []},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_overview",
            return_value={"status": "ok"},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_calibration",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_candidates",
            return_value={},
        ),
    ):
        report = build_goal_intensity_v5_readiness(db)

    assert report["signals_integration_status"] == "blocked"
    assert report["current_decision"] == "continue_monitoring"
    assert report["operational_status"] == "preview_monitored"
    assert report["scientific_maturity"] == "prospective_not_started"
    assert report["prospective_progress"]["earliest_theoretical_review_at"] is None
    assert report["prospective_progress"]["completed"] == 0


def _snap(status: str, attached: bool = False):
    s = MagicMock()
    s.snapshot_status = status
    s.scan_date = date(2026, 1, 10)
    s.competition_id = 1
    s.result_attached_at = (
        datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc) if attached else None
    )
    s.no_target_used_in_score = True
    return s


def test_readiness_199_insufficient_sample():
    clear_goal_intensity_v5_readiness_cache()
    from app.models.cecchino_goal_intensity_v5_preview import SNAPSHOT_COMPLETED

    bundle = MagicMock()
    bundle.id = 1
    bundle.candidate_definition_hash = "abc"
    snaps = [_snap(SNAPSHOT_COMPLETED, attached=True) for _ in range(199)]

    db = MagicMock()

    def _scalars(stmt):  # noqa: ARG001
        result = MagicMock()
        result.all.return_value = snaps
        return result

    db.scalars.side_effect = _scalars

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.get_active_bundle",
            return_value=bundle,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_prospective_monitoring",
            return_value={"phase_2b_readiness": {"blocking_issues": []}, "bundle": {"pending": 0}},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_data_health",
            return_value={"issues": []},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_overview",
            return_value={"status": "ok"},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_calibration",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_candidates",
            return_value={},
        ),
    ):
        report = build_goal_intensity_v5_readiness(db)

    assert report["prospective_progress"]["completed"] == 199
    assert report["scientific_maturity"] == "insufficient_completed_sample"
    assert report["signals_integration_status"] == "blocked"
    assert report["current_decision"] == "continue_monitoring"
    assert report["manual_review_status"] == "not_eligible"


def test_readiness_200_ready_for_manual_review():
    clear_goal_intensity_v5_readiness_cache()
    from app.models.cecchino_goal_intensity_v5_preview import SNAPSHOT_COMPLETED

    bundle = MagicMock()
    bundle.id = 1
    bundle.candidate_definition_hash = "abc"
    snaps = [_snap(SNAPSHOT_COMPLETED, attached=True) for _ in range(200)]

    db = MagicMock()

    def _scalars(stmt):  # noqa: ARG001
        result = MagicMock()
        result.all.return_value = snaps
        return result

    db.scalars.side_effect = _scalars

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.get_active_bundle",
            return_value=bundle,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_prospective_monitoring",
            return_value={"phase_2b_readiness": {"blocking_issues": []}, "bundle": {"pending": 0}},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_data_health",
            return_value={"issues": []},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_overview",
            return_value={"status": "ok"},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_calibration",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_candidates",
            return_value={},
        ),
    ):
        report = build_goal_intensity_v5_readiness(db)

    assert report["prospective_progress"]["completed"] == 200
    assert report["scientific_maturity"] == "ready_for_manual_review"
    assert report["signals_integration_status"] == "blocked"
    assert report["current_decision"] == "continue_monitoring"
    assert report["manual_review_status"] == "eligible"


def test_dossier_zip_serializes_with_jsonable_encoder():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    fake_readiness = {
        "status": "ok",
        "filters": {"date_from": date(2026, 1, 1), "date_to": date(2026, 7, 20)},
        "overview_summary": {"status": "ok"},
        "prospective_progress": {"completed": 0},
        "scientific": {"candidates": {}, "calibration": {}, "blocking_issues": []},
        "data_health": {"issues": []},
    }

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_readiness.build_goal_intensity_v5_readiness",
        return_value=fake_readiness,
    ):
        files = build_goal_intensity_v5_dossier_files(
            db, date_from=date(2026, 1, 1), date_to=date(2026, 7, 20)
        )

    assert "goal_readiness.json" in files
    assert "goal_readiness_policy.json" in files
    assert "README.md" in files
    # Round-trip ZIP without date serialization errors
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        assert "goal_readiness.json" in names
        raw = zf.read("goal_readiness.json").decode("utf-8")
        assert "2026-01-01" in raw
