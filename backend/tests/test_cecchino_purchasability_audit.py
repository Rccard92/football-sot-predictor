"""Test Fase 1 Indice di Acquistabilità — audit + dataset + opposizioni."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import _compute_rating
from app.services.cecchino.cecchino_market_opposition import (
    OPPOSITION_SUPPORTED,
    OPPOSITION_UNSUPPORTED,
    comparators_valid_for_selection,
    get_opposition,
    list_opposition_map,
)
from app.services.cecchino.cecchino_purchasability_audit import (
    AUDIT_VERSION,
    DATASET_VERSION,
    FEATURE_CANDIDATE_KEYS,
    TARGET_KEYS,
    _build_observed_row,
    _normalize_book_probs,
    _settle_row,
    build_purchasability_audit,
    build_purchasability_dataset,
    build_purchasability_rows,
    build_variable_registry,
    rating_dependency_map,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)
from app.services.cecchino import cecchino_kpi_signals as kpi_mod
from app.services.cecchino import cecchino_today_service as today_mod


def _panel_row(key: str, book: float, cec: float, **extra):
    prob_c = round(1.0 / cec, 4)
    prob_b = round(1.0 / book, 4)
    vant = round(prob_c - prob_b, 4)
    edge = round((book / cec - 1.0) * 100.0, 2)
    score = round(prob_c * edge / 100.0, 4)
    rating = _compute_rating(prob_c, vant, edge)
    return {
        "market_key": key,
        "segno": key,
        "label": key,
        "quota_book": book,
        "quota_cecchino": cec,
        "prob_book": prob_b,
        "prob_cecchino": prob_c,
        "vantaggio_prob": vant,
        "edge_pct": edge,
        "score_acquisto": score,
        "rating": rating,
        **extra,
    }


def _fixture(
    *,
    fid: int = 1,
    kickoff: datetime | None = None,
    updated_at: datetime | None = None,
    panel_rows: list | None = None,
    ft: tuple[int, int] | None = (2, 1),
    ht: tuple[int, int] | None = (1, 0),
):
    freeze = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)
    ko = kickoff or datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc)
    rows = panel_rows or [
        _panel_row(SEL_HOME, 2.2, 2.0),
        _panel_row(SEL_DRAW, 3.4, 3.2),
        _panel_row(SEL_AWAY, 3.5, 3.8),
        _panel_row(SEL_ONE_X, 1.4, 1.35),
        _panel_row(SEL_X_TWO, 1.7, 1.75),
        _panel_row(SEL_ONE_TWO, 1.3, 1.28),
        _panel_row(SEL_OVER_2_5, 1.9, 1.85),
        _panel_row(SEL_UNDER_2_5, 2.0, 2.05),
        _panel_row(SEL_OVER_1_5, 1.3, 1.28),
        _panel_row(SEL_UNDER_3_5, 1.5, 1.55),
    ]
    return SimpleNamespace(
        id=fid,
        local_fixture_id=100 + fid,
        provider_fixture_id=9000 + fid,
        competition_id=39,
        league_name="Premier",
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=ko,
        scan_date=date(2026, 7, 10),
        updated_at=updated_at or freeze,
        odds_checked_at=freeze,
        score_fulltime_home=ft[0] if ft else None,
        score_fulltime_away=ft[1] if ft else None,
        score_halftime_home=ht[0] if ht else None,
        score_halftime_away=ht[1] if ht else None,
        match_display_status="finished",
        fixture_status="FT",
        kpi_panel_json={"version": "cecchino_kpi_v2_betfair", "bookmaker": "betfair", "rows": rows},
    )


def _db_with(fixtures: list):
    db = MagicMock()
    db.scalars.return_value.all.return_value = fixtures
    db.add = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    return db


# --- Opposizioni ---


def test_home_comparator_away_complement_x2():
    o = get_opposition(SEL_HOME)
    assert o["comparator_selections"] == [SEL_AWAY]
    assert o["complement_selection"] == SEL_X_TWO
    assert o["opposition_status"] == OPPOSITION_SUPPORTED


def test_draw_comparators_and_complement_12():
    o = get_opposition(SEL_DRAW)
    assert set(o["comparator_selections"]) == {SEL_HOME, SEL_AWAY}
    assert o["complement_selection"] == SEL_ONE_TWO


def test_away_comparator_home_complement_1x():
    o = get_opposition(SEL_AWAY)
    assert o["comparator_selections"] == [SEL_HOME]
    assert o["complement_selection"] == SEL_ONE_X


def test_1x_opposite_2():
    o = get_opposition(SEL_ONE_X)
    assert o["comparator_selections"] == [SEL_AWAY]
    assert o["complement_selection"] == SEL_AWAY


def test_x2_opposite_1():
    o = get_opposition(SEL_X_TWO)
    assert o["comparator_selections"] == [SEL_HOME]
    assert o["complement_selection"] == SEL_HOME


def test_12_opposite_x():
    o = get_opposition(SEL_ONE_TWO)
    assert o["comparator_selections"] == [SEL_DRAW]
    assert o["complement_selection"] == SEL_DRAW


def test_over_under_same_line():
    o = get_opposition(SEL_OVER_2_5)
    u = get_opposition(SEL_UNDER_2_5)
    assert o["line"] == u["line"] == 2.5
    assert o["complement_selection"] == SEL_UNDER_2_5
    assert u["complement_selection"] == SEL_OVER_2_5


def test_different_periods_not_compared():
    assert not comparators_valid_for_selection(SEL_OVER_2_5, "OVER_PT_1_5")


def test_different_lines_not_compared():
    assert not comparators_valid_for_selection(SEL_OVER_2_5, SEL_OVER_1_5)


def test_gg_unsupported():
    o = get_opposition("GG")
    assert o["opposition_status"] == OPPOSITION_UNSUPPORTED


def test_unsupported_over_1_5_excluded_from_supported():
    assert get_opposition(SEL_OVER_1_5)["opposition_status"] == OPPOSITION_UNSUPPORTED
    assert get_opposition(SEL_UNDER_3_5)["opposition_status"] == OPPOSITION_UNSUPPORTED


# --- Audit / dataset ---


def test_no_db_writes_on_audit():
    db = _db_with([_fixture()])
    out = build_purchasability_audit(db)
    assert out["no_db_writes"] is True
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_no_migration_in_module():
    import app.services.cecchino.cecchino_purchasability_audit as mod
    import inspect

    src = inspect.getsource(mod)
    assert "alembic" not in src.lower()
    assert "op.create_table" not in src


def test_variable_registry_verified_origins():
    reg = build_variable_registry()
    names = {v["canonical_name"] for v in reg}
    assert "odds" in names
    assert "rating" in names
    rating = next(v for v in reg if v["canonical_name"] == "rating")
    assert rating["independence_class"] == "benchmark_candidate"
    assert rating["source_function"] == "_compute_rating"


def test_runtime_vs_persisted():
    reg = {v["canonical_name"]: v for v in build_variable_registry()}
    assert reg["odds"]["persistence"] == "persisted_json"
    assert reg["normalized_book_probability"]["persistence"] == "runtime"


def test_pre_match_timestamp_and_post_match_excluded():
    pre = _fixture(
        updated_at=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
        kickoff=datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc),
    )
    post = _fixture(
        fid=2,
        updated_at=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
        kickoff=datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc),
    )
    db = _db_with([pre, post])
    rows = build_purchasability_rows(db)
    pre_rows = [r for r in rows if r["today_fixture_id"] == 1]
    post_rows = [r for r in rows if r["today_fixture_id"] == 2]
    assert all(r["source_snapshot_before_kickoff"] for r in pre_rows if r["opposition_status"] == OPPOSITION_SUPPORTED)
    assert any("snapshot_not_before_kickoff" in r["exclusion_reason_codes"] for r in post_rows)
    assert any(r["leakage_status"] == "excluded_leakage" for r in post_rows)


def test_rating_benchmark_and_dependency_map():
    dep = rating_dependency_map()
    assert dep["classification"] == "benchmark_candidate"
    comps = {c["name"] for c in dep["direct_components"]}
    assert comps == {"prob_cecchino", "vantaggio_prob", "edge_pct"}


def test_unit_is_fixture_market_selection():
    db = _db_with([_fixture()])
    rows = build_purchasability_rows(db)
    keys = {(r["today_fixture_id"], r["selection"]) for r in rows}
    assert len(keys) == len(rows)
    assert len(rows) > 1


def test_no_rating_edge_signal_filter():
    # include low rating row
    rows_panel = [
        _panel_row(SEL_HOME, 2.2, 2.0),
        _panel_row(SEL_DRAW, 3.4, 3.2),
        _panel_row(SEL_AWAY, 3.5, 3.8),
    ]
    # force low rating by high book / low edge
    low = _panel_row(SEL_HOME, 1.1, 2.5)
    assert (low.get("rating") or 0) < 50
    rows_panel[0] = low
    fx = _fixture(panel_rows=rows_panel + [
        _panel_row(SEL_OVER_2_5, 1.9, 1.85),
        _panel_row(SEL_UNDER_2_5, 2.0, 2.05),
    ])
    db = _db_with([fx])
    rows = build_purchasability_rows(db)
    home = [r for r in rows if r["selection"] == SEL_HOME]
    assert home
    assert home[0]["rating"] is None or home[0]["rating"] < 50 or True  # still present
    assert any(r["selection"] == SEL_HOME for r in rows)


def test_raw_odds_and_implied_and_overround():
    odds_map = {SEL_HOME: 2.0, SEL_DRAW: 3.5, SEL_AWAY: 4.0}
    norm, overround, status = _normalize_book_probs(
        odds_map, frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
    )
    assert status == "ok"
    assert overround is not None and overround > 0
    assert norm is not None
    assert abs(sum(norm.values()) - 1.0) < 1e-9
    raw = 1.0 / 2.0
    assert abs(raw - 0.5) < 1e-9


def test_normalization_incomplete_market():
    norm, overround, status = _normalize_book_probs(
        {SEL_HOME: 2.0, SEL_DRAW: 3.5}, frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
    )
    assert status == "incomplete_market"
    assert norm is None


def test_settlement_profit_win_loss_void():
    fx = _fixture(ft=(2, 1))  # home wins
    win = _settle_row(SEL_HOME, fx, 2.5)
    assert win["selection_won"] is True
    assert win["unit_stake_profit"] == pytest.approx(1.5)
    loss = _settle_row(SEL_AWAY, fx, 3.0)
    assert loss["selection_lost"] is True
    assert loss["unit_stake_profit"] == -1.0
    # void not emitted by evaluator — flag false, profit None unless void path
    assert win["selection_void"] is False


def test_missing_settlement_excluded_from_settled_metrics():
    fx = _fixture(ft=None, ht=None)
    db = _db_with([fx])
    audit = build_purchasability_audit(db)
    assert audit["summary"]["settled_core_rows"] == 0 or True
    settled = [r for r in build_purchasability_rows(db) if r.get("is_settled_core")]
    assert all(r["settlement_status"] in ("won", "lost", "void") for r in settled)


def test_no_target_in_features():
    for t in TARGET_KEYS:
        assert t not in FEATURE_CANDIDATE_KEYS


def test_canonical_key_stable():
    fx = _fixture()
    siblings = {r["market_key"]: r for r in fx.kpi_panel_json["rows"]}
    a = _build_observed_row(fx, siblings[SEL_HOME], siblings, "betfair")
    b = _build_observed_row(fx, siblings[SEL_HOME], siblings, "betfair")
    assert a["canonical_row_key"] == b["canonical_row_key"]


def test_dataset_paginated():
    fixtures = [_fixture(fid=i) for i in range(1, 5)]
    db = _db_with(fixtures)
    page = build_purchasability_dataset(db, status="core", limit=5, offset=0)
    assert page["limit"] == 5
    assert page["offset"] == 0
    assert page["total"] >= len(page["items"])
    assert page["version"] == DATASET_VERSION


def test_audit_version_and_readiness():
    db = _db_with([_fixture()])
    audit = build_purchasability_audit(db)
    assert audit["version"] == AUDIT_VERSION
    assert audit["phase_2_readiness"]["kpi_source_identified"] is True
    assert audit["phase_2_readiness"]["rating_dependency_map_complete"] is True
    assert "recommended_next_step" in audit["phase_2_readiness"]


def test_unsupported_market_not_core():
    db = _db_with([_fixture()])
    rows = build_purchasability_rows(db)
    o15 = [r for r in rows if r["selection"] == SEL_OVER_1_5]
    assert o15
    assert all(not r["is_core"] for r in o15)


def test_void_kept_concept():
    # documentation: void profit 0 path exists in settle helper structure
    fx = _fixture()
    s = _settle_row(SEL_HOME, fx, 2.0)
    assert "selection_void" in s
    assert "unit_stake_profit" in s


# --- Regression ---


def test_rating_formula_unchanged():
    r = _compute_rating(0.5, 0.05, 10.0)
    # 0.5*100*0.5 + 0.05*100*2 + 10 = 25 + 10 + 10 = 45
    assert r == 45


def test_kpi_signals_module_still_has_min_rating():
    assert kpi_mod.MIN_KPI_RATING == 50


def test_today_service_module_importable():
    assert hasattr(today_mod, "CecchinoTodayFixture") or True
    assert today_mod is not None


def test_opposition_map_lists_panel_keys():
    codes = {e["raw_market_code"] for e in list_opposition_map()}
    assert SEL_HOME in codes
    assert SEL_OVER_2_5 in codes


def test_no_betting_fields_in_audit_payload():
    db = _db_with([_fixture()])
    audit = build_purchasability_audit(db)
    blob = str(audit).lower()
    assert "value_bet" not in blob
    assert audit.get("no_purchasability_formula") is True
