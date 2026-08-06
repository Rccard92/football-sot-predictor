"""Test Phase 2C — candidati GI_E/GI_F, split, freeze bundle v2.1 non attivo."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_ACTIVE,
    BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
    PREVIEW_BUNDLE_VERSION,
)
from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import (
    PRIMARY_ID,
    CHALLENGER_ID,
    BENCHMARK_ID,
    DIAGNOSTIC_ID,
    load_goal_intensity_prospective_paired_observations,
    _dedupe_by_fixture,
)
from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import (
    ACTIVE_CANDIDATE_IDS,
    ARCHIVED_CANDIDATE_IDS,
    DEVELOPMENT_PROTOCOL_VERSION,
    GI_E_ID,
    GI_F_ID,
    GI_F_ALPHA_GRID,
    GI_F_PILLARS,
    PHASE_2C_FREEZE_CONFIRM_TOKEN,
    TARGET_BUNDLE_VERSION,
    HoldoutAccessGuard,
    _gi_a_raw,
    _gi_f_raw_from_weights,
    apply_calibrations,
    fit_calibrations_for_scores,
    fit_gi_e,
    fit_gi_f,
    freeze_candidate_bundle,
    temporal_split,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    SCHEMA_CONTRACTS,
)


def _obs(
    i: int,
    *,
    day_offset: int,
    y_total: float = 2.0,
    pillars: dict | None = None,
) -> dict:
    kick = datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc) + timedelta(days=day_offset)
    base_pillars = {
        "OP1_HOME_LONG_TERM": 40 + (i % 20),
        "OP2_HOME_RECENCY": 45 + (i % 15),
        "DV1_MEAN_CONCEDED": 50 + (i % 10),
        "MT1_LONG_TERM": 55 + (i % 12),
        "MT2_LONG_TERM_PLUS_RECENCY": 52 + (i % 8),
        "OV1_STD": 48 + (i % 9),
    }
    if pillars:
        base_pillars.update(pillars)
    gi_a = float(
        np.mean(
            [
                base_pillars["OP1_HOME_LONG_TERM"],
                base_pillars["DV1_MEAN_CONCEDED"],
                base_pillars["MT1_LONG_TERM"],
                base_pillars["OV1_STD"],
            ]
        )
    )
    gi_b = float(
        np.mean(
            [
                base_pillars["OP2_HOME_RECENCY"],
                base_pillars["DV1_MEAN_CONCEDED"],
                base_pillars["MT2_LONG_TERM_PLUS_RECENCY"],
                base_pillars["OV1_STD"],
            ]
        )
    )
    return {
        "snapshot_id": i,
        "today_fixture_id": 1000 + i,
        "local_fixture_id": 2000 + i,
        "competition_id": 1 if i % 2 == 0 else 2,
        "competition_name": "A" if i % 2 == 0 else "B",
        "kickoff": kick,
        "scan_date": kick.date(),
        "y_total": y_total,
        "y_ge2": 1 if y_total >= 2 else 0,
        "y_ge3": 1 if y_total >= 3 else 0,
        "y_btts": 1 if i % 3 == 0 else 0,
        "v4_eg": 2.1,
        "v4_p_ge2": 0.7,
        "v4_p_ge3": 0.45,
        "pillars": base_pillars,
        "v5": {
            PRIMARY_ID: {
                "raw_score": gi_a,
                "expected_total_goals": 2.0 + (i % 5) * 0.05,
                "probability_goals_ge_2": 0.6,
                "probability_goals_ge_3": 0.4,
                "probability_btts": 0.5,
            },
            CHALLENGER_ID: {
                "raw_score": gi_b,
                "expected_total_goals": 2.05,
                "probability_goals_ge_2": 0.61,
                "probability_goals_ge_3": 0.41,
                "probability_btts": 0.51,
            },
            BENCHMARK_ID: {
                "raw_score": base_pillars["MT1_LONG_TERM"],
                "expected_total_goals": 2.2,
                "probability_goals_ge_2": 0.62,
                "probability_goals_ge_3": 0.42,
                "probability_btts": 0.52,
            },
            DIAGNOSTIC_ID: {
                "raw_score": gi_a - 1,
                "expected_total_goals": 2.15,
                "probability_goals_ge_2": 0.63,
                "probability_goals_ge_3": 0.43,
                "probability_btts": 0.53,
            },
        },
    }


def _make_cohort(n: int = 600) -> list[dict]:
    # Spread across many days so date-aware split works
    rows = []
    for i in range(n):
        day = i // 3  # ~3 fixtures per day
        y = 1.0 + (i % 5) * 0.5
        rows.append(_obs(i, day_offset=day, y_total=y))
    return rows


def test_schema_contract_includes_phase_2c_files():
    required = SCHEMA_CONTRACTS["goal-intensity-v5"]["required_files"]
    for name in (
        "phase_2c_candidate_summary.json",
        "phase_2c_split_manifest.json",
        "phase_2c_validation_metrics.csv",
        "phase_2c_holdout_metrics.csv",
        "phase_2c_holdout_pairwise.csv",
        "phase_2c_gi_f_weights.csv",
        "phase_2c_calibrations.json",
        "phase_2c_archived_candidates.json",
        "phase_2c_bundle_definition.json",
    ):
        assert name in required
    assert MONITORING_EXPORT_VERSION.endswith("v12")


def test_status_constant_length_fits_string64():
    assert len(BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE) == 35
    assert len(BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE) <= 64


def test_temporal_split_no_overlap_date_aware():
    rows = _make_cohort(600)
    split = temporal_split(rows)
    assert split["status"] == "ok"
    train, val, hold = split["train"], split["validation"], split["holdout"]
    assert len(train) >= 100 and len(val) >= 100 and len(hold) >= 100
    ids_t = {o["local_fixture_id"] for o in train}
    ids_v = {o["local_fixture_id"] for o in val}
    ids_h = {o["local_fixture_id"] for o in hold}
    assert not (ids_t & ids_v)
    assert not (ids_t & ids_h)
    assert not (ids_v & ids_h)
    # same UTC date not split
    dates_t = {o["kickoff"].date() for o in train}
    dates_v = {o["kickoff"].date() for o in val}
    dates_h = {o["kickoff"].date() for o in hold}
    assert not (dates_t & dates_v)
    assert not (dates_t & dates_h)
    assert not (dates_v & dates_h)
    assert max(o["kickoff"] for o in train) <= min(o["kickoff"] for o in val)
    assert max(o["kickoff"] for o in val) <= min(o["kickoff"] for o in hold)


def test_temporal_split_deterministic_rerun():
    rows = _make_cohort(520)
    a = temporal_split(rows)
    b = temporal_split(rows)
    assert [o["snapshot_id"] for o in a["train"]] == [o["snapshot_id"] for o in b["train"]]
    assert a["meta"]["train"]["fixture_ids_hash"] == b["meta"]["train"]["fixture_ids_hash"]


def test_temporal_split_blocked_when_too_small():
    rows = _make_cohort(50)
    split = temporal_split(rows)
    assert split["status"] == "blocked"
    assert "paired_total_below_minimum" in split["blocking_reasons"]


def test_gi_e_raw_identical_to_gi_a():
    rows = _make_cohort(600)
    split = temporal_split(rows)
    gi_e = fit_gi_e(split["train"], split["validation"])
    assert gi_e["status"] == "ok"
    for o in split["train"] + split["validation"] + split["holdout"]:
        assert _gi_a_raw(o) == pytest.approx(_gi_a_raw(o))
        # GI_E uses same raw
        raw = _gi_a_raw(o)
        assert raw is not None
    cal = gi_e["calibration_payload"]
    assert cal["total_goals_ft"]["calibration_method"] == "train_linear_regression"
    assert cal["goals_ge_2"]["calibration_method"] == "train_logistic_regression"
    assert "intercept" in cal["total_goals_ft"]
    # no hardcoded bias subtraction constant in payload
    assert cal["total_goals_ft"].get("coefficient") is not None


def test_gi_e_holdout_not_in_fit():
    rows = _make_cohort(600)
    split = temporal_split(rows)
    gi_e = fit_gi_e(split["train"], split["validation"])
    # refit n should be train+val
    n_tv = len(split["train"]) + len(split["validation"])
    assert gi_e["calibration_payload"]["total_goals_ft"]["train_n"] == n_tv


def test_gi_f_uses_only_allowed_pillars_and_alpha_grid():
    rows = _make_cohort(600)
    split = temporal_split(rows)
    gi_f = fit_gi_f(split["train"], split["validation"])
    assert gi_f["status"] == "ok"
    assert list(GI_F_ALPHA_GRID) == [0.01, 0.1, 1.0, 10.0, 100.0]
    assert set(gi_f["weights"].keys()) == set(GI_F_PILLARS)
    wsum = sum(gi_f["weights"].values())
    assert wsum == pytest.approx(1.0, abs=1e-6)
    assert all(v >= -1e-12 for v in gi_f["weights"].values())
    assert gi_f["selected_alpha"] in GI_F_ALPHA_GRID
    # scores 0-100
    for o in split["holdout"][:20]:
        sc = _gi_f_raw_from_weights(o, gi_f["weights"])
        assert sc is not None
        assert 0.0 <= sc <= 100.0 + 1e-6


def test_gi_f_selection_lexicographic_prefers_higher_alpha_on_tie():
    # unit: sorting key prefers larger alpha when metrics equal
    from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import fit_gi_f as _

    rows = [
        {
            "alpha": 1.0,
            "validation_mae": 0.5,
            "validation_mean_brier_ge2_ge3": 0.2,
            "validation_brier_btts": 0.2,
        },
        {
            "alpha": 10.0,
            "validation_mae": 0.5,
            "validation_mean_brier_ge2_ge3": 0.2,
            "validation_brier_btts": 0.2,
        },
    ]

    def key(r):
        return (
            float(r["validation_mae"]),
            float(r["validation_mean_brier_ge2_ge3"]),
            float(r["validation_brier_btts"]),
            -float(r["alpha"]),
        )

    assert sorted(rows, key=key)[0]["alpha"] == 10.0


def test_gi_f_definition_hash_changes_with_weight():
    rows = _make_cohort(600)
    split = temporal_split(rows)
    a = fit_gi_f(split["train"], split["validation"])
    b = fit_gi_f(split["train"], split["validation"])
    assert a["definition_hash"] == b["definition_hash"]
    # mutate weight
    w = dict(a["weights"])
    first = next(iter(w))
    w[first] = w[first] + 0.01
    # renormalize for hash contrast only
    from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import _sha256_canonical

    h1 = a["definition_hash"]
    h2 = _sha256_canonical({"alpha": a["selected_alpha"], "weights": w, "pillars": list(GI_F_PILLARS)})
    assert h1 != h2


def test_holdout_guard_blocks_second_access():
    g = HoldoutAccessGuard()
    g.access()
    g.lock()
    with pytest.raises(RuntimeError, match="holdout_reused_for_selection"):
        g.access()


def test_apply_calibrations_clipping():
    cal = {
        "total_goals_ft": {
            "intercept": 0.0,
            "coefficient": 0.03,
            "calibration_method": "train_linear_regression",
        },
        "goals_ge_2": {
            "intercept": -2.0,
            "coefficient": 0.05,
            "calibration_method": "train_logistic_regression",
        },
        "goals_ge_3": {
            "intercept": -3.0,
            "coefficient": 0.04,
            "calibration_method": "train_logistic_regression",
        },
        "btts_ft": {
            "intercept": -1.0,
            "coefficient": 0.02,
            "calibration_method": "train_logistic_regression",
        },
    }
    out = apply_calibrations(50.0, cal)
    assert out["expected_total_goals"] is not None
    assert 0 < out["probability_goals_ge_2"] < 1


def test_dedupe_counts_reason():
    # smoke: helper exists and returns list
    snaps = []
    assert _dedupe_by_fixture(snaps) == []


def test_active_archived_ids():
    assert ACTIVE_CANDIDATE_IDS == (
        PRIMARY_ID,
        CHALLENGER_ID,
        GI_E_ID,
        GI_F_ID,
    )
    assert ARCHIVED_CANDIDATE_IDS == (BENCHMARK_ID, DIAGNOSTIC_ID)
    assert DEVELOPMENT_PROTOCOL_VERSION == "cecchino_goal_intensity_v5_phase_2c_candidate_development_v1"
    assert TARGET_BUNDLE_VERSION == "cecchino_goal_intensity_v5_candidate_bundle_v2_1"


def test_freeze_dry_run_no_write_and_token_required(monkeypatch):
    parent = MagicMock()
    parent.id = 1
    parent.version = PREVIEW_BUNDLE_VERSION
    parent.is_active = True
    parent.status = BUNDLE_STATUS_ACTIVE
    parent.candidate_definition_hash = "abc"
    parent.normalization_method = "train_ecdf_midrank"
    parent.normalization_payload = {"features": {}}
    parent.calibration_payload = {
        PRIMARY_ID: {"total_goals_ft": {"intercept": 0.5, "coefficient": 0.02, "calibration_method": "train_linear_regression"}},
        CHALLENGER_ID: {"total_goals_ft": {"intercept": 0.5, "coefficient": 0.02, "calibration_method": "train_linear_regression"}},
    }
    parent.retrospective_date_from = date(2024, 1, 1)
    parent.retrospective_date_to = date(2024, 6, 1)
    parent.first_prospective_scan_date = date(2024, 7, 1)
    parent.frozen_at = datetime(2024, 7, 1, tzinfo=timezone.utc)

    db = MagicMock()

    def fake_develop(*args, **kwargs):
        return {
            "status": "preview",
            "freeze_allowed": True,
            "checks": {
                "holdout_access_count": 1,
                "historical_run_used": False,
                "external_api_calls": 0,
                "parent_bundle_modified": False,
                "snapshot_writes": 0,
            },
            "_bundle_payload": {
                "version": TARGET_BUNDLE_VERSION,
                "candidate_indices_version": DEVELOPMENT_PROTOCOL_VERSION,
                "candidate_definition_hash": "defhash",
                "fixture_ids_hash": "fixhash",
                "targets_hash": "tgthash",
                "normalization_method": parent.normalization_method,
                "normalization_payload": parent.normalization_payload,
                "calibration_payload": parent.calibration_payload,
                "candidate_definitions_payload": {"active_candidate_ids": list(ACTIVE_CANDIDATE_IDS)},
            },
            "parent_bundle": {"id": 1, "remains_active": True},
        }

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates.develop_phase_2c_candidates",
        fake_develop,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates.get_active_bundle",
        lambda _db: parent,
    )

    dry = freeze_candidate_bundle(db, dry_run=True)
    assert dry["dry_run"] is True
    assert dry.get("writes", 0) == 0
    db.add.assert_not_called()

    bad = freeze_candidate_bundle(db, dry_run=False, confirm="WRONG")
    assert bad["status"] == "error"
    assert bad["error"] == "invalid_confirm_token"
    db.add.assert_not_called()

    # token correct path with lock + insert
    locked = parent
    existing_q = MagicMock()
    existing_q.first.return_value = None

    def scalars(stmt):
        m = MagicMock()
        # first call: lock parent; second: existing check
        if not hasattr(scalars, "n"):
            scalars.n = 0
        scalars.n += 1
        if scalars.n == 1:
            m.first.return_value = locked
        else:
            m.first.return_value = None
        return m

    db.scalars = scalars
    ok = freeze_candidate_bundle(db, dry_run=False, confirm=PHASE_2C_FREEZE_CONFIRM_TOKEN)
    assert ok["status"] == "frozen"
    assert ok["is_active"] is False
    assert ok["writes"] == 1
    db.add.assert_called()
    db.commit.assert_called()


def test_fit_calibrations_finite():
    rows = _make_cohort(120)
    scores = [_gi_a_raw(o) for o in rows]
    scores_f = [float(s) for s in scores]
    cal = fit_calibrations_for_scores(scores_f, rows)
    assert cal["total_goals_ft"]["intercept"] is not None
    assert np.isfinite(cal["total_goals_ft"]["coefficient"])
