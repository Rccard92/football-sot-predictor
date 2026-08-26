"""Test snapshot Structural V2 — B.1 guards, freeze SHA, coesistenza V1."""

from __future__ import annotations

import copy
import time
from datetime import datetime, timezone
from unittest.mock import patch

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    compute_v2_formula_freeze_sha256,
    frozen_math_config_v35_v2,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_holdout_audit import (
    classify_v2_snapshot_creation_timing,
    summarize_v2_creation_timing,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXISTING_PREVIEW_MISSING,
    EXPECTED_FORMULA_FREEZE_SHA256,
    SNAPSHOT_OUTPUT_KEY,
    attach_purchasability_preview_v35_v2_to_output,
    classify_existing_v35_v2_snapshot,
    engine_payload_sha256_v35_v2,
    input_fingerprint_v35_v2,
    resolve_purchasability_preview_v35_v2_for_detail,
    validate_purchasability_preview_v35_v2_snapshot,
)

SNAP_AT = "2026-08-19T10:00:00+00:00"
KICKOFF = "2026-08-19T15:00:00+00:00"
NOW_BEFORE = datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc)
NOW_AFTER = datetime(2026, 8, 19, 17, 0, tzinfo=timezone.utc)


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
) -> dict:
    return {
        "market_key": mk,
        "quota_book": quota_book,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": "betfair_raw_match_winner",
        "book_fallback_used": False,
    }


def _kpi_panel(rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = [
            _row(mk, rating=60, prob=0.55, quota_book=2.2) for mk in PANEL_MARKET_KEYS
        ]
    return {"rows": rows}


def _attach_v2(
    *,
    kpi_panel: dict,
    existing: object = EXISTING_PREVIEW_MISSING,
    snap_at: str = SNAP_AT,
    kickoff: str = KICKOFF,
    verified: bool = True,
    output: dict | None = None,
    now_utc: datetime | None = NOW_BEFORE,
) -> dict:
    out = output if output is not None else {}
    attach_purchasability_preview_v35_v2_to_output(
        cecchino_output=out,
        kpi_panel=kpi_panel,
        fixture_meta=_fixture_meta(snapshot_at=snap_at, kickoff=kickoff),
        snapshot_info=_snapshot_info(
            snapshot_at=snap_at,
            snapshot_timestamp_verified=verified,
        ),
        existing_preview_v35_v2=existing,
        now_utc=now_utc,
    )
    return out


def test_formula_freeze_sha_unchanged_from_phase_a():
    assert compute_v2_formula_freeze_sha256() == EXPECTED_FORMULA_FREEZE_SHA256
    assert EXPECTED_FORMULA_FREEZE_SHA256 == (
        "3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe"
    )
    cfg = frozen_math_config_v35_v2()
    assert cfg["active_v35_structural_version_wired"] is False


def test_valid_pre_match_snapshot_persisted():
    out = _attach_v2(kpi_panel=_kpi_panel())
    snap = out.get(SNAPSHOT_OUTPUT_KEY)
    assert isinstance(snap, dict)
    check = validate_purchasability_preview_v35_v2_snapshot(snap)
    assert check["ok"] is True
    assert snap["formula_freeze_sha256"] == EXPECTED_FORMULA_FREEZE_SHA256
    assert snap["generated_at"] == NOW_BEFORE.isoformat()
    assert snap["runtime_meta"]["runtime_wired"] is True


def test_true_post_kickoff_guard_cases_a_b_c():
    panel = _kpi_panel()
    # A) snap 10, kick 15, now 14 → create
    out_a = _attach_v2(
        kpi_panel=panel,
        snap_at="2026-08-19T10:00:00+00:00",
        kickoff="2026-08-19T15:00:00+00:00",
        now_utc=datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc),
    )
    assert SNAPSHOT_OUTPUT_KEY in out_a
    assert validate_purchasability_preview_v35_v2_snapshot(out_a[SNAPSHOT_OUTPUT_KEY])[
        "ok"
    ]

    # B) snap 10, kick 15, now 17 → no create
    out_b = _attach_v2(
        kpi_panel=panel,
        snap_at="2026-08-19T10:00:00+00:00",
        kickoff="2026-08-19T15:00:00+00:00",
        now_utc=datetime(2026, 8, 19, 17, 0, tzinfo=timezone.utc),
    )
    assert SNAPSHOT_OUTPUT_KEY not in out_b

    # C) snap 16, kick 15, now 17 → no create
    out_c = _attach_v2(
        kpi_panel=panel,
        snap_at="2026-08-19T16:00:00+00:00",
        kickoff="2026-08-19T15:00:00+00:00",
        now_utc=datetime(2026, 8, 19, 17, 0, tzinfo=timezone.utc),
    )
    assert SNAPSHOT_OUTPUT_KEY not in out_c


def test_generated_at_after_kickoff_validator_rejects():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    tampered = copy.deepcopy(snap)
    tampered["generated_at"] = "2026-08-19T17:00:00+00:00"
    # generated_at excluded from engine hash → recompute not needed for mismatch
    check = validate_purchasability_preview_v35_v2_snapshot(tampered)
    assert check["ok"] is False
    assert check["reason"] == "creation_not_before_kickoff"


def test_19_markets_exact():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    assert len(snap["items"]) == 19
    assert {it["market_key"] for it in snap["items"]} == set(PANEL_MARKET_KEYS)


def test_runtime_meta_excluded_from_hashes():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    h1 = engine_payload_sha256_v35_v2(snap)
    mutated = copy.deepcopy(snap)
    mutated["runtime_meta"] = {**mutated["runtime_meta"], "extra": "x"}
    assert engine_payload_sha256_v35_v2(mutated) == h1


def test_first_write_wins_rescan_unchanged():
    panel1 = _kpi_panel()
    out1 = _attach_v2(kpi_panel=panel1)
    snap1 = copy.deepcopy(out1[SNAPSHOT_OUTPUT_KEY])
    panel2 = _kpi_panel(
        [_row(mk, rating=90, prob=0.80, quota_book=3.5) for mk in PANEL_MARKET_KEYS]
    )
    out2 = _attach_v2(kpi_panel=panel2, existing=snap1, now_utc=NOW_AFTER)
    assert out2[SNAPSHOT_OUTPUT_KEY] == snap1


def test_post_kickoff_source_still_blocks():
    out = _attach_v2(
        kpi_panel=_kpi_panel(),
        snap_at="2026-08-19T16:00:00+00:00",
        kickoff=KICKOFF,
        now_utc=NOW_BEFORE,
    )
    assert SNAPSHOT_OUTPUT_KEY not in out


def test_unverified_no_create():
    out = _attach_v2(kpi_panel=_kpi_panel(), verified=False)
    assert SNAPSHOT_OUTPUT_KEY not in out


def test_present_but_invalid_non_dict_preserved_no_batch():
    panel = _kpi_panel()
    for existing in ("broken", [], 123, False, None, {"snapshot_version": "x"}):
        with patch(
            "app.services.cecchino.cecchino_purchasability_v35_v2_snapshot."
            "calculate_purchasability_v35_v2_batch"
        ) as mocked:
            out = _attach_v2(kpi_panel=panel, existing=existing)
            mocked.assert_not_called()
        assert out[SNAPSHOT_OUTPUT_KEY] is existing or out[
            SNAPSHOT_OUTPUT_KEY
        ] == existing
        classified = classify_existing_v35_v2_snapshot(existing)
        assert classified.status == "present_but_invalid"


def test_key_present_null_is_present_but_invalid_not_absent():
    classified = classify_existing_v35_v2_snapshot(None)
    assert classified.status == "present_but_invalid"
    assert classify_existing_v35_v2_snapshot(EXISTING_PREVIEW_MISSING).status == "absent"

    # Detail: key present with null
    detail = resolve_purchasability_preview_v35_v2_for_detail(
        row=type("R", (), {"cecchino_output_json": {SNAPSHOT_OUTPUT_KEY: None}})()
    )
    assert detail["purchasability_v35_v2_snapshot_status"] == "present_but_invalid"

    # Detail: key absent
    absent = resolve_purchasability_preview_v35_v2_for_detail(
        row=type("R", (), {"cecchino_output_json": {}})()
    )
    assert absent["purchasability_v35_v2_snapshot_status"] == "absent"


def test_wiring_like_new_output_preserves_raw_invalid():
    """Simulate run_scan: new cecchino_output + raw existing from DB."""
    panel = _kpi_panel()
    new_output: dict = {"other": 1}
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_snapshot."
        "calculate_purchasability_v35_v2_batch"
    ) as mocked:
        attach_purchasability_preview_v35_v2_to_output(
            cecchino_output=new_output,
            kpi_panel=panel,
            fixture_meta=_fixture_meta(),
            snapshot_info=_snapshot_info(),
            existing_preview_v35_v2="broken",
            now_utc=NOW_BEFORE,
        )
        mocked.assert_not_called()
    assert new_output[SNAPSHOT_OUTPUT_KEY] == "broken"
    assert new_output["other"] == 1


def test_tamper_sha_rejected():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    tampered = copy.deepcopy(snap)
    tampered["engine_payload_sha256"] = "0" * 64
    check = validate_purchasability_preview_v35_v2_snapshot(tampered)
    assert check["ok"] is False
    assert check["reason"] == "engine_payload_sha256_mismatch"


def test_detail_valid_no_recompute():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_snapshot."
        "calculate_purchasability_v35_v2_batch"
    ) as mocked:
        valid = resolve_purchasability_preview_v35_v2_for_detail(
            row=type("R", (), {"cecchino_output_json": {SNAPSHOT_OUTPUT_KEY: snap}})()
        )
        mocked.assert_not_called()
    assert valid["purchasability_v35_v2_snapshot_status"] == "valid"


def test_v1_v2_coexist_without_cross_mutation():
    panel = _kpi_panel()
    output: dict = {}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel=panel,
        fixture_meta=_fixture_meta(),
        snapshot_info=_snapshot_info(),
        existing_preview_v35=None,
    )
    attach_purchasability_preview_v35_v2_to_output(
        cecchino_output=output,
        kpi_panel=panel,
        fixture_meta=_fixture_meta(),
        snapshot_info=_snapshot_info(),
        existing_preview_v35_v2=EXISTING_PREVIEW_MISSING,
        now_utc=NOW_BEFORE,
    )
    assert "purchasability_preview_v35" in output
    assert SNAPSHOT_OUTPUT_KEY in output
    v2_hash = output[SNAPSHOT_OUTPUT_KEY]["engine_payload_sha256"]
    output["purchasability_preview_v35"]["warnings"] = ["mutated_v1"]
    assert output[SNAPSHOT_OUTPUT_KEY]["engine_payload_sha256"] == v2_hash


def test_fingerprint_deterministic():
    panel = _kpi_panel()
    meta = _fixture_meta()
    assert input_fingerprint_v35_v2(
        kpi_panel=panel, fixture_meta=meta
    ) == input_fingerprint_v35_v2(kpi_panel=panel, fixture_meta=meta)


def test_holdout_audit_buckets_read_only():
    good = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    bad_time = copy.deepcopy(good)
    bad_time["generated_at"] = "2026-08-19T17:00:00+00:00"
    rows = [
        {"today_fixture_id": 1, "key_present": True, "snapshot": good},
        {"today_fixture_id": 2, "key_present": True, "snapshot": bad_time},
        {"today_fixture_id": 3, "key_present": True, "snapshot": None},
        {"today_fixture_id": 4, "key_present": True, "snapshot": "broken"},
        {
            "today_fixture_id": 5,
            "key_present": True,
            "snapshot": {**good, "generated_at": None},
        },
    ]
    summary = summarize_v2_creation_timing(rows)
    assert summary["total_v2_snapshots"] == 5
    assert summary["generated_before_kickoff"] == 1
    assert summary["generated_at_or_after_kickoff"] >= 1
    assert summary["invalid"] >= 1
    assert classify_v2_snapshot_creation_timing(bad_time)[
        "bucket"
    ] == "generated_at_or_after_kickoff"
    assert classify_v2_snapshot_creation_timing(good)["holdout_eligible"] is True


def test_attach_benchmark_19_markets():
    panel = _kpi_panel()
    t0 = time.perf_counter()
    _attach_v2(kpi_panel=panel)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 5000.0, f"attach too slow: {elapsed_ms:.1f}ms"
    print(f"BENCHMARK_ATTACH_V2_MS={elapsed_ms:.2f}")
