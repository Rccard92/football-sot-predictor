"""Test snapshot Structural V2 — first-write-wins, freeze SHA, coesistenza V1."""

from __future__ import annotations

import copy
import time
from unittest.mock import patch

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    compute_v2_formula_freeze_sha256,
    frozen_math_config_v35_v2,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
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
    existing: dict | None = None,
    snap_at: str = SNAP_AT,
    kickoff: str = KICKOFF,
    verified: bool = True,
    output: dict | None = None,
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
    assert snap["runtime_meta"]["runtime_wired"] is True
    assert snap["runtime_meta"]["holdout_mode"] == "paired_v1_v2"
    assert snap["immutable_first_write"] is True


def test_19_markets_exact():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    assert len(snap["items"]) == 19
    assert {it["market_key"] for it in snap["items"]} == set(PANEL_MARKET_KEYS)


def test_runtime_meta_excluded_from_hashes():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    h1 = engine_payload_sha256_v35_v2(snap)
    mutated = copy.deepcopy(snap)
    mutated["runtime_meta"] = {
        **mutated["runtime_meta"],
        "runtime_wired": False,
        "extra": "should_not_affect_hash",
    }
    h2 = engine_payload_sha256_v35_v2(mutated)
    assert h1 == h2
    # formula freeze independent of runtime
    assert compute_v2_formula_freeze_sha256() == EXPECTED_FORMULA_FREEZE_SHA256


def test_first_write_wins_rescan_unchanged():
    panel1 = _kpi_panel()
    out1 = _attach_v2(kpi_panel=panel1)
    snap1 = copy.deepcopy(out1[SNAPSHOT_OUTPUT_KEY])
    panel2 = _kpi_panel(
        [_row(mk, rating=90, prob=0.80, quota_book=3.5) for mk in PANEL_MARKET_KEYS]
    )
    out2 = _attach_v2(kpi_panel=panel2, existing=snap1)
    assert out2[SNAPSHOT_OUTPUT_KEY] == snap1
    assert out2[SNAPSHOT_OUTPUT_KEY]["engine_payload_sha256"] == snap1[
        "engine_payload_sha256"
    ]


def test_post_kickoff_no_create():
    out = _attach_v2(
        kpi_panel=_kpi_panel(),
        snap_at="2026-08-19T16:00:00+00:00",
        kickoff=KICKOFF,
    )
    assert SNAPSHOT_OUTPUT_KEY not in out


def test_unverified_no_create():
    out = _attach_v2(kpi_panel=_kpi_panel(), verified=False)
    assert SNAPSHOT_OUTPUT_KEY not in out


def test_present_but_invalid_preserved_not_repaired():
    bad = {"snapshot_version": "broken", "items": []}
    out = _attach_v2(kpi_panel=_kpi_panel(), existing=bad)
    assert out[SNAPSHOT_OUTPUT_KEY] is bad
    classified = classify_existing_v35_v2_snapshot(bad)
    assert classified.status == "present_but_invalid"


def test_tamper_sha_rejected():
    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    tampered = copy.deepcopy(snap)
    tampered["engine_payload_sha256"] = "0" * 64
    check = validate_purchasability_preview_v35_v2_snapshot(tampered)
    assert check["ok"] is False
    assert check["reason"] == "engine_payload_sha256_mismatch"


def test_detail_absent_valid_present_but_invalid_no_recompute():
    class _Row:
        def __init__(self, output):
            self.cecchino_output_json = output

    absent = resolve_purchasability_preview_v35_v2_for_detail(row=_Row({}))
    assert absent["purchasability_v35_v2_snapshot_status"] == "absent"

    snap = _attach_v2(kpi_panel=_kpi_panel())[SNAPSHOT_OUTPUT_KEY]
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_snapshot."
        "calculate_purchasability_v35_v2_batch"
    ) as mocked:
        valid = resolve_purchasability_preview_v35_v2_for_detail(
            row=_Row({SNAPSHOT_OUTPUT_KEY: snap})
        )
        mocked.assert_not_called()
    assert valid["purchasability_v35_v2_snapshot_status"] == "valid"
    assert valid["purchasability_preview_v35_v2"] is not None

    invalid = resolve_purchasability_preview_v35_v2_for_detail(
        row=_Row({SNAPSHOT_OUTPUT_KEY: {"snapshot_version": "x"}})
    )
    assert invalid["purchasability_v35_v2_snapshot_status"] == "present_but_invalid"
    assert invalid["purchasability_preview_v35_v2"] is None


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
        existing_preview_v35_v2=None,
    )
    assert "purchasability_preview_v35" in output
    assert SNAPSHOT_OUTPUT_KEY in output
    v1_hash = output["purchasability_preview_v35"]["engine_payload_sha256"]
    v2_hash = output[SNAPSHOT_OUTPUT_KEY]["engine_payload_sha256"]

    # Mutate V1 in place — V2 hash must remain valid/unchanged
    output["purchasability_preview_v35"]["warnings"] = ["mutated_v1"]
    assert (
        output[SNAPSHOT_OUTPUT_KEY]["engine_payload_sha256"] == v2_hash
    )
    assert validate_purchasability_preview_v35_v2_snapshot(
        output[SNAPSHOT_OUTPUT_KEY]
    )["ok"]

    # Rescan with different KPI must keep both first-writes
    panel2 = _kpi_panel(
        [_row(mk, rating=99, prob=0.9, quota_book=4.0) for mk in PANEL_MARKET_KEYS]
    )
    v1_copy = copy.deepcopy(output["purchasability_preview_v35"])
    v2_copy = copy.deepcopy(output[SNAPSHOT_OUTPUT_KEY])
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel=panel2,
        fixture_meta=_fixture_meta(),
        snapshot_info=_snapshot_info(),
        existing_preview_v35=v1_copy,
    )
    attach_purchasability_preview_v35_v2_to_output(
        cecchino_output=output,
        kpi_panel=panel2,
        fixture_meta=_fixture_meta(),
        snapshot_info=_snapshot_info(),
        existing_preview_v35_v2=v2_copy,
    )
    assert output["purchasability_preview_v35"]["engine_payload_sha256"] == v1_hash
    assert output[SNAPSHOT_OUTPUT_KEY]["engine_payload_sha256"] == v2_hash


def test_fingerprint_deterministic():
    panel = _kpi_panel()
    meta = _fixture_meta()
    assert input_fingerprint_v35_v2(
        kpi_panel=panel, fixture_meta=meta
    ) == input_fingerprint_v35_v2(kpi_panel=panel, fixture_meta=meta)


def test_attach_benchmark_19_markets():
    panel = _kpi_panel()
    t0 = time.perf_counter()
    _attach_v2(kpi_panel=panel)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # Soft bound for CI noise; report via assertion message
    assert elapsed_ms < 5000.0, f"attach too slow: {elapsed_ms:.1f}ms"
    print(f"BENCHMARK_ATTACH_V2_MS={elapsed_ms:.2f}")
