"""Test rebuild derived V3 su run storico Cecchino Lab (nessun dato reale 2021/22)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_lab_historical_scan_run import (
    STATUS_COMPLETED,
    STATUS_RUNNING,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_derived_rebuild import (
    CLASS_BLOCKED,
    CLASS_REBUILDABLE,
    CONFIRM_TOKEN,
    MARKET_REGISTRY_COUNT,
    classify_snapshot_for_derived_rebuild,
    preflight_historical_run_derived_rebuild,
    rebuild_historical_run_derived_modules,
)


def _utcnow():
    return datetime(2021, 9, 15, 15, 0, tzinfo=timezone.utc)


def _cecchino_output():
    return {
        "status": "available",
        "picchetti": {
            "totals": {"quota_1": 2.1, "quota_x": 3.2, "quota_2": 3.5},
            "home_away": {
                "quota_1": 2.0,
                "quota_x": 3.3,
                "quota_2": 3.6,
                "home_sample_count": 10,
                "away_sample_count": 10,
            },
            "last6_totals": {"quota_1": 2.2, "quota_x": 3.1, "quota_2": 3.4},
            "last5_home_away": {"quota_1": 2.05, "quota_x": 3.25, "quota_2": 3.55},
        },
        "final": {
            "status": "available",
            "quota_1": 2.1,
            "quota_x": 3.2,
            "quota_2": 3.5,
            "prob_1": 0.4,
            "prob_x": 0.3,
            "prob_2": 0.3,
        },
        "goal_markets": {"UNDER_2_5": {"final_odd": 1.95, "status": "available"}},
    }


def _quote_bundle():
    return {
        "quotes": {
            "HOME": {
                "value": 2.0,
                "source_type": "closing",
                "is_real_book_quote": True,
                "is_derived": False,
            },
            "DRAW": {
                "value": 3.4,
                "source_type": "closing",
                "is_real_book_quote": True,
                "is_derived": False,
            },
            "AWAY": {
                "value": 3.8,
                "source_type": "closing",
                "is_real_book_quote": True,
                "is_derived": False,
            },
            "OVER_2_5": {
                "value": 1.9,
                "source_type": "closing",
                "is_real_book_quote": True,
                "is_derived": False,
            },
            "UNDER_2_5": {
                "value": 1.95,
                "source_type": "closing",
                "is_real_book_quote": True,
                "is_derived": False,
            },
        },
        "counts": {
            "real_quote_markets_count": 5,
            "derived_quote_markets_count": 0,
            "unavailable_quote_markets_count": 0,
        },
        "kpi_1x2_real_available": True,
        "kpi_ou25_real_available": True,
    }


def _kpi_panel():
    rows = []
    for mk in (
        "HOME",
        "DRAW",
        "AWAY",
        "OVER_2_5",
        "UNDER_2_5",
        "ONE_X",
        "X_TWO",
        "ONE_TWO",
    ):
        rows.append(
            {
                "market_key": mk,
                "quota_cecchino": 2.2,
                "prob_cecchino": 0.4,
                "quota_book": 2.0,
                "edge_pct": 5.0,
                "vantaggio_prob": 0.05,
                "rating": 60,
            }
        )
    return {"version": "kpi_v2_test", "rows": rows}


def _snap(**overrides):
    base = dict(
        id=1,
        run_id=99,
        dataset_id=1,
        lab_match_id=1001,
        competition_name="Test League",
        season_label="TEST/SEASON",
        kickoff_at=_utcnow(),
        home_team="Home",
        away_team="Away",
        chronological_order=1,
        historical_eligibility_status="eligible_core",
        historical_eligibility_reason=None,
        blocking_reasons_json=[],
        module_availability_json={},
        input_snapshot_json={"leakage_ok": True, "prior_count": 20},
        cecchino_output_json=_cecchino_output(),
        historical_kpi_json=_kpi_panel(),
        signals_json={"formula_version": "legacy"},
        quote_sources_json=_quote_bundle(),
        pre_match_payload_sha256="abc123hash",
        pre_match_locked_at=_utcnow(),
        result_json={
            "fulltime": {"home": 2, "away": 1},
            "halftime": {"home": 1, "away": 0},
        },
        settlement_status="settled",
        settlement_summary_json={"won": 1},
        warnings_json=[],
        error_json=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _run(**overrides):
    base = dict(
        id=99,
        season_label="TEST/SEASON",
        status=STATUS_COMPLETED,
        scan_version="hist_test",
        summary_json={},
        source_git_commit="sourceruncommit",
        source_git_commit_source="test",
        source_revision_status="resolved",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _db_with(run, snaps, market_rows=None):
    db = MagicMock()
    market_rows = market_rows or []

    def get_side_effect(model, pk):
        if pk == run.id:
            return run
        return None

    db.get.side_effect = get_side_effect

    # Alternanza: call dispari = snapshots, pari = market results
    call_n = {"i": 0}

    def scalars_seq(stmt):
        call_n["i"] += 1
        mock = MagicMock()
        # odd = snaps, even = markets (tipico preflight/rebuild)
        if call_n["i"] % 2 == 1:
            mock.all.return_value = snaps
        else:
            mock.all.return_value = market_rows
        return mock

    db.scalars.side_effect = scalars_seq
    return db


def test_confirm_token_constant():
    assert CONFIRM_TOKEN == "REBUILD_CECCHINO_LAB_DERIVED_V3"
    assert MARKET_REGISTRY_COUNT == 19


def test_snapshot_without_input_blocked():
    snap = _snap(input_snapshot_json=None)
    cls = classify_snapshot_for_derived_rebuild(snap)
    assert cls["classification"] == CLASS_BLOCKED
    assert "missing_input_snapshot" in cls["reasons"]


def test_rebuildable_snapshot_classification():
    snap = _snap()
    cls = classify_snapshot_for_derived_rebuild(snap)
    assert cls["classification"] == CLASS_REBUILDABLE
    assert cls["signals_rebuildable"] is True
    assert cls["market_results_rebuildable"] is True


def test_dry_run_does_not_write():
    run = _run()
    snap = _snap()
    db = _db_with(run, [snap])

    out = rebuild_historical_run_derived_modules(db, 99, dry_run=True)
    assert out["status"] == "preview"
    assert out["dry_run"] is True
    assert out["external_api_calls"] == 0
    assert out["full_scan_restarted"] is False
    assert out["full_scan_required"] is False
    assert out["confirm_token_required"] == CONFIRM_TOKEN
    assert out["snapshots_found"] == 1
    assert out["snapshots_rebuildable"] == 1
    db.commit.assert_not_called()
    db.add.assert_not_called()
    db.execute.assert_not_called()


def test_running_run_rejected_on_apply():
    run = _run(status=STATUS_RUNNING)
    snap = _snap()
    db = _db_with(run, [snap])

    with pytest.raises(CecchinoLabImportError) as exc:
        rebuild_historical_run_derived_modules(
            db, 99, dry_run=False, confirm=CONFIRM_TOKEN
        )
    assert exc.value.code == "run_active"


def test_confirm_token_required_for_apply():
    run = _run()
    snap = _snap()
    db = _db_with(run, [snap])

    with pytest.raises(CecchinoLabImportError) as exc:
        rebuild_historical_run_derived_modules(db, 99, dry_run=False, confirm=None)
    assert exc.value.code == "confirm_required"

    with pytest.raises(CecchinoLabImportError) as exc2:
        rebuild_historical_run_derived_modules(
            db, 99, dry_run=False, confirm="WRONG_TOKEN"
        )
    assert exc2.value.code == "confirm_required"


def test_preflight_external_api_and_no_full_scan():
    run = _run()
    snap = _snap()
    db = _db_with(run, [snap])
    out = preflight_historical_run_derived_rebuild(db, 99, dry_run=True)
    assert out["external_api_calls"] == 0
    assert out["full_scan_required"] is False
    assert out["full_scan_restarted"] is False
    assert out["market_registry_count"] == 19
    assert "signal_contract" in out
    assert out["signal_contract"]["formula_version"]


@patch(
    "app.services.cecchino_data_lab.historical_derived_rebuild.resolve_code_revision",
    return_value={
        "git_commit": "deadbeef",
        "git_commit_source": "test",
        "revision_status": "resolved",
    },
)
@patch(
    "app.services.cecchino_data_lab.historical_derived_rebuild.settle_historical_markets",
)
@patch(
    "app.services.cecchino_data_lab.historical_derived_rebuild.build_historical_signal_models",
)
def test_apply_rebuild_idempotent_replace(mock_signals, mock_settle, _rev):
    mock_signals.return_value = {
        "observation_status": "complete",
        "formula_version": "cecchino_signals_matrix_v3_draw_dfg_decimal2",
        "default_matrix": {"status": "available"},
        "models": {},
    }
    mock_settle.return_value = [
        {
            "market_key": "HOME",
            "market_label": "1",
            "period": "FT",
            "line": None,
            "quota_cecchino": 2.1,
            "prob_cecchino": 0.4,
            "quota_book": 2.0,
            "prob_book_raw": None,
            "prob_book_fair": None,
            "quote_source_type": "closing",
            "is_real_book_quote": True,
            "is_derived_quote": False,
            "derivation_method": None,
            "edge_pct": 5.0,
            "vantaggio_prob": 0.05,
            "rating": 60,
            "signal_active": False,
            "signal_sources_json": [],
            "evaluation_status": "won",
            "won": True,
            "profit_1u_real": 1.0,
            "profit_1u_synthetic": None,
            "result_reason": "ft_home",
            "profit_category": "actual_bet365",
        }
    ]

    run = _run()
    snap = _snap()
    frozen_hash = snap.pre_match_payload_sha256
    frozen_input = snap.input_snapshot_json
    original_commit = run.source_git_commit
    db = _db_with(run, [snap])

    out = rebuild_historical_run_derived_modules(
        db, 99, dry_run=False, confirm=CONFIRM_TOKEN
    )
    assert out["status"] == "completed"
    assert out["external_api_calls"] == 0
    assert out["full_scan_restarted"] is False
    assert out["snapshots_rebuilt"] == 1
    assert snap.pre_match_payload_sha256 == frozen_hash
    assert snap.input_snapshot_json == frozen_input
    assert run.source_git_commit == original_commit
    assert (run.summary_json or {}).get("derived_refresh", {}).get("status") == "completed"
    assert (run.summary_json or {})["derived_refresh"]["external_api_calls"] == 0
    assert (run.summary_json or {})["derived_refresh"]["full_scan_restarted"] is False
    db.commit.assert_called()
    mock_signals.assert_called()
    mock_settle.assert_called()


def test_running_preflight_marks_blocked():
    run = _run(status=STATUS_RUNNING)
    snap = _snap()
    db = _db_with(run, [snap])
    out = preflight_historical_run_derived_rebuild(db, 99)
    assert out["run_active"] is True
    assert out["snapshots_blocked"] == 1
    assert out["snapshots_rebuildable"] == 0
    assert out["external_api_calls"] == 0
