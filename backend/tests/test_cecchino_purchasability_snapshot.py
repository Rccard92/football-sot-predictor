"""Test snapshot + persistenza + regressione compact 10531 — Fase 4."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from app.services.cecchino.cecchino_purchasability_candidate import (
    ACTIVE_PURCHASABILITY_CANDIDATE_VERSION,
    PURCHASABILITY_CANDIDATE_V2_VERSION,
    calculate_purchasability_candidate_batch,
    calculate_purchasability_candidate_item,
)
from app.services.cecchino.cecchino_purchasability_snapshot import (
    PURCHASABILITY_SNAPSHOT_VERSION,
    attach_purchasability_preview_to_output,
    build_purchasability_preview_snapshot,
    canonical_candidate_batch_sha256,
    index_purchasability_snapshot_by_market,
    resolve_purchasability_preview_for_detail,
    validate_purchasability_preview_snapshot,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)


def _dq(**kw):
    base = {
        "today_fixture_id": 10531,
        "snapshot_at": "2026-03-15T12:00:00+00:00",
        "snapshot_timestamp_verified": True,
        "snapshot_before_kickoff": True,
        "pre_match_only": True,
        "contains_settlement_fields": False,
        "contains_result_fields": False,
    }
    base.update(kw)
    return base


def _item(
    market_key,
    *,
    edge=0.0,
    pc=0.45,
    mcp=0.45,
    opm=0.30,
    opb=0.30,
    fa="aligned",
    comps=None,
    intensity=0.40,
    book_fav=None,
    feature_status="ready",
):
    if comps is None:
        comps = [SEL_DRAW, SEL_AWAY] if market_key == SEL_HOME else [SEL_HOME, SEL_AWAY]
    return {
        "market_key": market_key,
        "selection": market_key,
        "feature_status": feature_status,
        "status": "not_calculated",
        "phase_1_value": {
            "status": "available",
            "inputs": {
                "prob_cecchino": pc,
                "edge_pct": edge,
                "rating": 70,
                "score_acquisto": 0.01,
            },
        },
        "phase_2_quality": {
            "status": "available",
            "model_context_probability": mcp,
            "opposition_pressure_model": opm,
            "opposition_pressure_book": opb,
            "favourite_alignment": fa,
            "favourite_intensity_book": intensity,
            "book_favourite": {
                "selection": book_fav or SEL_AWAY,
                "implied_prob": intensity,
            },
            "comparator_selections": comps,
            "absolute_model_book_gap": 0.12,
            "model_book_gap": 0.12,
            "gap_direction": "positive",
        },
        "data_quality": _dq(),
        "reason_codes": [],
        "context_hooks": {},
    }


# Compact regression inputs calibrated for expected scores (candidate_2).
# Scores 0 → edge<=0; AWAY/X2≈59; UNDER_2_5≈58.
FIXTURE_10531_ITEMS = [
    _item(SEL_HOME, edge=0, pc=0.40, mcp=0.55, opm=0.28, opb=0.30),
    _item(SEL_DRAW, edge=0, pc=0.28, mcp=0.30, opm=0.40, opb=0.35, comps=[SEL_HOME, SEL_AWAY]),
    _item(
        SEL_AWAY,
        edge=8.2,
        pc=0.54,
        mcp=0.54,
        opm=0.28,
        opb=0.30,
        comps=[SEL_HOME, SEL_DRAW],
        book_fav=SEL_HOME,
        fa="aligned",
    ),
    _item(SEL_ONE_X, edge=0, pc=0.70, mcp=0.70, opm=0.25, opb=0.28, comps=[SEL_AWAY]),
    _item(
        SEL_X_TWO,
        edge=8.2,
        pc=0.54,
        mcp=0.54,
        opm=0.28,
        opb=0.30,
        comps=[SEL_HOME],
        book_fav=SEL_HOME,
    ),
    _item(SEL_ONE_TWO, edge=0, pc=0.75, mcp=0.75, opm=0.22, opb=0.25, comps=[SEL_DRAW]),
    _item(SEL_OVER_2_5, edge=0, pc=0.55, mcp=0.55, opm=0.45, opb=0.48, comps=[SEL_UNDER_2_5]),
    _item(
        SEL_UNDER_2_5,
        edge=8.3,
        pc=0.54,
        mcp=0.54,
        opm=0.35,
        opb=0.35,
        comps=[SEL_OVER_2_5],
        book_fav=SEL_OVER_2_5,
        intensity=0.35,
    ),
    _item(SEL_UNDER_PT_1_5, edge=0, pc=0.50, mcp=0.50, opm=0.40, opb=0.45, comps=[SEL_OVER_PT_1_5]),
    _item(SEL_OVER_PT_1_5, edge=0, pc=0.50, mcp=0.35, opm=0.50, opb=0.70, comps=[SEL_UNDER_PT_1_5]),
    _item(SEL_DRAW_PT, edge=5, feature_status="unavailable"),
    _item(SEL_OVER_1_5, edge=5, feature_status="unavailable"),
    _item(SEL_UNDER_3_5, edge=5, feature_status="unavailable"),
    _item(SEL_OVER_PT_0_5, edge=5, feature_status="unavailable"),
]

EXPECTED_10531 = {
    SEL_HOME: 0,
    SEL_DRAW: 0,
    SEL_AWAY: 59,
    SEL_ONE_X: 0,
    SEL_X_TWO: 59,
    SEL_ONE_TWO: 0,
    SEL_OVER_2_5: 0,
    SEL_UNDER_2_5: 58,
    SEL_UNDER_PT_1_5: 0,
    SEL_OVER_PT_1_5: 0,
}


def test_fixture_10531_scores():
    batch = calculate_purchasability_candidate_batch(
        {"today_fixture_id": 10531, "items": FIXTURE_10531_ITEMS}
    )
    assert batch["candidate_version"] == PURCHASABILITY_CANDIDATE_V2_VERSION
    assert batch["status"] in ("ok", "partial")
    by_m = {it["market_key"]: it for it in batch["items"]}
    for mk, exp in EXPECTED_10531.items():
        assert by_m[mk]["score"] == exp, f"{mk}: got {by_m[mk]['score']} expected {exp}"
    for mk in (SEL_DRAW_PT, SEL_OVER_1_5, SEL_UNDER_3_5, SEL_OVER_PT_0_5):
        assert by_m[mk]["status"] == "unavailable"
        assert by_m[mk]["score"] is None
    # partial batch still exposes available scores
    assert by_m[SEL_AWAY]["score"] == 59
    assert by_m[SEL_ONE_X]["score"] == 0
    assert "valore positivo" in (by_m[SEL_ONE_X]["reading"] or "").lower()


def test_snapshot_compact_and_hash():
    batch = calculate_purchasability_candidate_batch(
        {"today_fixture_id": 10531, "items": FIXTURE_10531_ITEMS[:3]}
    )
    snap = build_purchasability_preview_snapshot(batch)
    assert snap["snapshot_version"] == PURCHASABILITY_SNAPSHOT_VERSION
    assert snap["candidate_version"] == ACTIVE_PURCHASABILITY_CANDIDATE_VERSION
    assert snap["signals_integration"] is False
    assert snap["contains_settlement_fields"] is False
    assert "comparator_evidence" not in json.dumps(snap)
    assert "rating" not in json.dumps(snap.get("items"))
    h1 = snap["full_candidate_payload_sha256"]
    assert h1 == canonical_candidate_batch_sha256(batch)
    batch2 = copy.deepcopy(batch)
    batch2["items"][0]["phase_1_value"]["inputs"]["edge_pct"] = 99.0
    # recompute would change hash of original batch content — mutate batch then hash
    h2 = canonical_candidate_batch_sha256(batch2)
    assert h1 != h2
    assert validate_purchasability_preview_snapshot(snap)["ok"] is True
    idx = index_purchasability_snapshot_by_market(snap)
    assert SEL_HOME in idx
    # score 0 preserved
    zero_items = [i for i in snap["items"] if i["score"] == 0]
    assert len(zero_items) >= 1


def test_attach_pre_match_persists():
    output: dict = {"final": {}}
    panel = {"rows": [], "bookmaker": {"name": "x"}}
    attach_purchasability_preview_to_output(
        cecchino_output=output,
        kpi_panel=panel,
        fixture_meta={
            "today_fixture_id": 1,
            "kickoff": "2026-12-01T18:00:00+00:00",
        },
        snapshot_info={
            "snapshot_at": "2026-12-01T12:00:00+00:00",
            "snapshot_source": "odds_meta.odds_fetched_at",
            "snapshot_fidelity": "verified_panel_odds_meta",
            "snapshot_timestamp_verified": True,
        },
    )
    assert "purchasability_preview" in output
    assert output["purchasability_preview"]["candidate_version"] == (
        PURCHASABILITY_CANDIDATE_V2_VERSION
    )


def test_attach_post_kickoff_preserves_existing():
    existing = build_purchasability_preview_snapshot(
        calculate_purchasability_candidate_batch(
            {"today_fixture_id": 1, "items": [_item(SEL_AWAY, edge=12, pc=0.42)]}
        )
    )
    output: dict = {}
    attach_purchasability_preview_to_output(
        cecchino_output=output,
        kpi_panel={"rows": []},
        fixture_meta={"today_fixture_id": 1, "kickoff": "2020-01-01T12:00:00+00:00"},
        snapshot_info={
            "snapshot_at": "2026-01-01T12:00:00+00:00",  # after kickoff
            "snapshot_source": "x",
            "snapshot_fidelity": "verified_panel_odds_meta",
            "snapshot_timestamp_verified": True,
        },
        existing_preview=existing,
    )
    assert output["purchasability_preview"]["full_candidate_payload_sha256"] == (
        existing["full_candidate_payload_sha256"]
    )


def test_attach_post_kickoff_no_existing_skips():
    output: dict = {"final": {}}
    attach_purchasability_preview_to_output(
        cecchino_output=output,
        kpi_panel={"rows": []},
        fixture_meta={"today_fixture_id": 1, "kickoff": "2020-01-01T12:00:00+00:00"},
        snapshot_info={
            "snapshot_at": "2026-01-01T12:00:00+00:00",
            "snapshot_source": "x",
            "snapshot_fidelity": "verified_panel_odds_meta",
            "snapshot_timestamp_verified": True,
        },
        existing_preview=None,
    )
    assert "purchasability_preview" not in output


def test_resolve_detail_persisted():
    snap = build_purchasability_preview_snapshot(
        calculate_purchasability_candidate_batch(
            {"today_fixture_id": 10531, "items": [_item(SEL_AWAY, edge=12, pc=0.42)]}
        )
    )
    row = SimpleNamespace(
        id=10531,
        cecchino_output_json={"purchasability_preview": snap},
        kpi_panel_json={"rows": []},
        odds_snapshot_json={
            "odds_meta": {"odds_fetched_at": "2026-03-15T12:00:00+00:00"}
        },
        local_fixture_id=1,
        provider_fixture_id=2,
        competition_id=3,
        scan_date=None,
        kickoff=None,
        odds_checked_at=None,
        updated_at=None,
    )
    out = resolve_purchasability_preview_for_detail(row=row, kpi_panel={"rows": []})
    assert out["source_mode"] == "persisted_pre_match_snapshot"
    assert out["items"][0]["score"] == snap["items"][0]["score"]


def test_resolve_detail_derived_no_commit():
    from datetime import datetime, timezone

    row = SimpleNamespace(
        id=99,
        cecchino_output_json={},
        kpi_panel_json={
            "bookmaker": {"name": "Betfair"},
            "rows": [
                {
                    "market_key": SEL_HOME,
                    "quota_book": 2.1,
                    "quota_cecchino": 1.95,
                    "prob_book": 0.45,
                    "prob_cecchino": 0.48,
                    "vantaggio_prob": 0.03,
                    "edge_pct": 7.0,
                    "score_acquisto": 0.03,
                    "rating": 70,
                    "status": "ok",
                },
                {
                    "market_key": SEL_DRAW,
                    "quota_book": 3.4,
                    "quota_cecchino": 3.2,
                    "prob_book": 0.29,
                    "prob_cecchino": 0.30,
                    "edge_pct": 5.0,
                    "score_acquisto": 0.02,
                    "rating": 60,
                    "status": "ok",
                },
                {
                    "market_key": SEL_AWAY,
                    "quota_book": 3.6,
                    "quota_cecchino": 3.5,
                    "prob_book": 0.27,
                    "prob_cecchino": 0.22,
                    "edge_pct": 2.0,
                    "score_acquisto": 0.01,
                    "rating": 55,
                    "status": "ok",
                },
            ],
            "odds_meta": {"odds_fetched_at": "2026-03-15T12:00:00+00:00"},
        },
        odds_snapshot_json={
            "odds_meta": {"odds_fetched_at": "2026-03-15T12:00:00+00:00"}
        },
        local_fixture_id=1,
        provider_fixture_id=2,
        competition_id=3,
        scan_date="2026-03-15",
        kickoff=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
        odds_checked_at=None,
        updated_at=None,
    )
    out = resolve_purchasability_preview_for_detail(
        row=row, kpi_panel=row.kpi_panel_json
    )
    assert out["source_mode"] == "derived_read_only_from_stored_snapshot"
    assert row.cecchino_output_json == {}  # no persist
    assert out["status"] in ("ok", "partial", "unavailable")
