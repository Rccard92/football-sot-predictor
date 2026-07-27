"""Test snapshot v2 e confronto con v1.1."""

from __future__ import annotations

from copy import deepcopy

from app.schemas.cecchino_purchasability_v2 import (
    PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
    PURCHASABILITY_V2_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v2_normalization import (
    build_empty_provisional_profile,
)
from app.services.cecchino.cecchino_purchasability_v2_snapshot import (
    attach_purchasability_preview_v2_to_output,
    build_candidate_and_compact_snapshot_v2,
    build_purchasability_comparison,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_HOME


def _panel() -> dict:
    return {
        "rows": [
            {
                "market_key": SEL_HOME,
                "rating": 60,
                "edge_pct": 4,
                "vantaggio_prob": 0.03,
                "prob_cecchino": 0.4,
                "quota_book": 2.4,
                "quota_cecchino": 2.2,
                "prob_book": 0.4167,
            },
            {
                "market_key": SEL_AWAY,
                "rating": 75,
                "edge_pct": 10,
                "vantaggio_prob": 0.06,
                "prob_cecchino": 0.35,
                "quota_book": 3.0,
                "quota_cecchino": 2.6,
                "prob_book": 0.333,
            },
            {
                "market_key": "DRAW",
                "rating": 50,
                "edge_pct": 1,
                "vantaggio_prob": 0.01,
                "prob_cecchino": 0.25,
                "quota_book": 3.5,
                "quota_cecchino": 3.4,
                "prob_book": 0.2857,
            },
        ]
    }


def test_snapshot_v2_separate_key_preserves_v1():
    profile = build_empty_provisional_profile()
    v1_snapshot = {
        "snapshot_version": "cecchino_purchasability_snapshot_v1",
        "candidate_version": "cecchino_purchasability_v1_preview_candidate_2",
        "candidate_name": "balanced_geometric_v1_1",
        "status": "ok",
        "items": [{"market_key": SEL_AWAY, "score": 64, "status": "available"}],
        "marker": "v1_byte_marker_xyz",
    }
    output = {"purchasability_preview": deepcopy(v1_snapshot), "other": 1}
    attach_purchasability_preview_v2_to_output(
        cecchino_output=output,
        kpi_panel=_panel(),
        fixture_meta={"kickoff": "2099-01-01T20:00:00+00:00", "today_fixture_id": 1},
        snapshot_info={
            "snapshot_at": "2099-01-01T10:00:00+00:00",
            "snapshot_timestamp_verified": True,
        },
        profile=profile,
    )
    assert output["purchasability_preview"]["marker"] == "v1_byte_marker_xyz"
    assert "purchasability_preview_v2" in output
    assert (
        output["purchasability_preview_v2"]["snapshot_version"]
        == PURCHASABILITY_V2_SNAPSHOT_VERSION
    )
    assert (
        output["purchasability_preview_v2"]["candidate_version"]
        == PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION
    )
    # v2 must not appear inside v1
    assert "purchasability_preview_v2" not in str(output["purchasability_preview"].keys())


def test_post_kickoff_preserves_v2():
    profile = build_empty_provisional_profile()
    existing = {
        "snapshot_version": PURCHASABILITY_V2_SNAPSHOT_VERSION,
        "candidate_version": PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
        "candidate_name": "decision_quality_v2",
        "status": "ok",
        "items": [{"market_key": SEL_AWAY, "score": 72, "status": "available"}],
        "frozen": True,
    }
    output: dict = {}
    attach_purchasability_preview_v2_to_output(
        cecchino_output=output,
        kpi_panel=_panel(),
        fixture_meta={"kickoff": "2020-01-01T12:00:00+00:00"},
        snapshot_info={
            "snapshot_at": "2020-01-01T18:00:00+00:00",
            "snapshot_timestamp_verified": True,
        },
        existing_preview_v2=existing,
        profile=profile,
    )
    assert output["purchasability_preview_v2"].get("frozen") is True


def test_comparison_delta():
    v1 = {
        "items": [
            {"market_key": SEL_AWAY, "score": 64},
            {"market_key": SEL_HOME, "score": 50},
        ]
    }
    v2 = {
        "items": [
            {"market_key": SEL_AWAY, "score": 72},
            {"market_key": SEL_HOME, "score": 50},
        ]
    }
    cmp = build_purchasability_comparison(v1, v2)
    assert cmp["items"][SEL_AWAY]["delta_v2_minus_v1_1"] == 8
    assert cmp["items"][SEL_HOME]["delta_v2_minus_v1_1"] == 0
    assert cmp["items"][SEL_AWAY]["comparison_status"] == "available"

    cmp2 = build_purchasability_comparison(v1, {"items": [{"market_key": SEL_AWAY}]})
    assert cmp2["items"][SEL_AWAY]["delta_v2_minus_v1_1"] is None
    assert cmp2["items"][SEL_AWAY]["comparison_status"] == "partial"


def test_json_safe_no_nan():
    profile = build_empty_provisional_profile()
    _batch, snap = build_candidate_and_compact_snapshot_v2(
        kpi_panel=_panel(),
        profile=profile,
    )
    import json

    json.dumps(snap)
