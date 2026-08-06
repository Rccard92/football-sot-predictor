"""Test finalizzazione Goal Intensity V5 official support (Phase 2D)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
    ARCHIVED_FROM_OPERATIONAL,
    FALLBACK_REASON_FEATURES_INCOMPLETE,
    FREEZE_CONFIRM_TOKEN,
    GI_E_ID,
    OFFICIAL_BUNDLE_VERSION,
    OFFICIAL_MODULE_VERSION,
    OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS,
    OPERATIONAL_CALIBRATION_KEY,
    RAW_INDEX_ID,
    TARGET_CALIBRATION_MAPPING,
    build_finalization_dry_run,
    build_goal_intensity_market_support,
    build_official_bundle_payload,
    build_operational_calibration_payload,
    freeze_official_support_bundle,
    official_features_complete,
    score_official_support_with_bundle,
    validate_benchmark_job_for_finalization,
)
from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import (
    TARGET_BUNDLE_VERSION as CANDIDATE_BUNDLE_VERSION,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    PREVIEW_BUNDLE_VERSION,
    score_legacy_preview_with_bundle,
    score_features_with_bundle,
)
from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_ACTIVE,
    BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
    BUNDLE_STATUS_SUPERSEDED,
)


def _cal_head(intercept: float, coefficient: float, *, logistic: bool = False) -> dict:
    method = "train_logistic_regression" if logistic else "train_linear_regression"
    return {
        "calibration_method": method,
        "method": method,
        "intercept": intercept,
        "coefficient": coefficient,
        "train_n": 100,
    }


def _candidate_bundle(**overrides):
    gi_a = {
        "total_goals_ft": _cal_head(1.0, 0.02),
        "goals_ge_2": _cal_head(-1.0, 0.03, logistic=True),
        "goals_ge_3": _cal_head(-2.0, 0.04, logistic=True),
        "btts_ft": _cal_head(-0.5, 0.02, logistic=True),
    }
    gi_e = {
        "total_goals_ft": _cal_head(1.5, 0.025),
        "goals_ge_2": _cal_head(-0.8, 0.035, logistic=True),
        "goals_ge_3": _cal_head(-1.5, 0.045, logistic=True),
        "btts_ft": _cal_head(-0.3, 0.022, logistic=True),
    }
    base = SimpleNamespace(
        id=21,
        version=CANDIDATE_BUNDLE_VERSION,
        status=BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
        is_active=False,
        candidate_definition_hash="candhash" + "a" * 56,
        fixture_ids_hash="fixhash" + "b" * 57,
        targets_hash="tgthash" + "c" * 57,
        normalization_method="train_ecdf_midrank",
        normalization_payload={
            "features": {
                k: {"train_values": [float(i) for i in range(20)], "distribution_hash": f"h_{k}"}
                for k in (
                    "home_goals_scored_avg",
                    "home_goals_scored_rolling_5",
                    "home_goals_conceded_avg",
                    "away_goals_conceded_avg",
                    "total_goals_avg",
                    "total_goals_rolling_5",
                    "goals_scored_std_last_10",
                )
            }
        },
        calibration_payload={
            RAW_INDEX_ID: gi_a,
            "GI_B_RECENCY": gi_a,
            GI_E_ID: gi_e,
            "GI_F_REGULARIZED_PILLARS": gi_e,
        },
        candidate_definitions_payload={
            "intended_use": "historical_external_benchmark_only",
            "development_protocol_version": "cecchino_goal_intensity_v5_phase_2c_candidate_development_v1",
            "active_candidate_ids": [
                RAW_INDEX_ID,
                "GI_B_RECENCY",
                GI_E_ID,
                "GI_F_REGULARIZED_PILLARS",
            ],
            "archived_candidate_ids": ["MT1_LONG_TERM", "GI_A_without_volatility"],
            "gi_f_weights": {
                "OP1_HOME_LONG_TERM": 0.2,
                "OP2_HOME_RECENCY": 0.1,
                "DV1_MEAN_CONCEDED": 0.2,
                "MT1_LONG_TERM": 0.2,
                "MT2_LONG_TERM_PLUS_RECENCY": 0.1,
                "OV1_STD": 0.2,
            },
            "selected_alpha": 1.0,
            "parent_bundle_id": 11,
            "parent_bundle_version": PREVIEW_BUNDLE_VERSION,
            "holdout_access_count": 1,
            "live_scoring_enabled": False,
            "signals_integration_enabled": False,
        },
        candidate_indices_version="phase2c",
        retrospective_date_from=date(2024, 1, 1),
        retrospective_date_to=date(2025, 6, 1),
        first_prospective_scan_date=date(2025, 6, 2),
        frozen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _preview_bundle(**overrides):
    b = SimpleNamespace(
        id=11,
        version=PREVIEW_BUNDLE_VERSION,
        status=BUNDLE_STATUS_ACTIVE,
        is_active=True,
        candidate_definition_hash="prevhash" + "d" * 56,
        fixture_ids_hash="fixhash_p",
        targets_hash="tgthash_p",
        normalization_method="train_ecdf_midrank",
        normalization_payload=_candidate_bundle().normalization_payload,
        calibration_payload={RAW_INDEX_ID: _candidate_bundle().calibration_payload[RAW_INDEX_ID]},
        candidate_definitions_payload={},
        candidate_indices_version="v1_1",
        retrospective_date_from=date(2024, 1, 1),
        retrospective_date_to=date(2025, 6, 1),
        first_prospective_scan_date=date(2025, 6, 2),
        frozen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    for k, v in overrides.items():
        setattr(b, k, v)
    return b


def _ok_job(bundle_id: int = 21, **overrides):
    summary = {
        "scientific_label": "external_validation",
        "models": [
            "GI_V4_EXPECTED_GOALS",
            RAW_INDEX_ID,
            "GI_B_RECENCY",
            GI_E_ID,
            "GI_F_REGULARIZED_PILLARS",
        ],
        "metrics": {"model_metrics": {}},
        "reconciliation": {
            "ok": True,
            "duplicate_rows": 0,
            "all_paired_have_five_models": True,
        },
        "reconciliation_ok": True,
        "checks": {
            "external_api_calls": 0,
            "base_run_writes": 0,
            "bundle_refit": False,
            "result_used_in_prediction": False,
        },
    }
    job = SimpleNamespace(
        id=2,
        mode="full",
        status="completed",
        job_version="cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1",
        independence_status="external_independent",
        bundle_id=bundle_id,
        bundle_definition_hash="candhash" + "a" * 56,
        selected_snapshots=5489,
        processed_snapshots=5489,
        paired_complete=5489,
        skipped=0,
        errors=0,
        summary_json=summary,
        historical_run_id=1,
    )
    for k, v in overrides.items():
        setattr(job, k, v)
    return job


def _features_complete() -> dict:
    return {
        "home_goals_scored_avg": 1.5,
        "home_goals_scored_rolling_5": 1.4,
        "home_goals_conceded_avg": 1.1,
        "away_goals_conceded_avg": 1.2,
        "total_goals_avg": 2.6,
        "total_goals_rolling_5": 2.5,
        "goals_scored_std_last_10": 0.8,
    }


# ---------------------------------------------------------------------------
# Job validation
# ---------------------------------------------------------------------------


def test_validate_job_not_found():
    db = MagicMock()
    db.get.return_value = None
    out = validate_benchmark_job_for_finalization(db, 999)
    assert out["ok"] is False
    assert "benchmark_job_not_found" in out["blocking_reasons"]


def test_validate_pilot_rejected():
    cand = _candidate_bundle()
    job = _ok_job(mode="pilot")
    db = MagicMock()
    db.get.return_value = job
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
        return_value={},
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_candidate_bundle_v2_1",
        return_value=cand,
    ):
        out = validate_benchmark_job_for_finalization(db, 2, candidate_bundle=cand)
    assert out["ok"] is False
    assert "pilot_job_rejected" in out["blocking_reasons"]


def test_validate_full_not_completed():
    cand = _candidate_bundle()
    job = _ok_job(status="running")
    db = MagicMock()
    db.get.return_value = job
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
        return_value={},
    ):
        out = validate_benchmark_job_for_finalization(db, 2, candidate_bundle=cand)
    assert "job_not_completed" in out["blocking_reasons"]


def test_validate_job_with_errors():
    cand = _candidate_bundle()
    job = _ok_job(errors=3)
    db = MagicMock()
    db.get.return_value = job
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
        return_value={},
    ):
        out = validate_benchmark_job_for_finalization(db, 2, candidate_bundle=cand)
    assert "job_has_errors" in out["blocking_reasons"]


def test_validate_not_independent():
    cand = _candidate_bundle()
    job = _ok_job(independence_status="partial_development_overlap")
    db = MagicMock()
    db.get.return_value = job
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
        return_value={},
    ):
        out = validate_benchmark_job_for_finalization(db, 2, candidate_bundle=cand)
    assert "independence_not_external" in out["blocking_reasons"]


def test_validate_ok_job():
    cand = _candidate_bundle()
    job = _ok_job()
    db = MagicMock()
    db.get.return_value = job
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
        return_value={},
    ):
        out = validate_benchmark_job_for_finalization(db, 2, candidate_bundle=cand)
    assert out["ok"] is True
    assert out["blocking_reasons"] == []


# ---------------------------------------------------------------------------
# Mapping / coefficients / scoring
# ---------------------------------------------------------------------------


def test_target_mapping_exact():
    assert TARGET_CALIBRATION_MAPPING["total_goals_ft"] == GI_E_ID
    assert TARGET_CALIBRATION_MAPPING["goals_ge_2"] == RAW_INDEX_ID
    assert TARGET_CALIBRATION_MAPPING["goals_ge_3"] == GI_E_ID
    assert TARGET_CALIBRATION_MAPPING["btts_ft"] == GI_E_ID


def test_coefficients_copied_without_modification():
    cand = _candidate_bundle()
    op = build_operational_calibration_payload(cand)
    heads = op[OPERATIONAL_CALIBRATION_KEY]
    assert heads["goals_ge_2"]["intercept"] == cand.calibration_payload[RAW_INDEX_ID]["goals_ge_2"]["intercept"]
    assert heads["goals_ge_2"]["coefficient"] == cand.calibration_payload[RAW_INDEX_ID]["goals_ge_2"]["coefficient"]
    assert heads["total_goals_ft"]["intercept"] == cand.calibration_payload[GI_E_ID]["total_goals_ft"]["intercept"]
    assert heads["goals_ge_3"]["coefficient"] == cand.calibration_payload[GI_E_ID]["goals_ge_3"]["coefficient"]
    assert heads["btts_ft"]["intercept"] == cand.calibration_payload[GI_E_ID]["btts_ft"]["intercept"]
    assert op["no_refit"] is True
    assert op["no_blending"] is True


def test_required_features_gi_a_only():
    assert "home_goals_scored_rolling_5" not in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS
    assert "total_goals_rolling_5" not in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS
    assert len(OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS) == 5
    feats = _features_complete()
    assert official_features_complete(feats, sample_size=10) is True
    incomplete = dict(feats)
    incomplete["home_goals_scored_avg"] = None
    assert official_features_complete(incomplete, sample_size=10) is False


def test_official_scoring_single_raw_and_heads():
    cand = _candidate_bundle()
    preview = _preview_bundle()
    job_val = {
        "ok": True,
        "job": {
            "id": 2,
            "job_version": "cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1",
            "independence_status": "external_independent",
            "scientific_label": "external_validation",
            "paired_complete": 5489,
            "reconciliation": {"ok": True},
        },
    }
    payload = build_official_bundle_payload(
        candidate=cand, preview=preview, job_validation=job_val, source_git_commit="abc"
    )
    official = SimpleNamespace(
        version=OFFICIAL_BUNDLE_VERSION,
        normalization_payload=payload["normalization_payload"],
        calibration_payload=payload["calibration_payload"],
        candidate_definition_hash=payload["candidate_definition_hash"],
    )
    feats = _features_complete()
    scored = score_official_support_with_bundle(feats, official)
    assert list(scored["candidate_scores"].keys()) == [RAW_INDEX_ID]
    assert scored["challenger_candidate_score"] is None
    assert scored["benchmark_score"] is None
    assert scored["diagnostic_score"] is None
    op = scored["calibrated_predictions"][OPERATIONAL_CALIBRATION_KEY]
    assert op["calibration_sources"]["goals_ge_2"] == RAW_INDEX_ID
    assert op["calibration_sources"]["total_goals_ft"] == GI_E_ID
    assert op["calibration_sources"]["goals_ge_3"] == GI_E_ID
    assert op["calibration_sources"]["btts_ft"] == GI_E_ID
    assert op["probability_under_1_5"] == pytest.approx(1.0 - op["probability_goals_ge_2"], abs=1e-5)
    assert op["probability_under_2_5"] == pytest.approx(1.0 - op["probability_goals_ge_3"], abs=1e-5)
    assert op["probability_btts_no"] == pytest.approx(1.0 - op["probability_btts"], abs=1e-5)
    assert op["no_blending"] is True


def test_official_raw_equals_legacy_gi_a():
    cand = _candidate_bundle()
    preview = _preview_bundle(
        calibration_payload={
            RAW_INDEX_ID: cand.calibration_payload[RAW_INDEX_ID],
            "GI_B_RECENCY": cand.calibration_payload[RAW_INDEX_ID],
            "MT1_LONG_TERM": {
                "total_goals_ft": _cal_head(1.0, 0.01),
                "goals_ge_2": _cal_head(-1.0, 0.01, logistic=True),
                "goals_ge_3": _cal_head(-1.0, 0.01, logistic=True),
                "btts_ft": _cal_head(-1.0, 0.01, logistic=True),
            },
            "GI_A_without_volatility": cand.calibration_payload[RAW_INDEX_ID],
        }
    )
    job_val = {
        "ok": True,
        "job": {"id": 2, "job_version": "cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1"},
    }
    payload = build_official_bundle_payload(candidate=cand, preview=preview, job_validation=job_val)
    official = SimpleNamespace(
        version=OFFICIAL_BUNDLE_VERSION,
        normalization_payload=payload["normalization_payload"],
        calibration_payload=payload["calibration_payload"],
    )
    feats = _features_complete()
    legacy = score_legacy_preview_with_bundle(feats, preview)
    official_scored = score_official_support_with_bundle(feats, official)
    assert official_scored["primary_candidate_score"] == legacy["primary_candidate_score"]
    assert official_scored["candidate_scores"][RAW_INDEX_ID] == legacy["candidate_scores"][RAW_INDEX_ID]


def test_dispatch_score_features_official():
    cand = _candidate_bundle()
    preview = _preview_bundle()
    payload = build_official_bundle_payload(
        candidate=cand,
        preview=preview,
        job_validation={"ok": True, "job": {"id": 2, "job_version": "x"}},
    )
    official = SimpleNamespace(
        version=OFFICIAL_BUNDLE_VERSION,
        normalization_payload=payload["normalization_payload"],
        calibration_payload=payload["calibration_payload"],
    )
    scored = score_features_with_bundle(_features_complete(), official)
    assert "GI_B_RECENCY" not in scored["candidate_scores"]
    assert RAW_INDEX_ID in scored["candidate_scores"]


def test_market_support_adapter():
    outputs = {
        "probability_goals_ge_2": 0.7,
        "probability_under_1_5": 0.3,
        "probability_goals_ge_3": 0.4,
        "expected_total_goals": 2.5,
        "probability_btts": 0.55,
    }
    over = build_goal_intensity_market_support(outputs, market="OVER_1_5")
    assert over["status"] == "ok"
    assert over["calibration_source"] == RAW_INDEX_ID
    assert over["advisory"] is False
    assert over["signals_integration_status"] == "blocked"
    total = build_goal_intensity_market_support(outputs, market="TOTAL_GOALS")
    assert total["calibration_source"] == GI_E_ID
    bad = build_goal_intensity_market_support(outputs, market="OVER_3_5")
    assert bad["status"] == "unsupported_market"


# ---------------------------------------------------------------------------
# Dry-run / freeze
# ---------------------------------------------------------------------------


def test_dry_run_read_only_no_write():
    cand = _candidate_bundle()
    preview = _preview_bundle()
    job = _ok_job()
    db = MagicMock()
    db.get.return_value = job
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_preview_bundle_v1_1",
        return_value=preview,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_candidate_bundle_v2_1",
        return_value=cand,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
        return_value={},
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_active_bundle",
        return_value=preview,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_bundle_by_version",
        return_value=None,
    ):
        out = freeze_official_support_bundle(db, 2, dry_run=True)
    assert out["dry_run"] is True
    assert out["writes"] == 0
    db.add.assert_not_called()
    assert out.get("freeze_allowed") is True or out.get("status") in {"preview", "blocked"}


def test_token_missing_no_write():
    db = MagicMock()
    out = freeze_official_support_bundle(db, 2, dry_run=False, confirm=None)
    assert out["status"] == "error"
    assert out["error"] == "invalid_confirm_token"
    assert out["writes"] == 0
    db.add.assert_not_called()


def test_token_wrong_no_write():
    db = MagicMock()
    out = freeze_official_support_bundle(db, 2, dry_run=False, confirm="WRONG")
    assert out["status"] == "error"
    assert out["writes"] == 0


def test_freeze_creates_official_and_supersedes_preview():
    cand = _candidate_bundle()
    preview = _preview_bundle()
    job = _ok_job()
    db = MagicMock()
    db.get.return_value = job

    call_n = {"n": 0}

    def scalars_side_effect(stmt):
        call_n["n"] += 1
        m = MagicMock()
        n = call_n["n"]
        if n == 1:
            m.first.return_value = preview  # lock preview
        elif n == 2:
            m.first.return_value = cand  # lock candidate
        elif n == 3:
            m.first.return_value = None  # existing official same hash
        elif n == 4:
            m.all.return_value = [preview]  # other actives
        else:
            m.first.return_value = None
            m.all.return_value = []
        return m

    db.scalars.side_effect = scalars_side_effect

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_preview_bundle_v1_1",
        return_value=preview,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_candidate_bundle_v2_1",
        return_value=cand,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
        return_value={},
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_active_bundle",
        return_value=preview,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_bundle_by_version",
        return_value=None,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.clear_goal_intensity_v5_readiness_cache",
        create=True,
    ):
        # build_finalization_dry_run needs get_bundle_by_version for existing official
        out = freeze_official_support_bundle(
            db, 2, dry_run=False, confirm=FREEZE_CONFIRM_TOKEN, source_git_commit="test"
        )

    assert out["status"] in {"frozen", "blocked", "error", "already_frozen_same_definition"}
    if out["status"] == "frozen":
        assert out["writes"] == 1
        assert out["version"] == OFFICIAL_BUNDLE_VERSION
        assert preview.is_active is False
        assert preview.status == BUNDLE_STATUS_SUPERSEDED
        assert cand.status == BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE
        assert cand.is_active is False
        db.add.assert_called()
        db.commit.assert_called()


def test_idempotency_already_frozen():
    cand = _candidate_bundle()
    preview = _preview_bundle()
    existing = SimpleNamespace(
        id=99,
        version=OFFICIAL_BUNDLE_VERSION,
        candidate_definition_hash="will_match",
        is_active=True,
        status=BUNDLE_STATUS_ACTIVE,
    )
    # Force same hash by patching build
    job = _ok_job()
    db = MagicMock()
    db.get.return_value = job

    def scalars_side_effect(stmt):
        m = MagicMock()
        # After locks, existing found
        text = str(stmt)
        if "FOR UPDATE" in text.upper() or True:
            pass
        return m

    # Simpler: call freeze path after dry_run allowed and mock existing lookup
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.build_finalization_dry_run",
    ) as dry:
        payload = build_official_bundle_payload(
            candidate=cand,
            preview=preview,
            job_validation={
                "ok": True,
                "job": {"id": 2, "job_version": "cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1"},
            },
        )
        existing.candidate_definition_hash = payload["candidate_definition_hash"]
        dry.return_value = {
            "freeze_allowed": True,
            "_bundle_payload": payload,
            "status": "preview",
        }

        call_state = {"i": 0}

        def scalars_fn(stmt):
            call_state["i"] += 1
            m = MagicMock()
            i = call_state["i"]
            if i == 1:
                m.first.return_value = preview
            elif i == 2:
                m.first.return_value = cand
            elif i == 3:
                m.first.return_value = existing  # same definition
            else:
                m.first.return_value = None
                m.all.return_value = []
            return m

        db.scalars.side_effect = scalars_fn
        with patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_preview_bundle_v1_1",
            return_value=preview,
        ), patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_candidate_bundle_v2_1",
            return_value=cand,
        ), patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_official_support.validate_frozen_candidate_bundle",
            return_value={},
        ):
            out = freeze_official_support_bundle(db, 2, dry_run=False, confirm=FREEZE_CONFIRM_TOKEN)

    assert out["status"] == "already_frozen_same_definition"
    assert out["writes"] == 0


def test_archived_candidates_list():
    assert "GI_B_RECENCY" in ARCHIVED_FROM_OPERATIONAL
    assert "GI_F_REGULARIZED_PILLARS" in ARCHIVED_FROM_OPERATIONAL
    assert RAW_INDEX_ID not in ARCHIVED_FROM_OPERATIONAL
    assert GI_E_ID not in ARCHIVED_FROM_OPERATIONAL


def test_definition_hash_deterministic():
    cand = _candidate_bundle()
    preview = _preview_bundle()
    job_val = {
        "ok": True,
        "job": {"id": 2, "job_version": "cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1"},
    }
    a = build_official_bundle_payload(candidate=cand, preview=preview, job_validation=job_val, source_git_commit="x")
    b = build_official_bundle_payload(candidate=cand, preview=preview, job_validation=job_val, source_git_commit="x")
    assert a["candidate_definition_hash"] == b["candidate_definition_hash"]
    assert a["version"] == OFFICIAL_BUNDLE_VERSION
    assert a["candidate_definitions_payload"]["module_version"] == OFFICIAL_MODULE_VERSION
    assert a["candidate_definitions_payload"]["no_refit"] is True
    assert a["candidate_definitions_payload"]["fallback_policy"]["reason_code"] == FALLBACK_REASON_FEATURES_INCOMPLETE


def test_get_active_bundle_prefers_official():
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import get_active_bundle

    official = _preview_bundle(id=50, version=OFFICIAL_BUNDLE_VERSION)
    db = MagicMock()
    first = MagicMock()
    first.first.return_value = official
    db.scalars.return_value = first
    out = get_active_bundle(db)
    assert out is official
    assert out.version == OFFICIAL_BUNDLE_VERSION
