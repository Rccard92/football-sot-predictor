"""Test normalizzazione storica Acquistabilità v2."""

from __future__ import annotations

import math

from app.services.cecchino.cecchino_purchasability_v2_normalization import (
    PROVISIONAL_CAPS,
    build_empty_provisional_profile,
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
