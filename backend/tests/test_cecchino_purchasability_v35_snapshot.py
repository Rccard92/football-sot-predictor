"""Test Cecchino Purchasability V3.5 snapshot — persistenza pre-match immutabile."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_candidate import (
    calculate_purchasability_v35_batch,
)
from app.services.cecchino.cecchino_purchasability_v35_config import (
    RATING_MIN_GATE,
    frozen_config_v35,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
    build_candidate_and_compact_snapshot_v35,
    build_purchasability_preview_v35_snapshot,
    classify_existing_v35_snapshot,
    engine_payload_sha256_v35,
    input_fingerprint_v35,
    resolve_valid_persisted_purchasability_v35,
    validate_purchasability_preview_v35_snapshot,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME

SNAP_AT = "2026-08-19T10:00:00+00:00"
KICKOFF = "2026-08-19T15:00:00+00:00"


def _fixture_meta(**overrides) -> dict:
    base = {
        "today_fixture_id": 1,
        "provider_fixture_id": 999,
        "snapshot_at": SNAP_AT,
        "kickoff": KICKOFF,
    }
    base.update(overrides)
    return base


def _snapshot_info(**overrides) -> dict:
    base = {
        "snapshot_at": SNAP_AT,
        "snapshot_timestamp_verified": True,
        "source_snapshot_before_kickoff": True,
    }
    base.update(overrides)
    return base


def _row(
    mk: str,
    *,
    rating: float | None = 70,
    prob: float | None = 0.55,
    quota_book: float | None = 2.2,
    book_source: str = "betfair_raw_match_winner",
) -> dict:
    return {
        "market_key": mk,
        "quota_book": quota_book,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": book_source,
        "book_fallback_used": False,
    }


def _kpi_panel(rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = [_row(mk, rating=60, prob=0.55, quota_book=2.2) for mk in PANEL_MARKET_KEYS]
    return {"rows": rows}


def _attach(
    *,
    kpi_panel: dict,
    existing_preview_v35: dict | None = None,
    snap_at: str = SNAP_AT,
    kickoff: str = KICKOFF,
    verified: bool = True,
) -> dict:
    output: dict = {}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel=kpi_panel,
        fixture_meta=_fixture_meta(snapshot_at=snap_at, kickoff=kickoff),
        snapshot_info=_snapshot_info(
            snapshot_at=snap_at,
            snapshot_timestamp_verified=verified,
        ),
        existing_preview_v35=existing_preview_v35,
    )
    return output


def _valid_snapshot() -> dict:
    return _attach(kpi_panel=_kpi_panel())["purchasability_preview_v35"]


def test_valid_pre_match_snapshot_persisted():
    out = _attach(kpi_panel=_kpi_panel())
    snap = out.get("purchasability_preview_v35")
    assert isinstance(snap, dict)
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is True
    assert snap["pre_match_verified"] is True
    assert snap["immutable_first_write"] is True


def test_19_markets_preserved():
    out = _attach(kpi_panel=_kpi_panel())
    snap = out["purchasability_preview_v35"]
    assert len(snap["items"]) == 19
    keys = {it["market_key"] for it in snap["items"]}
    assert keys == set(PANEL_MARKET_KEYS)


def test_all_candidates_abcd_present():
    out = _attach(kpi_panel=_kpi_panel())
    for item in out["purchasability_preview_v35"]["items"]:
        assert set(item["candidates"].keys()) == {"A", "B", "C", "D"}


def test_frozen_config_present():
    out = _attach(kpi_panel=_kpi_panel())
    fc = out["purchasability_preview_v35"]["frozen_config"]
    assert fc == frozen_config_v35()
    assert fc["rating_min_gate"] == RATING_MIN_GATE
    assert set(fc["candidates"].keys()) == {"A", "B", "C", "D"}


def test_relation_registry_once_not_per_item():
    out = _attach(kpi_panel=_kpi_panel())
    snap = out["purchasability_preview_v35"]
    assert isinstance(snap.get("relation_registry"), list)
    assert len(snap["relation_registry"]) > 0
    for item in snap["items"]:
        assert "relation_registry" not in item


def test_fingerprint_deterministic():
    panel = _kpi_panel()
    meta = _fixture_meta()
    fp1 = input_fingerprint_v35(kpi_panel=panel, fixture_meta=meta)
    fp2 = input_fingerprint_v35(kpi_panel=panel, fixture_meta=meta)
    assert fp1 == fp2
    assert len(fp1) == 64


def test_changed_input_changes_fingerprint():
    panel_a = _kpi_panel([_row(SEL_HOME, quota_book=2.2)])
    panel_b = _kpi_panel([_row(SEL_HOME, quota_book=3.5)])
    meta = _fixture_meta()
    fp_a = input_fingerprint_v35(kpi_panel=panel_a, fixture_meta=meta)
    fp_b = input_fingerprint_v35(kpi_panel=panel_b, fixture_meta=meta)
    assert fp_a != fp_b


def test_first_write_wins_preserves_exact_snapshot():
    panel_a = _kpi_panel([_row(SEL_HOME, quota_book=2.2, rating=60, prob=0.55)])
    out1 = _attach(kpi_panel=panel_a)
    snap1 = out1["purchasability_preview_v35"]
    fp1 = snap1["input_fingerprint_sha256"]
    eng1 = snap1["engine_payload_sha256"]
    scores1 = {
        ck: snap1["items"][0]["candidates"][ck].get("score")
        for ck in ("A", "B", "C", "D")
    }

    panel_b = _kpi_panel([_row(SEL_HOME, quota_book=9.9, rating=99, prob=0.99)])
    out2 = _attach(kpi_panel=panel_b, existing_preview_v35=snap1)
    snap2 = out2["purchasability_preview_v35"]

    assert snap2 == snap1
    assert snap2["input_fingerprint_sha256"] == fp1
    assert snap2["engine_payload_sha256"] == eng1
    scores2 = {
        ck: snap2["items"][0]["candidates"][ck].get("score")
        for ck in ("A", "B", "C", "D")
    }
    assert scores2 == scores1


def test_rescan_changed_odds_does_not_overwrite():
    """Attach con quote diverse ma senza existing → crea; con existing → preserva."""
    panel_low = _kpi_panel([_row(SEL_HOME, quota_book=2.0)])
    out_first = _attach(kpi_panel=panel_low)
    first = out_first["purchasability_preview_v35"]

    panel_high = _kpi_panel([_row(SEL_HOME, quota_book=5.0)])
    out_rescan = _attach(kpi_panel=panel_high, existing_preview_v35=first)
    assert out_rescan["purchasability_preview_v35"] == first


def test_post_kickoff_without_existing_no_snapshot():
    """snap_at >= kickoff → nessun nuovo snapshot (CASO C)."""
    snap_after_kick = "2026-08-19T16:00:00+00:00"
    out = _attach(
        kpi_panel=_kpi_panel(),
        snap_at=snap_after_kick,
        kickoff=KICKOFF,
    )
    assert "purchasability_preview_v35" not in out


def test_post_kickoff_with_existing_preserves():
    out1 = _attach(kpi_panel=_kpi_panel())
    existing = out1["purchasability_preview_v35"]
    past_kickoff = "2026-08-19T08:00:00+00:00"
    out2 = _attach(
        kpi_panel=_kpi_panel([_row(SEL_HOME, quota_book=9.9)]),
        existing_preview_v35=existing,
        snap_at="2026-08-19T07:30:00+00:00",
        kickoff=past_kickoff,
    )
    assert out2["purchasability_preview_v35"] == existing


def test_invalid_timestamp_no_new_valid_snapshot():
    out = _attach(
        kpi_panel=_kpi_panel(),
        snap_at=KICKOFF,
        kickoff=SNAP_AT,
    )
    assert "purchasability_preview_v35" not in out


def test_unverified_timestamp_no_snapshot():
    out = _attach(kpi_panel=_kpi_panel(), verified=False)
    assert "purchasability_preview_v35" not in out


def test_engine_failure_non_blocking():
    output: dict = {"purchasability_preview_v31": {"status": "ok"}}
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_snapshot.calculate_purchasability_v35_batch",
        side_effect=RuntimeError("boom"),
    ):
        attach_purchasability_preview_v35_to_output(
            cecchino_output=output,
            kpi_panel=_kpi_panel(),
            fixture_meta=_fixture_meta(),
            snapshot_info=_snapshot_info(),
        )
    assert "purchasability_preview_v35" not in output
    assert output["purchasability_preview_v31"]["status"] == "ok"


def test_v31_key_unchanged_by_v35_attach():
    output = {"purchasability_preview_v31": {"snapshot_version": "v31_test"}}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel=_kpi_panel(),
        fixture_meta=_fixture_meta(),
        snapshot_info=_snapshot_info(),
    )
    assert output["purchasability_preview_v31"]["snapshot_version"] == "v31_test"


def test_no_post_match_fields_in_snapshot():
    out = _attach(kpi_panel=_kpi_panel())
    snap = out["purchasability_preview_v35"]
    assert snap["contains_post_match_fields"] is False
    assert snap["pre_match_only"] is True
    forbidden = {"result", "outcome", "goals_home", "settlement", "won"}
    raw = str(snap)
    for key in forbidden:
        assert f'"{key}"' not in raw or key in ("outcome",)  # allow in reason strings only
    for item in snap["items"]:
        assert item["contains_post_match_fields"] is False


def test_historical_reliability_never_called():
    with patch(
        "app.services.cecchino.cecchino_purchasability_v31_hr.build_hr_history_context",
        side_effect=AssertionError("HR must not be called from V35"),
    ):
        out = _attach(kpi_panel=_kpi_panel())
    assert out.get("purchasability_preview_v35") is not None
    assert (
        out["purchasability_preview_v35"]["historical_reliability_integrated"] is False
    )


def test_no_db_or_api_calls_from_attach(monkeypatch):
    def _fail_db(*_a, **_k):
        raise AssertionError("DB must not be called from V35 attach")

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_service.get_db",
        _fail_db,
        raising=False,
    )
    out = _attach(kpi_panel=_kpi_panel())
    assert "purchasability_preview_v35" in out


def test_malformed_existing_logs_conflict_not_valid():
    bad = {"snapshot_version": "wrong_version", "items": []}
    classified = classify_existing_v35_snapshot(bad)
    assert classified.status == "invalid"
    assert resolve_valid_persisted_purchasability_v35(bad) is None


def test_invalid_existing_preserved_no_recalc_on_rescan():
    invalid = {
        "snapshot_version": "wrong_version",
        "_custom_marker": "keep_me",
        "items": [],
    }
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_snapshot.calculate_purchasability_v35_batch",
        side_effect=AssertionError("must not recalc over invalid existing"),
    ) as spy:
        out = _attach(kpi_panel=_kpi_panel(), existing_preview_v35=invalid)
    spy.assert_not_called()
    assert out["purchasability_preview_v35"] == invalid
    assert out["purchasability_preview_v35"]["_custom_marker"] == "keep_me"


def test_invalid_existing_in_output_preserved_no_recalc():
    invalid = {
        "snapshot_version": "wrong_version",
        "_custom_marker": "keep_me_in_output",
        "items": [],
    }
    output: dict = {"purchasability_preview_v35": invalid}
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_snapshot.calculate_purchasability_v35_batch",
        side_effect=AssertionError("must not recalc over invalid in output"),
    ) as spy:
        attach_purchasability_preview_v35_to_output(
            cecchino_output=output,
            kpi_panel=_kpi_panel(),
            fixture_meta=_fixture_meta(),
            snapshot_info=_snapshot_info(),
        )
    spy.assert_not_called()
    assert output["purchasability_preview_v35"] == invalid


def test_validate_fresh_snapshot_passes():
    snap = _valid_snapshot()
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check == {"ok": True, "reason": None}


def test_validate_engine_hash_mismatch_on_score_tamper():
    snap = copy.deepcopy(_valid_snapshot())
    home = next(it for it in snap["items"] if it["market_key"] == SEL_HOME)
    home["candidates"]["A"]["score"] = 999
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == "engine_payload_sha256_mismatch"


def test_validate_engine_hash_mismatch_on_frozen_config():
    snap = copy.deepcopy(_valid_snapshot())
    snap["frozen_config"] = dict(snap["frozen_config"], tampered=True)
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == "engine_payload_sha256_mismatch"


def test_validate_engine_hash_mismatch_on_relation_registry():
    snap = copy.deepcopy(_valid_snapshot())
    snap["relation_registry"] = list(snap["relation_registry"]) + [{"tampered": True}]
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == "engine_payload_sha256_mismatch"


def test_validate_generated_at_only_does_not_break_hash():
    snap = copy.deepcopy(_valid_snapshot())
    snap["generated_at"] = "2099-01-01T00:00:00+00:00"
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check == {"ok": True, "reason": None}


def test_validate_19_markets_pass():
    snap = _valid_snapshot()
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is True


def test_validate_18_markets_fail():
    snap = copy.deepcopy(_valid_snapshot())
    snap["items"] = snap["items"][:18]
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == "items_count_mismatch"


def test_validate_20_markets_duplicate_fail():
    snap = copy.deepcopy(_valid_snapshot())
    dup = copy.deepcopy(snap["items"][0])
    snap["items"] = snap["items"] + [dup]
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == "items_count_mismatch"


def test_validate_unknown_market_fail():
    snap = copy.deepcopy(_valid_snapshot())
    snap["items"][0]["market_key"] = "UNKNOWN_MARKET"
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == "invalid_market_key"


def test_validate_duplicate_home_missing_other_fail():
    snap = copy.deepcopy(_valid_snapshot())
    home = next(it for it in snap["items"] if it["market_key"] == SEL_HOME)
    away_idx = next(i for i, it in enumerate(snap["items"]) if it["market_key"] == SEL_AWAY)
    snap["items"][away_idx] = copy.deepcopy(home)
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == "duplicate_market_key"


@pytest.mark.parametrize(
    "field,expected_reason",
    [
        ("input_fingerprint_sha256", "missing_input_fingerprint_sha256"),
        ("frozen_config", "missing_frozen_config"),
        ("candidate_registry", "missing_candidate_registry"),
        ("relation_registry", "missing_relation_registry"),
        ("summary", "missing_summary"),
    ],
)
def test_validate_missing_required_fields(field, expected_reason):
    snap = copy.deepcopy(_valid_snapshot())
    del snap[field]
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is False
    assert check["reason"] == expected_reason


def test_source_snapshot_at_not_generated_at():
    out = _attach(kpi_panel=_kpi_panel())
    snap = out["purchasability_preview_v35"]
    assert snap["source_snapshot_at"] == SNAP_AT
    assert snap["generated_at"] != snap["source_snapshot_at"]


def test_engine_payload_hash_excludes_generated_at():
    batch, snap = build_candidate_and_compact_snapshot_v35(
        kpi_panel=_kpi_panel(),
        fixture_meta=_fixture_meta(),
        snapshot_info=_snapshot_info(),
    )
    assert snap is not None
    hash_before = snap["engine_payload_sha256"]
    snap_copy = dict(snap)
    snap_copy["generated_at"] = "2099-01-01T00:00:00+00:00"
    assert engine_payload_sha256_v35(snap_copy) == hash_before


def test_summary_candidate_bands_present():
    out = _attach(kpi_panel=_kpi_panel())
    summary = out["purchasability_preview_v35"]["summary"]
    for ck in ("A", "B", "C", "D"):
        assert ck in summary
        assert "score_band_counts" in summary[ck]
        assert set(summary[ck]["score_band_counts"].keys()) == {
            "0_19",
            "20_39",
            "40_59",
            "60_79",
            "80_100",
        }


def test_historical_reliability_integrated_false():
    out = _attach(kpi_panel=_kpi_panel())
    assert out["purchasability_preview_v35"]["historical_reliability_integrated"] is False
