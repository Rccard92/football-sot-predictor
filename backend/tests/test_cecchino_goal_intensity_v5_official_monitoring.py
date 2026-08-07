"""Readiness / soft overview official vs preview Goal Intensity v5."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
    OFFICIAL_BUNDLE_VERSION,
    OPERATIONAL_STATUS,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import PREVIEW_BUNDLE_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_readiness import (
    build_goal_intensity_v5_readiness,
    clear_goal_intensity_v5_readiness_cache,
)
from app.services.cecchino.cecchino_goal_intensity_v5_readiness_policy import (
    GOAL_INTENSITY_V5_READINESS_VERSION,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    build_goal_intensity_module_overview,
)


def _bundle(*, official: bool, bundle_id: int = 3):
    return SimpleNamespace(
        id=bundle_id,
        version=OFFICIAL_BUNDLE_VERSION if official else PREVIEW_BUNDLE_VERSION,
        status="active",
        is_active=True,
        candidate_definition_hash="hash" + "a" * 60,
        frozen_at=None,
    )


def _empty_scalars():
    m = MagicMock()
    m.all.return_value = []
    m.first.return_value = None
    return m


def _patch_common(db, bundle):
    db.scalars.return_value = _empty_scalars()
    return patch.multiple(
        "app.services.cecchino.cecchino_goal_intensity_v5_readiness",
        get_active_bundle=MagicMock(return_value=bundle),
        build_prospective_monitoring=MagicMock(
            return_value={
                "status": "collecting",
                "phase_2b_readiness": {"blocking_issues": [], "recommended_next_step": None},
            }
        ),
        normalize_goal_v5_monitoring_contract=MagicMock(
            return_value={
                "total_snapshots": 0,
                "completed_snapshots": 0,
                "pending_snapshots": 0,
                "locked_snapshots": 0,
                "incomplete_snapshots": 0,
                "error_snapshots": 0,
                "coverage_global": {},
                "coverage_in_period": {},
            }
        ),
        build_data_health=MagicMock(return_value={"issues": []}),
        build_overview=MagicMock(return_value={"operational_status": OPERATIONAL_STATUS}),
        build_calibration=MagicMock(return_value={}),
        build_candidates=MagicMock(return_value={}),
        _bundle_summary=MagicMock(return_value={"id": bundle.id, "version": bundle.version}),
    )


def test_readiness_version_bumped():
    assert GOAL_INTENSITY_V5_READINESS_VERSION.endswith("_v2")


def test_readiness_preview_keeps_legacy_semantics():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    bundle = _bundle(official=False, bundle_id=11)
    with _patch_common(db, bundle):
        out = build_goal_intensity_v5_readiness(db, date_from=date(2026, 1, 1), date_to=date(2026, 8, 1))
    assert out["operational_status"] == "preview_monitored"
    assert out["current_decision"] == "continue_monitoring"
    assert out["post_cutover_qc_only"] is False
    assert out["phase_2b_benchmark"]["status"] != "not_applicable_official_support"


def test_readiness_official_contract():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    bundle = _bundle(official=True, bundle_id=3)
    with _patch_common(db, bundle):
        with patch(
            "app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark.build_goal_intensity_v4_v5_prospective_benchmark"
        ) as bench:
            out = build_goal_intensity_v5_readiness(
                db, date_from=date(2026, 1, 1), date_to=date(2026, 8, 1)
            )
            bench.assert_not_called()

    assert out["operational_status"] == "official_support"
    assert out["operational_status_label_it"] == "Supporto ufficiale"
    assert out["scientific_evidence"] == "external_validation_completed"
    assert out["scientific_maturity"] == "external_validation_completed"
    assert out["current_decision"] == "support_module_active"
    assert out["recommended_next_step"] == "monitor_post_cutover_quality"
    assert out["signals_integration_status"] == "blocked"
    assert out["signals_integration_status_label_it"] == "Non collegato ai Segnali"
    assert out["role"] == "contextual_support_only"
    assert out["post_cutover_qc_only"] is True
    assert out["no_gate_on_200"] is True
    assert out["phase_2b_benchmark"]["status"] == "not_applicable_official_support"
    assert "Preview" not in (out["operational_status_label_it"] or "")


def test_readiness_official_sample_zero_does_not_regress():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    bundle = _bundle(official=True)
    with _patch_common(db, bundle):
        out = build_goal_intensity_v5_readiness(db)
    assert out["operational_status"] == "official_support"
    assert out["scientific_maturity"] == "external_validation_completed"
    assert out["prospective_progress"]["snapshots"] == 0
    assert out["current_decision"] != "continue_monitoring"


def test_readiness_official_sample_below_200_does_not_regress():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    bundle = _bundle(official=True)
    with _patch_common(db, bundle):
        with patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.normalize_goal_v5_monitoring_contract",
            return_value={
                "total_snapshots": 50,
                "completed_snapshots": 40,
                "pending_snapshots": 10,
                "locked_snapshots": 0,
                "incomplete_snapshots": 0,
                "error_snapshots": 0,
                "coverage_global": {},
                "coverage_in_period": {},
            },
        ):
            out = build_goal_intensity_v5_readiness(db)
    assert out["operational_status"] == "official_support"
    assert out["prospective_progress"]["completed"] == 40
    assert out["scientific_maturity"] != "preview_research"
    assert out["scientific_maturity"] != "insufficient_completed_sample"


def test_readiness_official_sample_ge_200_stays_official():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    bundle = _bundle(official=True)
    with _patch_common(db, bundle):
        with patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_readiness.normalize_goal_v5_monitoring_contract",
            return_value={
                "total_snapshots": 250,
                "completed_snapshots": 210,
                "pending_snapshots": 40,
                "locked_snapshots": 0,
                "incomplete_snapshots": 0,
                "error_snapshots": 0,
                "coverage_global": {},
                "coverage_in_period": {},
            },
        ):
            with patch(
                "app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark.build_goal_intensity_v4_v5_prospective_benchmark"
            ) as bench:
                out = build_goal_intensity_v5_readiness(db)
                bench.assert_not_called()
    assert out["operational_status"] == "official_support"
    assert out["phase_2b_benchmark"]["status"] == "not_applicable_official_support"


def test_readiness_cache_includes_bundle_identity():
    clear_goal_intensity_v5_readiness_cache()
    db = MagicMock()
    preview = _bundle(official=False, bundle_id=11)
    official = _bundle(official=True, bundle_id=3)

    with _patch_common(db, preview):
        a = build_goal_intensity_v5_readiness(db, date_from=date(2026, 1, 1), date_to=date(2026, 2, 1))
    assert a["operational_status"] == "preview_monitored"

    with _patch_common(db, official):
        b = build_goal_intensity_v5_readiness(db, date_from=date(2026, 1, 1), date_to=date(2026, 2, 1))
    assert b["operational_status"] == "official_support"
    assert b.get("cache_hit") is not True


def test_soft_overview_official_not_preview_research():
    db = MagicMock()
    official = _bundle(official=True, bundle_id=3)
    db.scalars.return_value = _empty_scalars()
    with patch(
        "app.services.cecchino.cecchino_module_monitoring_exports._active_goal_bundle",
        return_value=official,
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports._eligible_fixture_counts",
        return_value=(5, 2),
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_prospective_monitoring",
        return_value={"status": "ok", "phase_2b_readiness": {}},
    ):
        out = build_goal_intensity_module_overview(
            db, date_from=date(2026, 8, 1), date_to=date(2026, 8, 7)
        )
    assert out["status"] == "official_support"
    assert out["current_decision"] == "support_module_active"
    assert out["scientific_maturity"] == "external_validation_completed"
    assert "Preview research" not in " ".join(out.get("warnings") or [])
    assert out["minimum_sample"] is None
    assert out["no_gate_on_200"] is True


def test_soft_overview_preview_unchanged():
    db = MagicMock()
    preview = _bundle(official=False, bundle_id=11)
    db.scalars.return_value = _empty_scalars()
    with patch(
        "app.services.cecchino.cecchino_module_monitoring_exports._active_goal_bundle",
        return_value=preview,
    ), patch(
        "app.services.cecchino.cecchino_module_monitoring_exports._eligible_fixture_counts",
        return_value=(5, 2),
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_prospective_monitoring",
        return_value={
            "status": "collecting",
            "phase_2b_readiness": {"blocking_issues": [], "recommended_next_step": None},
        },
    ):
        out = build_goal_intensity_module_overview(
            db, date_from=date(2026, 1, 1), date_to=date(2026, 8, 1)
        )
    assert out["status"] == "preview_research"
    assert out["current_decision"] == "continue_monitoring"
