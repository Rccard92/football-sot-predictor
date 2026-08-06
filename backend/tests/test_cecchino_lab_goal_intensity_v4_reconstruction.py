"""Test ricostruzione certificata V4 da input storici congelati."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.services.cecchino_data_lab.goal_intensity_historical_benchmark_scoring import (
    extract_v4_from_historical_snapshot,
    extract_v4_with_provenance,
    prediction_input_hash,
)
from app.services.cecchino_data_lab.goal_intensity_historical_v4_reconstruction import (
    CONTEXT_BUILDER_VERSION,
    REASON_INPUT_MISMATCH,
    REASON_KPI_MISMATCH,
    REASON_MISSING_CONTEXT,
    REASON_MISSING_LAMBDA,
    RECONSTRUCTION_VERSION,
    V4_FORMULA_VERSION,
    V4_SOURCE_PERSISTED_PAYLOAD,
    V4_SOURCE_RECONSTRUCTED,
    CompetitionProxyCache,
    certify_reconstructed_input_snapshot,
    check_historical_kpi_consistency,
    extract_v4_certified,
    reconstruct_v4_from_frozen_historical_inputs,
)
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    build_lab_prematch_contexts,
    compute_goal_markets_from_contexts,
    prior_proxies_strict,
    sort_proxies,
)
from app.services.cecchino_data_lab import goal_intensity_historical_benchmark_service as svc
from app.services.cecchino.cecchino_goal_intensity_analysis import _lambda_from_goal_markets


def _proxy(
    *,
    pid: int,
    kickoff: datetime,
    home_id: int,
    away_id: int,
    gh: int = 1,
    ga: int = 0,
    home_name: str = "Home",
    away_name: str = "Away",
    row: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=pid,
        kickoff_at=kickoff,
        match_date=kickoff.date(),
        match_time=kickoff.time().replace(tzinfo=None) if kickoff.tzinfo else kickoff.time(),
        source_row_number=row if row is not None else pid,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name=home_name,
        away_team_name=away_name,
        goals_home=gh,
        goals_away=ga,
        status="FT",
        competition_id=1,
        raw_json={"score": {"halftime": {"home": 0, "away": 0}}},
        lab_match=None,
    )


def _season_proxies(n: int = 36) -> list[SimpleNamespace]:
    """Stagione sintetica con poche squadre ricorrenti (sample goal markets sufficiente)."""
    base = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    teams = [
        (100, "Alpha"),
        (200, "Beta"),
        (300, "Gamma"),
        (400, "Delta"),
    ]
    out: list[SimpleNamespace] = []
    for i in range(n):
        home = teams[i % len(teams)]
        away = teams[(i + 1 + (i // len(teams))) % len(teams)]
        if home[0] == away[0]:
            away = teams[(i + 2) % len(teams)]
        out.append(
            _proxy(
                pid=i + 1,
                kickoff=base + timedelta(days=i),
                home_id=home[0],
                away_id=away[0],
                gh=1 + (i % 3),
                ga=i % 2,
                home_name=home[1],
                away_name=away[1],
            )
        )
    return sort_proxies(out)


def _cache_from_proxies(
    proxies: list[SimpleNamespace],
    *,
    competition: str = "E0",
) -> CompetitionProxyCache:
    cache = CompetitionProxyCache()
    cache.season_label = "2021/22"
    cache._by_competition[competition] = list(proxies)
    cache._load_counts[competition] = len(proxies)
    for p in proxies:
        cache._proxy_by_id[int(p.id)] = p
        cache._competition_by_match_id[int(p.id)] = competition
    return cache


def _snap_for_target(
    proxies: list[SimpleNamespace],
    target: SimpleNamespace,
    *,
    competition: str = "E0",
    kpi: dict | None = None,
    mutate_input: dict | None = None,
) -> SimpleNamespace:
    ctx = build_lab_prematch_contexts(competition_ordered=proxies, target=target)
    inp = build_input_snapshot(ctx)
    if mutate_input:
        inp = deepcopy(inp)
        for k, v in mutate_input.items():
            if isinstance(v, dict) and isinstance(inp.get(k), dict):
                inp[k] = {**inp[k], **v}
            else:
                inp[k] = v
    gm = compute_goal_markets_from_contexts(ctx)
    if kpi is None:
        rows = []
        for mk in ("OVER_1_5", "OVER_2_5"):
            block = gm.get(mk) if isinstance(gm.get(mk), dict) else {}
            summary = block.get("summary") if isinstance(block.get("summary"), dict) else {}
            odd = block.get("final_odd")
            if odd is None:
                odd = summary.get("final_odd")
            prob = summary.get("final_probability")
            if odd is not None:
                rows.append(
                    {
                        "market_key": mk,
                        "quota_cecchino": round(float(odd), 2),
                        "prob_cecchino": round(1.0 / float(odd), 4) if odd else None,
                    }
                )
        kpi = {"rows": rows}
    return SimpleNamespace(
        id=9000 + int(target.id),
        lab_match_id=int(target.id),
        competition_name=competition,
        kickoff_at=target.kickoff_at,
        chronological_order=int(target.id),
        cecchino_output_json={},
        goal_intensity_compatibility_json={
            "inputs": {
                "bundle_features": {
                    "home_goals_scored_avg": 1.4,
                    "home_goals_scored_rolling_5": 1.6,
                    "home_goals_conceded_avg": 1.1,
                    "away_goals_conceded_avg": 1.2,
                    "total_goals_avg": 2.5,
                    "total_goals_rolling_5": 2.7,
                    "goals_scored_std_last_10": 0.9,
                }
            }
        },
        result_json={"fulltime": {"home": 2, "away": 1}},
        input_snapshot_json=inp,
        module_availability_json={},
        balance_v5_json={},
        historical_kpi_json=kpi,
    )


def test_persisted_v4_preferred_over_reconstruction():
    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(proxies, target)
    snap.cecchino_output_json = {
        "goal_intensity_analysis": {
            "status": "available",
            "expected_goals_total": 3.33,
            "version": V4_FORMULA_VERSION,
        }
    }
    result = extract_v4_certified(snap, proxy_cache=cache)
    assert result["v4_source"] == V4_SOURCE_PERSISTED_PAYLOAD
    assert result["v4_payload"]["expected_goals_total"] == 3.33
    assert result["reconstruction_version"] is None


def test_fallback_only_when_persisted_missing():
    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(proxies, target)
    result = extract_v4_certified(snap, proxy_cache=cache)
    assert result["reason"] is None
    assert result["v4_source"] == V4_SOURCE_RECONSTRUCTED
    assert result["reconstruction_version"] == RECONSTRUCTION_VERSION
    assert result["v4_payload"] is not None
    assert float(result["expected_goals_total"]) > 0


def test_contexts_from_priors_only_target_and_same_kickoff_excluded():
    proxies = _season_proxies()
    target = proxies[28]
    same_ko = _proxy(
        pid=999,
        kickoff=target.kickoff_at,
        home_id=50,
        away_id=60,
        home_name="SameKoH",
        away_name="SameKoA",
    )
    ordered = sort_proxies(list(proxies) + [same_ko])
    priors = prior_proxies_strict(ordered, target)
    assert all(int(p.id) != int(target.id) for p in priors)
    assert all(p.kickoff_at < target.kickoff_at for p in priors)
    assert all(int(p.id) != 999 for p in priors)

    ctx = build_lab_prematch_contexts(competition_ordered=ordered, target=target)
    assert ctx.leakage_ok is True
    flat_ids = [i for ids in ctx.fixture_ids.values() for i in ids]
    assert int(target.id) not in flat_ids
    assert 999 not in flat_ids


def test_result_not_passed_to_scorer_path():
    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(proxies, target)
    # poison result — reconstruction must ignore it
    snap.result_json = {"fulltime": {"home": 99, "away": 99}}
    with patch(
        "app.services.cecchino_data_lab.goal_intensity_historical_v4_reconstruction.compute_goal_markets_from_contexts",
        wraps=compute_goal_markets_from_contexts,
    ) as mocked:
        result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["v4_payload"] is not None
    assert mocked.called
    # contexts built without reading result_json
    assert result["anti_leakage"]["result_not_used"] is True
    assert result["anti_leakage"]["result_json_not_read_for_prediction"] is True


def test_input_snapshot_perfectly_coherent():
    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(proxies, target)
    result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["reason"] is None
    assert result["input_hash"] is not None
    assert result["reconstruction_hash"] is not None


def test_fixture_ids_mismatch():
    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(
        proxies,
        target,
        mutate_input={"fixture_ids": {"home_context": [1, 2, 3]}},
    )
    result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["v4_payload"] is None
    assert result["reason"] == REASON_INPUT_MISMATCH


def test_wdl_mismatch():
    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(
        proxies,
        target,
        mutate_input={
            "home_context": {"wdl": {"wins": 99, "draws": 0, "losses": 0}, "sample": 99}
        },
    )
    result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["reason"] == REASON_INPUT_MISMATCH


def test_sample_mismatch():
    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(
        proxies,
        target,
        mutate_input={"away_total": {"sample": 12345}},
    )
    result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["reason"] == REASON_INPUT_MISMATCH


def test_kpi_consistency_pass_and_fail():
    proxies = _season_proxies()
    target = proxies[28]
    ctx = build_lab_prematch_contexts(competition_ordered=proxies, target=target)
    gm = compute_goal_markets_from_contexts(ctx)
    odd15 = (gm.get("OVER_1_5") or {}).get("final_odd")
    assert odd15 is not None

    ok = check_historical_kpi_consistency(
        gm,
        {
            "rows": [
                {
                    "market_key": "OVER_1_5",
                    "quota_cecchino": round(float(odd15), 2),
                    "prob_cecchino": round(1.0 / float(odd15), 4),
                }
            ]
        },
    )
    assert ok["pass"] is True
    assert ok["historical_kpi_consistency_status"] == "pass"

    bad = check_historical_kpi_consistency(
        gm,
        {
            "rows": [
                {
                    "market_key": "OVER_1_5",
                    "quota_cecchino": round(float(odd15) + 0.5, 2),
                    "prob_cecchino": 0.1,
                }
            ]
        },
    )
    assert bad["pass"] is False
    assert bad["historical_kpi_consistency_status"] == "fail"

    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(
        proxies,
        target,
        kpi={
            "rows": [
                {
                    "market_key": "OVER_1_5",
                    "quota_cecchino": round(float(odd15) + 0.5, 2),
                    "prob_cecchino": 0.1,
                }
            ]
        },
    )
    result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["reason"] == REASON_KPI_MISMATCH


def test_lambda_valid_and_missing():
    proxies = _season_proxies()
    target = proxies[28]
    ctx = build_lab_prematch_contexts(competition_ordered=proxies, target=target)
    gm = compute_goal_markets_from_contexts(ctx)
    lam = _lambda_from_goal_markets(gm)
    assert lam is not None and lam > 0

    with patch(
        "app.services.cecchino_data_lab.goal_intensity_historical_v4_reconstruction._lambda_from_goal_markets",
        return_value=None,
    ):
        cache = _cache_from_proxies(proxies)
        snap = _snap_for_target(proxies, target)
        result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["reason"] == REASON_MISSING_LAMBDA


def test_missing_context_data():
    cache = CompetitionProxyCache()
    snap = SimpleNamespace(
        lab_match_id=1,
        competition_name="E0",
        input_snapshot_json={},
        historical_kpi_json={},
    )
    result = reconstruct_v4_from_frozen_historical_inputs(snap, proxy_cache=cache)
    assert result["reason"] == REASON_MISSING_CONTEXT


def test_certify_helper_detects_mismatch():
    left = {
        "home_context": {"wdl": {"wins": 1, "draws": 0, "losses": 0}, "sample": 1},
        "away_context": {"wdl": {"wins": 0, "draws": 1, "losses": 0}, "sample": 1},
        "home_total": {"wdl": {"wins": 1, "draws": 0, "losses": 0}, "sample": 1},
        "away_total": {"wdl": {"wins": 0, "draws": 1, "losses": 0}, "sample": 1},
        "home_recent_context_5": {"wdl": {"wins": 1, "draws": 0, "losses": 0}, "sample": 1},
        "away_recent_context_5": {"wdl": {"wins": 0, "draws": 1, "losses": 0}, "sample": 1},
        "home_recent_total_6": {"wdl": {"wins": 1, "draws": 0, "losses": 0}, "sample": 1},
        "away_recent_total_6": {"wdl": {"wins": 0, "draws": 1, "losses": 0}, "sample": 1},
        "fixture_ids": {"home_context": [1]},
        "prior_count": 1,
        "leakage_ok": True,
        "sample_meta": {},
    }
    right = deepcopy(left)
    right["fixture_ids"] = {"home_context": [2]}
    cert = certify_reconstructed_input_snapshot(left, right)
    assert cert["ok"] is False
    assert "fixture_ids" in cert["mismatches"]


def test_prediction_input_hash_includes_reconstruction():
    h1 = prediction_input_hash(
        features={"total_goals_avg": 2.5},
        bundle_definition_hash="b",
        snapshot_id=1,
        v4_source=V4_SOURCE_RECONSTRUCTED,
        reconstruction_version=RECONSTRUCTION_VERSION,
        v4_formula_version=V4_FORMULA_VERSION,
        reconstruction_input_hash="abc",
    )
    h2 = prediction_input_hash(
        features={"total_goals_avg": 2.5},
        bundle_definition_hash="b",
        snapshot_id=1,
        v4_source=V4_SOURCE_RECONSTRUCTED,
        reconstruction_version=RECONSTRUCTION_VERSION,
        v4_formula_version=V4_FORMULA_VERSION,
        reconstruction_input_hash="abc",
    )
    h3 = prediction_input_hash(
        features={"total_goals_avg": 2.5},
        bundle_definition_hash="b",
        snapshot_id=1,
        v4_source=V4_SOURCE_PERSISTED_PAYLOAD,
        v4_formula_version=V4_FORMULA_VERSION,
    )
    assert h1 == h2
    assert h1 != h3


def test_process_uses_same_reconstruction_as_extract():
    from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import (
        ACTIVE_CANDIDATE_IDS,
        ARCHIVED_CANDIDATE_IDS,
        DEVELOPMENT_PROTOCOL_VERSION,
        GI_F_ID,
        GI_F_PILLARS,
        TARGET_BUNDLE_VERSION,
    )
    from app.models.cecchino_goal_intensity_v5_preview import (
        BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
    )

    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(proxies, target)

    weights = {p: round(1.0 / len(GI_F_PILLARS), 6) for p in GI_F_PILLARS}
    bundle = SimpleNamespace(
        id=1,
        version=TARGET_BUNDLE_VERSION,
        status=BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
        is_active=False,
        candidate_definition_hash="hash",
        fixture_ids_hash="fix",
        targets_hash="th",
        candidate_definitions_payload={
            "parent_bundle_id": 1,
            "parent_bundle_version": "v1",
            "development_protocol_version": DEVELOPMENT_PROTOCOL_VERSION,
            "active_candidate_ids": list(ACTIVE_CANDIDATE_IDS),
            "archived_candidate_ids": list(ARCHIVED_CANDIDATE_IDS),
            "intended_use": "historical_external_benchmark_only",
            "live_scoring_enabled": False,
            "signals_integration_enabled": False,
            "holdout_access_count": 1,
            "gi_f_weights": weights,
            "selected_alpha": 1.0,
            GI_F_ID: {"weights": weights, "selected_alpha": 1.0},
        },
        calibration_payload={
            mid: {
                "total_goals_ft": {"intercept": 0.5, "coefficient": 0.02, "train_n": 100},
                "goals_ge_2": {"intercept": -1.0, "coefficient": 0.03, "train_n": 100},
                "goals_ge_3": {"intercept": -2.0, "coefficient": 0.03, "train_n": 100},
                "btts_ft": {"intercept": -1.5, "coefficient": 0.02, "train_n": 100},
            }
            for mid in list(ACTIVE_CANDIDATE_IDS) + ["GI_E_PRIMARY_RECALIBRATED", "GI_F_REGULARIZED_PILLARS"]
        },
        normalization_payload={
            "feature_ecdfs": {
                k: {"values": [0.0, 1.0, 2.0, 3.0], "n": 4}
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
    )

    extracted = extract_v4_with_provenance(snap, proxy_cache=cache)
    fake_pred = {
        "five_models_available": True,
        "models": {
            mid: {"expected_total_goals": 2.5}
            for mid in (
                "GI_V4_EXPECTED_GOALS",
                "GI_A_STRICT_CORE",
                "GI_B_RECENCY",
                "GI_E_PRIMARY_RECALIBRATED",
                "GI_F_REGULARIZED_PILLARS",
            )
        },
    }
    with patch.object(svc, "score_five_models_with_frozen_bundle", return_value=fake_pred):
        out = svc._process_one_snapshot(
            snap=snap,
            bundle=bundle,
            bundle_hash="hash",
            proxy_cache=cache,
            source_code_commit="deadbeef",
        )
    assert out["included_in_main_cohort"] is True
    assert out["v4_source"] == V4_SOURCE_RECONSTRUCTED
    assert out["prediction_payload_json"]["v4_provenance"]["v4_source"] == V4_SOURCE_RECONSTRUCTED
    assert (
        out["prediction_payload_json"]["v4_provenance"]["expected_goals_total"]
        == extracted["expected_goals_total"]
    )


def test_incomplete_v5_is_diagnostic_exclusion_not_error():
    from app.models.cecchino_lab_goal_intensity_benchmark_job import ERROR_EXCLUSION_REASONS

    proxies = _season_proxies()
    target = proxies[28]
    cache = _cache_from_proxies(proxies)
    snap = _snap_for_target(proxies, target)
    snap.goal_intensity_compatibility_json = {
        "inputs": {"bundle_features": {"total_goals_avg": 2.5}}
    }
    bundle = MagicMock()
    bundle.candidate_definition_hash = "h"
    out = svc._process_one_snapshot(
        snap=snap,
        bundle=bundle,
        bundle_hash="h",
        proxy_cache=cache,
    )
    assert out["exclusion_reason"] == "incomplete_v5_features"
    assert out["exclusion_reason"] not in ERROR_EXCLUSION_REASONS
    assert out["included_in_main_cohort"] is False


def test_estimate_availability_counts_reconstructed_and_incomplete_v5():
    from app.services.cecchino.cecchino_goal_intensity_v5_phase_2c_candidates import (
        ACTIVE_CANDIDATE_IDS,
        ARCHIVED_CANDIDATE_IDS,
        DEVELOPMENT_PROTOCOL_VERSION,
        GI_F_ID,
        GI_F_PILLARS,
        TARGET_BUNDLE_VERSION,
    )
    from app.models.cecchino_goal_intensity_v5_preview import (
        BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
    )

    proxies = _season_proxies()
    cache = _cache_from_proxies(proxies)
    snaps = []
    for t in (proxies[26], proxies[28], proxies[30]):
        snaps.append(_snap_for_target(proxies, t))
    # one incomplete V5
    snaps[0].goal_intensity_compatibility_json = {
        "inputs": {"bundle_features": {"total_goals_avg": 1.0}}
    }

    weights = {p: round(1.0 / len(GI_F_PILLARS), 6) for p in GI_F_PILLARS}
    bundle = SimpleNamespace(
        id=1,
        version=TARGET_BUNDLE_VERSION,
        status=BUNDLE_STATUS_FROZEN_EXTERNAL_BENCHMARK_CANDIDATE,
        is_active=False,
        candidate_definition_hash="hash",
        fixture_ids_hash="fix",
        targets_hash="th",
        candidate_definitions_payload={
            "parent_bundle_id": 1,
            "parent_bundle_version": "v1",
            "development_protocol_version": DEVELOPMENT_PROTOCOL_VERSION,
            "active_candidate_ids": list(ACTIVE_CANDIDATE_IDS),
            "archived_candidate_ids": list(ARCHIVED_CANDIDATE_IDS),
            "intended_use": "historical_external_benchmark_only",
            "live_scoring_enabled": False,
            "signals_integration_enabled": False,
            "holdout_access_count": 1,
            "gi_f_weights": weights,
            "selected_alpha": 1.0,
            GI_F_ID: {"weights": weights, "selected_alpha": 1.0},
        },
        calibration_payload={
            mid: {
                "total_goals_ft": {"intercept": 0.5, "coefficient": 0.02, "train_n": 100},
                "goals_ge_2": {"intercept": -1.0, "coefficient": 0.03, "train_n": 100},
                "goals_ge_3": {"intercept": -2.0, "coefficient": 0.03, "train_n": 100},
                "btts_ft": {"intercept": -1.5, "coefficient": 0.02, "train_n": 100},
            }
            for mid in list(ACTIVE_CANDIDATE_IDS)
            + ["GI_E_PRIMARY_RECALIBRATED", "GI_F_REGULARIZED_PILLARS"]
        },
        normalization_payload={
            "feature_ecdfs": {
                k: {"values": [0.0, 1.0, 2.0, 3.0], "n": 4}
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
    )

    with patch.object(
        svc,
        "score_five_models_with_frozen_bundle",
        return_value={"five_models_available": True, "models": {}},
    ):
        avail = svc._estimate_availability(snaps, bundle, proxy_cache=cache)
    assert avail["v4_reconstructed_available"] >= 1
    assert avail["v4_total_available"] == avail["v4_rebuildable"]
    assert avail["missing_by_reason"].get("incomplete_v5_features", 0) >= 1
    assert avail["paired_complete_estimate"] >= 1
    assert avail["paired_coverage_pct"] > 0
    assert avail["proxy_cache_stats"]["competitions"] == 1
    assert avail["context_builder_version"] == CONTEXT_BUILDER_VERSION


def test_preflight_read_only_zero_writes_zero_api():
    db = MagicMock()
    run = SimpleNamespace(
        id=3,
        status="completed",
        season_label="2021/22",
        source_git_commit="abc",
    )
    with (
        patch.object(svc, "_load_run", return_value=run),
        patch.object(svc, "_require_completed_run"),
        patch.object(svc, "get_frozen_goal_intensity_candidate_bundle") as get_b,
        patch.object(svc, "validate_frozen_candidate_bundle", return_value={
            "is_active": False,
            "live_scoring_enabled": False,
            "intended_use": "historical_external_benchmark_only",
        }),
        patch.object(svc, "_load_snapshots", return_value=[]),
        patch.object(svc, "assess_independence", return_value={
            "status": "external_independent",
            "scientific_label": "external_validation",
            "overlap_count": 0,
            "overlap_pct": 0,
        }),
        patch.object(svc, "CompetitionProxyCache") as cache_cls,
        patch.object(svc, "select_pilot_snapshots", return_value={
            "requested": 300,
            "selected": 0,
            "snapshot_ids": [],
            "selection_hash": "x",
            "selection_protocol": "p",
            "competition_distribution": {},
            "month_distribution": {},
            "kickoff_range": {},
            "random_seed": 42,
        }),
        patch.object(svc, "resolve_code_revision", return_value={"git_commit": "deadbeef"}),
    ):
        cache = CompetitionProxyCache()
        cache_cls.build.return_value = cache
        get_b.return_value = SimpleNamespace(
            id=1,
            version="v",
            status="frozen",
            is_active=False,
            candidate_definition_hash="h",
        )
        # ensure no writes
        db.add = MagicMock(side_effect=AssertionError("db.write"))
        db.commit = MagicMock(side_effect=AssertionError("db.commit"))
        out = svc.build_goal_intensity_benchmark_preflight(db, 3)
    assert out["checks"]["external_api_calls"] == 0
    assert out["checks"]["base_run_writes"] == 0
    assert out["checks"]["full_scan_restarted"] is False
    assert out["v4_provenance_manifest"]["external_api_calls"] == 0
    assert cache.external_api_calls == 0


def test_extract_v4_compat_tuple_without_cache():
    snap = SimpleNamespace(
        cecchino_output_json={},
        goal_intensity_compatibility_json={},
        module_availability_json={},
        balance_v5_json={},
        historical_kpi_json={},
        input_snapshot_json={},
    )
    v4, reason = extract_v4_from_historical_snapshot(snap)
    assert v4 is None
    assert reason == "missing_persisted_v4_expected_goals"
