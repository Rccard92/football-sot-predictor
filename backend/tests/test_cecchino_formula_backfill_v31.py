"""Test backfill formule Cecchino V3.1 Fase 1B."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino.cecchino_formula_backfill_v31 import (
    BACKFILL_MODE,
    CONFIRM_TOKEN,
    PHASE1B_TARGET_MARKETS,
    backfill_fixture_formulas_phase1b,
    merge_goal_markets_phase1b,
    run_formula_backfill_v31_phase1b,
)
from app.services.cecchino.cecchino_purchasability_v3_opposition import SUPPORTED_V3_MARKETS
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY_PT,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
    SEL_OVER_2_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
)


def _block(mk: str, odd: float | None, version: str = "goal_market_poisson_empirical_v2"):
    return {
        "market_key": mk,
        "formula_version": version,
        "final_odd": odd,
        "status": "available" if odd else "insufficient_data",
        "summary": {"final_probability_raw": 0.4 if odd else None},
    }


def test_merge_adds_missing_without_overwrite():
    existing = {
        SEL_UNDER_1_5: _block(SEL_UNDER_1_5, 3.2),
        SEL_DRAW_PT: _block(SEL_DRAW_PT, 2.5, "first_half_draw_empirical_shrinkage_v1"),
    }
    computed = {
        SEL_UNDER_1_5: _block(SEL_UNDER_1_5, 9.9),
        SEL_HOME_PT: _block(SEL_HOME_PT, 2.1, "first_half_1x2_empirical_shrinkage_v2"),
        SEL_DRAW_PT: _block(SEL_DRAW_PT, 3.0, "first_half_1x2_empirical_shrinkage_v2"),
        SEL_AWAY_PT: _block(SEL_AWAY_PT, 3.5, "first_half_1x2_empirical_shrinkage_v2"),
    }
    out = merge_goal_markets_phase1b(existing, computed, force=False)
    gm = out["goal_markets"]
    # UNDER_1_5 già presente → non sovrascritto
    assert gm[SEL_UNDER_1_5]["final_odd"] == 3.2
    assert SEL_UNDER_1_5 in out["merge_report"]["markets_skipped_present"]
    # HOME/AWAY aggiunti; DRAW presente → skipped in family unless missing
    assert gm[SEL_HOME_PT]["final_odd"] == 2.1
    assert gm[SEL_AWAY_PT]["final_odd"] == 3.5
    assert gm[SEL_DRAW_PT]["final_odd"] == 2.5


def test_merge_force_replaces_with_trace():
    existing = {SEL_UNDER_1_5: _block(SEL_UNDER_1_5, 3.2)}
    computed = {SEL_UNDER_1_5: _block(SEL_UNDER_1_5, 4.5)}
    out = merge_goal_markets_phase1b(existing, computed, force=True)
    assert out["goal_markets"][SEL_UNDER_1_5]["final_odd"] == 4.5
    assert "previous_version_trace" in out["goal_markets"][SEL_UNDER_1_5]
    assert out["goal_markets"][SEL_UNDER_1_5]["previous_version_trace"]["previous_final_odd"] == 3.2


def test_merge_not_computable_recorded():
    existing = {}
    computed = {SEL_UNDER_1_5: _block(SEL_UNDER_1_5, None)}
    out = merge_goal_markets_phase1b(existing, computed, force=False)
    assert SEL_UNDER_1_5 in out["merge_report"]["markets_not_computable"]


def test_dry_run_does_not_write(monkeypatch):
    row = SimpleNamespace(
        id=10,
        kickoff=datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc),
        local_fixture_id=100,
        cecchino_output_json={
            "final": {"status": "available", "quota_1": 2.0},
            "goal_markets": {},
            "purchasability_preview_v3": {"candidate_version": "fixed_discount_v3", "keep": True},
        },
        kpi_panel_json={"rows": []},
        odds_snapshot_json={},
    )
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=100)

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.build_goal_market_contexts",
        lambda *a, **k: object(),
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.build_goal_market_cecchino_odds",
        lambda *a, **k: {
            SEL_HOME_PT: _block(SEL_HOME_PT, 2.2, "first_half_1x2_empirical_shrinkage_v2"),
            SEL_DRAW_PT: _block(SEL_DRAW_PT, 3.1, "first_half_1x2_empirical_shrinkage_v2"),
            SEL_AWAY_PT: _block(SEL_AWAY_PT, 3.4, "first_half_1x2_empirical_shrinkage_v2"),
            SEL_UNDER_1_5: _block(SEL_UNDER_1_5, 3.0),
        },
    )

    result = backfill_fixture_formulas_phase1b(db, row, dry_run=True, force=False)
    assert result["updatable"] is True
    assert result["updated"] is False
    assert result["dry_run"] is True
    assert SEL_HOME_PT in result["markets_added"]
    # Nessuna scrittura
    assert row.cecchino_output_json["goal_markets"] == {}
    assert row.cecchino_output_json["purchasability_preview_v3"]["keep"] is True


def test_apply_writes_and_preserves_v3(monkeypatch):
    row = SimpleNamespace(
        id=11,
        kickoff=datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc),
        local_fixture_id=101,
        cecchino_output_json={
            "final": {"status": "available", "quota_1": 2.0, "prob_1": 0.5, "prob_x": 0.25, "prob_2": 0.25},
            "goal_markets": {},
            "purchasability_preview_v3": {"candidate_version": "fixed_discount_v3", "keep": True},
        },
        kpi_panel_json={"rows": []},
        odds_snapshot_json={},
    )
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=101)

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.build_goal_market_contexts",
        lambda *a, **k: object(),
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.build_goal_market_cecchino_odds",
        lambda *a, **k: {
            SEL_HOME_PT: _block(SEL_HOME_PT, 2.2, "first_half_1x2_empirical_shrinkage_v2"),
            SEL_DRAW_PT: _block(SEL_DRAW_PT, 3.1, "first_half_1x2_empirical_shrinkage_v2"),
            SEL_AWAY_PT: _block(SEL_AWAY_PT, 3.4, "first_half_1x2_empirical_shrinkage_v2"),
            SEL_UNDER_1_5: _block(SEL_UNDER_1_5, 3.0),
        },
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31._load_betfair_payload_offline",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.build_cecchino_kpi_panel_v2_betfair",
        lambda **k: {"version": "kpi", "rows": [{"market_key": SEL_HOME_PT, "quota_cecchino": 2.2}]},
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.read_odds_meta",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.flag_modified",
        lambda *a, **k: None,
    )

    result = backfill_fixture_formulas_phase1b(db, row, dry_run=False, force=False)
    assert result["updated"] is True
    assert SEL_HOME_PT in row.cecchino_output_json["goal_markets"]
    assert row.cecchino_output_json["purchasability_preview_v3"]["keep"] is True
    assert row.cecchino_output_json["formula_backfill_v31_phase1b"]["mode"] == BACKFILL_MODE
    assert row.kpi_panel_json["rows"][0]["quota_cecchino"] == 2.2


def test_idempotent_second_run(monkeypatch):
    gm = {
        SEL_HOME_PT: _block(SEL_HOME_PT, 2.2, "first_half_1x2_empirical_shrinkage_v2"),
        SEL_DRAW_PT: _block(SEL_DRAW_PT, 3.1, "first_half_1x2_empirical_shrinkage_v2"),
        SEL_AWAY_PT: _block(SEL_AWAY_PT, 3.4, "first_half_1x2_empirical_shrinkage_v2"),
        SEL_UNDER_1_5: _block(SEL_UNDER_1_5, 3.0),
    }
    row = SimpleNamespace(
        id=12,
        kickoff=datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc),
        local_fixture_id=102,
        cecchino_output_json={"final": {}, "goal_markets": dict(gm)},
        kpi_panel_json={},
        odds_snapshot_json={},
    )
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=102)
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.build_goal_market_contexts",
        lambda *a, **k: object(),
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_formula_backfill_v31.build_goal_market_cecchino_odds",
        lambda *a, **k: dict(gm),
    )
    result = backfill_fixture_formulas_phase1b(db, row, dry_run=False, force=False)
    assert result["skip_reason"] == "nothing_to_update"
    assert result["updated"] is False


def test_kickoff_missing_skipped():
    row = SimpleNamespace(
        id=13,
        kickoff=None,
        local_fixture_id=103,
        cecchino_output_json={"goal_markets": {}},
    )
    result = backfill_fixture_formulas_phase1b(MagicMock(), row, dry_run=True)
    assert result["skip_reason"] == "kickoff_missing"


def test_range_without_limit_guard():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with pytest.raises(ValueError, match="limit"):
        run_formula_backfill_v31_phase1b(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 2, 1),
            dry_run=True,
            limit=None,
        )


def test_confirm_token_constant():
    assert CONFIRM_TOKEN == "WRITE_FORMULA_BACKFILL_V31_P1B"
    assert BACKFILL_MODE == "formula_backfill_v31_phase1b"


def test_v3_supported_markets_unchanged_regression():
    """Fase 1B non estende SUPPORTED_V3_MARKETS."""
    assert SEL_HOME in SUPPORTED_V3_MARKETS
    assert SEL_OVER_2_5 in SUPPORTED_V3_MARKETS
    assert SEL_UNDER_2_5 in SUPPORTED_V3_MARKETS
    assert SEL_HOME_PT not in SUPPORTED_V3_MARKETS
    assert SEL_UNDER_1_5 not in SUPPORTED_V3_MARKETS
    assert SEL_AWAY_PT not in SUPPORTED_V3_MARKETS


def test_phase1b_targets_include_new_markets():
    assert SEL_HOME_PT in PHASE1B_TARGET_MARKETS
    assert SEL_UNDER_1_5 in PHASE1B_TARGET_MARKETS
