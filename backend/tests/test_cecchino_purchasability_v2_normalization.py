"""Test normalizzazione storica Acquistabilità v2."""

from __future__ import annotations

import inspect
import math
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.schemas.cecchino_purchasability_v2 import (
    PURCHASABILITY_V2_NORM_PROFILE_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v2_normalization import (
    PROVISIONAL_CAPS,
    build_empty_provisional_profile,
    build_normalization_profile_from_rows,
    compute_profile_hash,
    finalize_profile_from_accumulator,
    get_or_build_normalization_profile,
    invalidate_v2_norm_profile_cache,
    nearest_rank_percentile,
    normalize_component_value,
    resolve_caps_for_component,
    zero_anchored_normalize,
)


def test_zero_maps_to_50():
    n, clip = zero_anchored_normalize(0.0, positive_cap=20.0, negative_cap=20.0)
    assert n == 50.0
    assert clip is False


def test_positive_cap_to_100_and_clip():
    n, clip = zero_anchored_normalize(20.0, positive_cap=20.0, negative_cap=10.0)
    assert n == 100.0
    assert clip is False
    n2, clip2 = zero_anchored_normalize(40.0, positive_cap=20.0, negative_cap=10.0)
    assert n2 == 100.0
    assert clip2 is True


def test_negative_cap_to_0_and_clip():
    n, clip = zero_anchored_normalize(-10.0, positive_cap=20.0, negative_cap=10.0)
    assert n == 0.0
    assert clip is False
    n2, clip2 = zero_anchored_normalize(-30.0, positive_cap=20.0, negative_cap=10.0)
    assert n2 == 0.0
    assert clip2 is True


def test_nearest_rank_percentile():
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    # ceil(0.95 * 20) = 19 → index 18 → 19
    assert nearest_rank_percentile(vals, 0.95) == 19
    assert nearest_rank_percentile([], 0.95) is None


def test_provisional_fallback_and_cache():
    invalidate_v2_norm_profile_cache()
    profile = build_empty_provisional_profile()
    caps = resolve_caps_for_component(profile, component="edge_pct", scope="OUTCOMES")
    assert caps["cap_source"] == "provisional_versioned_fallback"
    assert caps["positive_cap"] == PROVISIONAL_CAPS["edge_pct"]

    # Cache
    p1 = get_or_build_normalization_profile(None)
    p2 = get_or_build_normalization_profile(None)
    assert p1["hash"] == p2["hash"]
    invalidate_v2_norm_profile_cache()
    p3 = get_or_build_normalization_profile(None)
    assert p3["hash"] == p1["hash"]  # deterministic empty profile


def test_scope_vs_global_fallback():
    from app.services.cecchino.cecchino_purchasability_v2_normalization import (
        _new_accumulator,
        _push_value,
    )

    acc = _new_accumulator()
    for i in range(20):
        _push_value(acc["by_component_scope"]["edge_pct::OUTCOMES"], float(i + 1))
        _push_value(acc["by_component_scope"]["edge_pct::OUTCOMES"], float(-(i + 1)))
        _push_value(acc["by_component_global"]["edge_pct"], float(i + 1))
        _push_value(acc["by_component_global"]["edge_pct"], float(-(i + 1)))
    profile = finalize_profile_from_accumulator(acc, fixtures_seen=1)
    caps_scope = resolve_caps_for_component(profile, component="edge_pct", scope="OUTCOMES")
    assert caps_scope["cap_source"] == "historical_scope"
    caps_ft = resolve_caps_for_component(profile, component="edge_pct", scope="GOALS_FT_2_5")
    assert caps_ft["cap_source"] == "historical_global_fallback"


def test_normalize_component_trace_fields():
    profile = build_empty_provisional_profile()
    trace = normalize_component_value(
        10.0, component="edge_pct", scope="OUTCOMES", profile=profile
    )
    assert trace["raw_value"] == 10.0
    assert trace["normalized_value"] == 75.0  # 50 + 50*(10/20)
    assert trace["cap_source"] == "provisional_versioned_fallback"
    assert "profile_version" in trace


def test_profile_hash_deterministic():
    p1 = build_empty_provisional_profile()
    p2 = build_empty_provisional_profile()
    assert compute_profile_hash(p1) == compute_profile_hash(p2)
    assert p1["cutoff"] == "2026-07-26"
    assert p1["excludes_cecchino_lab"] is True
    assert p1["excludes_post_match"] is True


def test_no_nan_infinity():
    n, _ = zero_anchored_normalize(5.0, positive_cap=20.0, negative_cap=20.0)
    assert math.isfinite(n)


def test_profile_version_is_v2():
    assert (
        PURCHASABILITY_V2_NORM_PROFILE_VERSION
        == "cecchino_purchasability_v2_norm_profile_2026_07_26_v2"
    )
    p = build_empty_provisional_profile()
    assert p["version"] == PURCHASABILITY_V2_NORM_PROFILE_VERSION


def test_cache_invalidated_by_version_change():
    invalidate_v2_norm_profile_cache()
    p1 = get_or_build_normalization_profile(None)
    assert "v2" in p1["version"]
    # Nuova chiave cache con versione diversa
    p_other = get_or_build_normalization_profile(
        None, version="cecchino_purchasability_v2_norm_profile_2026_07_26_v1"
    )
    assert p_other["version"].endswith("_v1")
    assert p1["hash"] != p_other["hash"] or p1["version"] != p_other["version"]


def _verified_panel():
    snap = datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc)
    return {
        "rows": [
            {
                "market_key": "HOME",
                "rating": 70,
                "edge_pct": 5.0,
                "vantaggio_prob": 0.02,
                "prob_cecchino": 0.4,
                "prob_book": 0.38,
                "quota_book": 2.5,
            },
            {
                "market_key": "DRAW",
                "rating": 55,
                "edge_pct": 1.0,
                "vantaggio_prob": 0.01,
                "prob_cecchino": 0.28,
                "prob_book": 0.29,
                "quota_book": 3.4,
            },
            {
                "market_key": "AWAY",
                "rating": 60,
                "edge_pct": 3.0,
                "vantaggio_prob": 0.015,
                "prob_cecchino": 0.32,
                "prob_book": 0.33,
                "quota_book": 3.0,
            },
        ],
        "odds_meta": {"odds_fetched_at": snap.isoformat()},
    }


def _row_fixture(**kwargs):
    base = {
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "kpi_panel_json": _verified_panel(),
        "odds_snapshot_json": None,
        "odds_checked_at": None,
        "updated_at": datetime(2026, 7, 20, 19, 0, 0, tzinfo=timezone.utc),
        "kickoff": datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc),
        "result_json": {"home_goals": 1},  # non deve essere letto
        "settlement_json": {"won": True},
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_build_from_rows_includes_verified_eligible():
    rows = [_row_fixture()]
    profile = build_normalization_profile_from_rows(rows)
    assert profile["fixtures_seen"] == 1
    assert profile["accepted_pre_match_rows"] == 1
    assert profile["eligible_rows_seen"] == 1
    assert profile["rows_seen"] == 1
    assert profile["excludes_post_match"] is True
    assert profile["excludes_cecchino_lab"] is True
    assert profile["summary"]["accepted_pre_match_rows"] == 1


def test_excluded_with_kpi_skipped():
    rows = [
        _row_fixture(eligibility_status="excluded"),
        _row_fixture(),
    ]
    profile = build_normalization_profile_from_rows(rows)
    assert profile["rows_seen"] == 2
    assert profile["eligible_rows_seen"] == 1
    assert profile["fixtures_seen"] == 1
    assert profile["accepted_pre_match_rows"] == 1


def test_unverified_timestamp_excluded():
    rows = [
        _row_fixture(
            kpi_panel_json={"rows": [{"market_key": "HOME", "edge_pct": 5}]},
            odds_checked_at=None,
            updated_at=datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc),
        )
    ]
    profile = build_normalization_profile_from_rows(rows)
    assert profile["fixtures_seen"] == 0
    assert profile["rejected_snapshot_unverified"] == 1
    assert profile["accepted_pre_match_rows"] == 0


def test_post_kickoff_excluded():
    kick = datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc)
    snap = datetime(2026, 7, 20, 19, 0, 0, tzinfo=timezone.utc)
    rows = [
        _row_fixture(
            kickoff=kick,
            kpi_panel_json={
                "rows": [{"market_key": "HOME", "edge_pct": 5, "rating": 70}],
                "odds_meta": {"odds_fetched_at": snap.isoformat()},
            },
        )
    ]
    profile = build_normalization_profile_from_rows(rows)
    assert profile["fixtures_seen"] == 0
    assert profile["rejected_not_before_kickoff"] == 1


def test_kickoff_missing_excluded():
    rows = [_row_fixture(kickoff=None)]
    profile = build_normalization_profile_from_rows(rows)
    assert profile["fixtures_seen"] == 0
    assert profile["rejected_kickoff_missing"] == 1


def test_fixtures_seen_counts_only_accepted():
    rows = [
        _row_fixture(),
        _row_fixture(eligibility_status="excluded"),
        _row_fixture(kickoff=None),
        _row_fixture(
            kpi_panel_json={"rows": [{"market_key": "HOME"}]},
            updated_at=datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc),
        ),
    ]
    profile = build_normalization_profile_from_rows(rows)
    assert profile["fixtures_seen"] == profile["accepted_pre_match_rows"]
    assert profile["fixtures_seen"] == 1
    assert profile["rows_seen"] == 4


def test_no_cecchino_lab_access_in_builder():
    src = inspect.getsource(build_normalization_profile_from_rows)
    assert "cecchino_lab" not in src.lower()
    assert "cecchino_data_lab" not in src.lower()


def test_db_query_filters_eligibility():
    from app.services.cecchino import cecchino_purchasability_v2_normalization as mod

    src = inspect.getsource(mod.build_normalization_profile_from_db)
    assert "ELIGIBILITY_ELIGIBLE" in src
    assert "eligibility_status" in src


def test_profile_hash_deterministic_with_diagnostics():
    rows = [_row_fixture()]
    p1 = build_normalization_profile_from_rows(rows)
    p2 = build_normalization_profile_from_rows(rows)
    assert p1["hash"] == p2["hash"]
    assert compute_profile_hash(p1) == p1["hash"]
