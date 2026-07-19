"""Test feature Acquistabilità Fase 2 — phase1/phase2/data quality."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.cecchino.cecchino_purchasability_features import (
    build_model_context_probability_map,
    build_purchasability_feature_item,
    build_purchasability_features_for_fixture,
    build_purchasability_features_for_panel,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)


def _full_row(market_key: str, *, qb=2.0, qc=1.9, pb=0.5, pc=0.52, **kw) -> dict:
    base = {
        "market_key": market_key,
        "quota_book": qb,
        "quota_cecchino": qc,
        "prob_book": pb,
        "prob_cecchino": pc,
        "vantaggio_prob": pc - pb,
        "edge_pct": (qb / qc - 1) * 100 if qc else None,
        "score_acquisto": pc * ((qb / qc - 1) * 100) / 100 if qc else None,
        "rating": 72,
        "rating_label": "Buona",
        "status": "ok",
        "book_source": "betfair",
        "cecchino_source": "model",
    }
    base.update(kw)
    return base


def _1x2_panel():
    return [
        _full_row(SEL_HOME, qb=2.10, qc=1.95, pb=1 / 2.10, pc=0.48),
        _full_row(SEL_DRAW, qb=3.40, qc=3.20, pb=1 / 3.40, pc=0.30),
        _full_row(SEL_AWAY, qb=3.60, qc=3.50, pb=1 / 3.60, pc=0.22),
    ]


FIXTURE_META = {
    "today_fixture_id": 99,
    "provider_fixture_id": 1001,
    "competition_id": 7,
    "scan_date": "2026-03-15",
    "kickoff": "2026-03-15T18:00:00+00:00",
    "bookmaker_name": "Betfair",
}

SNAP_OK = {
    "snapshot_at": "2026-03-15T12:00:00+00:00",
    "snapshot_source": "kpi_panel_json.odds_meta.odds_fetched_at",
    "snapshot_fidelity": "verified_panel_odds_meta",
    "snapshot_timestamp_verified": True,
}


def test_phase1_available_complete_row():
    item = build_purchasability_feature_item(
        panel_row=_full_row(SEL_HOME),
        sibling_rows=_1x2_panel(),
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    assert item["phase_1_value"]["status"] == "available"
    assert item["phase_1_value"]["score"] is None
    assert item["phase_1_value"]["inputs"]["quota_book"] == 2.0
    assert item["phase_1_value"]["inputs"]["rating"] == 72
    assert item["phase_1_value"]["dependency_metadata"]["double_counting_prevention_required"] is True
    assert item["status"] == "not_calculated"
    assert item["score"] is None
    assert item["class"] is None


def test_phase1_partial_missing_derived():
    row = _full_row(SEL_HOME)
    row["rating"] = None
    row["edge_pct"] = None
    row["score_acquisto"] = None
    row["vantaggio_prob"] = None
    item = build_purchasability_feature_item(
        panel_row=row,
        sibling_rows=[row],
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    assert item["phase_1_value"]["status"] == "partial"
    assert item["phase_1_value"]["score"] is None


def test_phase1_unavailable_no_odds():
    row = {
        "market_key": SEL_HOME,
        "quota_book": None,
        "quota_cecchino": None,
        "prob_book": None,
        "prob_cecchino": None,
    }
    item = build_purchasability_feature_item(
        panel_row=row,
        sibling_rows=[row],
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    assert item["phase_1_value"]["status"] == "unavailable"


def test_rating_and_score_not_recomputed():
    row = _full_row(SEL_HOME, rating=88, score_acquisto=0.123)
    item = build_purchasability_feature_item(
        panel_row=row,
        sibling_rows=_1x2_panel()[:1] + [row] + _1x2_panel()[1:],
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    assert item["phase_1_value"]["inputs"]["rating"] == 88
    assert item["phase_1_value"]["inputs"]["score_acquisto"] == pytest.approx(0.123)


def test_case_a_home_comparator_away_gap_convention():
    rows = _1x2_panel()
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows, "bookmaker": {"name": "Betfair"}},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    home = next(i for i in batch["items"] if i["market_key"] == SEL_HOME)
    p2 = home["phase_2_quality"]
    assert p2["comparator_selections"] == [SEL_AWAY]
    assert p2["score"] is None
    ev = p2["comparator_evidence"][0]
    assert ev["market_key"] == SEL_AWAY
    # gap = selected - comparator
    if ev["book_probability_gap_vs_selected"] is not None:
        assert ev["book_probability_gap_vs_selected"] == pytest.approx(
            p2["fair_book_probability"] - ev["fair_book_probability"]
        )


def test_case_b_draw_strongest_comparator():
    rows = _1x2_panel()
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    draw = next(i for i in batch["items"] if i["market_key"] == SEL_DRAW)
    assert set(draw["phase_2_quality"]["comparator_selections"]) == {SEL_HOME, SEL_AWAY}
    assert draw["phase_2_quality"]["strongest_comparator_selection"] in (SEL_HOME, SEL_AWAY)


def test_case_c_dc_favourite_on_1x2_context():
    rows = _1x2_panel() + [
        _full_row(SEL_ONE_X, qb=1.35, qc=1.30, pb=1 / 1.35, pc=0.75),
    ]
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    onex = next(i for i in batch["items"] if i["market_key"] == SEL_ONE_X)
    p2 = onex["phase_2_quality"]
    assert p2["comparator_selections"] == [SEL_AWAY]
    assert p2["favourite_context_basis"] == "normalized_1x2"
    if p2["book_favourite"]:
        assert p2["book_favourite"]["selection"] in (SEL_HOME, SEL_DRAW, SEL_AWAY)


def test_case_d_over_25():
    rows = [
        _full_row(SEL_OVER_2_5, qb=1.90, qc=1.85, pb=1 / 1.9, pc=0.55),
        _full_row(SEL_UNDER_2_5, qb=2.05, qc=2.10, pb=1 / 2.05, pc=0.45),
    ]
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    over = next(i for i in batch["items"] if i["market_key"] == SEL_OVER_2_5)
    assert over["phase_2_quality"]["comparator_selections"] == [SEL_UNDER_2_5]
    assert over["phase_2_quality"]["period"] == "FT"
    assert over["phase_2_quality"]["line"] == 2.5


def test_case_e_f_alignment_no_bonus_penalty():
    rows = _1x2_panel()
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    for item in batch["items"]:
        assert item["score"] is None
        assert item["phase_2_quality"]["score"] is None
        al = item["phase_2_quality"]["favourite_alignment"]
        assert al in ("aligned", "disagree", "partial", "unavailable", None)


def test_case_g_large_gap_no_auto_penalty():
    rows = [
        _full_row(SEL_HOME, qb=3.0, qc=1.5, pb=1 / 3.0, pc=0.70),
        _full_row(SEL_DRAW, qb=3.5, qc=4.0, pb=1 / 3.5, pc=0.15),
        _full_row(SEL_AWAY, qb=3.0, qc=5.0, pb=1 / 3.0, pc=0.15),
    ]
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    home = next(i for i in batch["items"] if i["market_key"] == SEL_HOME)
    assert home["score"] is None
    assert "model_above_book" in home["reason_codes"] or "model_below_book" in home["reason_codes"] or "model_book_aligned" in home["reason_codes"] or "model_book_gap_unavailable" in home["reason_codes"]


def test_case_h_unsupported_opposition():
    rows = [_full_row(SEL_OVER_1_5, qb=1.25, qc=1.20, pb=0.8, pc=0.82)]
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    item = batch["items"][0]
    assert item["phase_2_quality"]["status"] == "unavailable"
    assert item["phase_2_quality"]["unsupported_reason"]
    assert item["phase_2_quality"]["comparator_evidence"] == []


def test_model_context_1x2_sums_to_one():
    rows = _1x2_panel()
    m = build_model_context_probability_map(rows)
    total = sum(m[s]["model_context_probability"] for s in (SEL_HOME, SEL_DRAW, SEL_AWAY))
    assert abs(total - 1.0) < 1e-9


def test_snapshot_fallback_not_ready():
    snap = {
        "snapshot_at": "2026-03-15T12:00:00+00:00",
        "snapshot_source": "cecchino_today_fixtures.updated_at",
        "snapshot_fidelity": "generic_updated_at_fallback",
        "snapshot_timestamp_verified": False,
    }
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": _1x2_panel()},
        fixture_meta=FIXTURE_META,
        snapshot_info=snap,
    )
    assert all(i["feature_status"] != "ready" for i in batch["items"])


def test_snapshot_post_kickoff_unavailable():
    snap = {
        **SNAP_OK,
        "snapshot_at": "2026-03-15T19:00:00+00:00",
    }
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": _1x2_panel()},
        fixture_meta=FIXTURE_META,
        snapshot_info=snap,
    )
    assert all(i["feature_status"] == "unavailable" for i in batch["items"])
    assert all("snapshot_not_before_kickoff" in i["reason_codes"] for i in batch["items"])


def test_no_settlement_or_result_fields_in_payload():
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": _1x2_panel()},
        fixture_meta=FIXTURE_META,
        snapshot_info=SNAP_OK,
    )
    blob = json.dumps(batch)
    for banned in (
        "settlement_status",
        "selection_won",
        "selection_lost",
        "unit_stake_profit",
        "ft_result",
        "historical_reliability",
    ):
        assert banned not in blob
    assert batch["no_score_formula"] is True
    assert batch["no_db_writes"] is True
    json.dumps(batch, allow_nan=False)


def test_no_historical_reliability_import():
    path = Path(__file__).resolve().parents[1] / "app/services/cecchino/cecchino_purchasability_features.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            joined = mod + " " + " ".join(names)
            assert "historical_reliability" not in joined


def test_fixture_missing_panel():
    fx = SimpleNamespace(
        id=5,
        local_fixture_id=None,
        provider_fixture_id=9,
        competition_id=1,
        scan_date=None,
        kickoff=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
        kpi_panel_json=None,
        odds_snapshot_json=None,
        odds_checked_at=None,
        updated_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        cecchino_output_json=None,
    )
    payload = build_purchasability_features_for_fixture(fx)
    assert payload["status"] == "unavailable"
    assert payload["items"] == []
    assert payload["no_score_formula"] is True


def _orm_fixture(
    *,
    fixture_id: int = 50,
    local_fixture_id: int | None = 900,
    cecchino_output_json: dict | None = None,
    panel: dict | None = None,
):
    """Fixture ORM-shaped: solo cecchino_output_json, nessun cecchino_output."""
    return SimpleNamespace(
        id=fixture_id,
        local_fixture_id=local_fixture_id,
        provider_fixture_id=1001,
        competition_id=7,
        scan_date="2026-03-15",
        kickoff=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
        kpi_panel_json=panel
        if panel is not None
        else {"rows": _1x2_panel(), "bookmaker": {"name": "Betfair"}},
        odds_snapshot_json={
            "odds_meta": {"odds_fetched_at": "2026-03-15T12:00:00+00:00"}
        },
        odds_checked_at=None,
        updated_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        cecchino_output_json=cecchino_output_json,
    )


def test_orm_local_fixture_id_distinct_from_today_id():
    fx = _orm_fixture(
        cecchino_output_json={
            "goal_intensity_v5_preview": {"version": "gi_v5_test"},
            "balance_v5": {"version": "balance_v5_test"},
        }
    )
    assert not hasattr(fx, "cecchino_output")
    payload = build_purchasability_features_for_fixture(fx)
    assert payload["items"]
    dq = payload["items"][0]["data_quality"]
    assert dq["today_fixture_id"] == 50
    assert dq["local_fixture_id"] == 900
    assert dq["today_fixture_id"] != dq["local_fixture_id"]
    hooks = payload["items"][0]["context_hooks"]
    assert hooks["goal_intensity_v5"]["status"] == "available_not_used"
    assert hooks["balance_v5"]["status"] == "available_not_used"
    for item in payload["items"]:
        assert item["score"] is None
        assert item["class"] is None
        assert item["phase_1_value"]["score"] is None
        assert item["phase_2_quality"]["score"] is None
        assert "purchasability_score_formula_not_implemented" in item["reason_codes"]
        assert "formula_not_implemented_phase_1" not in item["reason_codes"]


def test_orm_local_fixture_id_absent_stays_null():
    fx = _orm_fixture(local_fixture_id=None, cecchino_output_json=None)
    payload = build_purchasability_features_for_fixture(fx)
    dq = payload["items"][0]["data_quality"]
    assert dq["today_fixture_id"] == 50
    assert dq["local_fixture_id"] is None
    hooks = payload["items"][0]["context_hooks"]
    assert hooks["balance_v5"]["status"] == "not_connected"
    assert hooks["goal_intensity_v5"]["status"] == "not_connected"


def test_orm_goal_intensity_only_hook():
    fx = _orm_fixture(
        cecchino_output_json={
            "goal_intensity_v5": {"version": "gi_only"},
        }
    )
    payload = build_purchasability_features_for_fixture(fx)
    hooks = payload["items"][0]["context_hooks"]
    assert hooks["goal_intensity_v5"]["status"] == "available_not_used"
    assert hooks["balance_v5"]["status"] == "not_connected"
