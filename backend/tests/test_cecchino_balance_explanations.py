"""Test servizio balance-explanations (audit diagnostico 4 pilastri)."""

from __future__ import annotations

import json
import math
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino.cecchino_balance_explanations import (
    AUDIT_VERSION,
    PILLAR_AUDIT_KEYS,
    build_balance_explanations,
    get_balance_explanations,
)
from app.services.cecchino.cecchino_balance_v5 import (
    VERSION as BALANCE_VERSION,
    build_cecchino_balance_v5,
    classify_conviction,
    classify_gap_coherence,
    conviction_index,
    gap_coherence_index,
    probability_balance_index,
)


def _final(**kwargs):
    defaults = dict(
        status="available",
        quota_1=4.59,
        quota_x=3.40,
        quota_2=2.13,
        prob_1=0.20,
        prob_x=0.2924,
        prob_2=0.5076,
    )
    defaults.update(kwargs)
    return defaults


def _goal_markets():
    return {
        "under_2_5": {"final_odd": 1.35},
        "over_2_5": {"final_odd": 3.90},
    }


def _fixture(**overrides):
    base = dict(
        id=42,
        local_fixture_id=7,
        provider_fixture_id=999001,
        home_team_name="Squadra A",
        away_team_name="Squadra B",
        kickoff=None,
        scan_date=date(2026, 7, 25),
        eligibility_status="eligible",
        cecchino_output_json={
            "final": _final(),
            "goal_markets": _goal_markets(),
        },
        kpi_panel_json=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_get_not_found():
    db = MagicMock()
    db.get.return_value = None
    assert get_balance_explanations(db, 1) is None


def test_not_eligible():
    db = MagicMock()
    db.get.return_value = _fixture(eligibility_status="excluded_cup")
    out = get_balance_explanations(db, 42)
    assert out["status"] == "error"
    assert out["code"] == "not_eligible"


def test_balance_absent():
    db = MagicMock()
    db.get.return_value = _fixture(cecchino_output_json={})
    out = get_balance_explanations(db, 42)
    assert out["status"] == "error"
    assert out["code"] == "balance_not_available"


def test_audit_complete_four_pillars():
    out = build_balance_explanations(_fixture())
    assert out["status"] in ("ok", "partial")
    assert out["audit_version"] == AUDIT_VERSION
    assert out["module"] == "balance_v5"
    assert out["no_operational_recalculation"] is True
    assert out["diagnostic_re_evaluation_only"] is True
    assert set(out["pillars"]) == {"geometry", "conviction", "draw_credibility", "coherence_1_2"}
    order = [k for k, *_ in PILLAR_AUDIT_KEYS]
    assert list(out["pillars"].keys()) == order or all(k in out["pillars"] for k in order)
    for i, (audit_key, _canon, num, title) in enumerate(PILLAR_AUDIT_KEYS, start=1):
        p = out["pillars"][audit_key]
        assert p["pillar_number"] == num == i
        assert p["title"] == title


def test_pillar_badges_official_descriptive():
    out = build_balance_explanations(_fixture())
    assert out["pillars"]["geometry"]["badge"] == "UFFICIALE"
    assert out["pillars"]["geometry"]["classification_type"] == "official"
    assert out["pillars"]["conviction"]["badge"] == "UFFICIALE"
    assert out["pillars"]["draw_credibility"]["badge"] == "DESCRITTIVO"
    assert out["pillars"]["draw_credibility"]["classification_type"] == "descriptive"
    assert out["pillars"]["coherence_1_2"]["badge"] == "UFFICIALE"
    assert "descrittivo" in (out["pillars"]["draw_credibility"]["methodological_caution"] or "").lower()


def test_geometry_f36_signed_abs_direction():
    out = build_balance_explanations(_fixture())
    geo = out["pillars"]["geometry"]
    can = geo["canonical_audit_result"]
    # q2=2.13, q1=4.59 → signed negative → lato 2
    assert can["f36_signed"] == pytest.approx(2.13 - 4.59, abs=1e-6)
    assert can["f36_abs"] == pytest.approx(abs(2.13 - 4.59), abs=1e-6)
    assert can["direction"] == "2"
    assert can["class"] == "Squilibrio"
    assert can["value"] == 40
    assert "F36" in geo["formula_symbolic"]
    assert any("F36_signed =" in s or "F36 =" in s for s in geo["formula_applied"])
    assert geo["consistency"]["status"] in ("match", "rounding_match")
    assert can.get("base_index") == 40
    assert can.get("gap_coherence_f36_input") == 40
    assert "SEZIONE" in geo["formula_symbolic"]
    assert geo.get("audit_version") == AUDIT_VERSION
    assert AUDIT_VERSION == "cecchino_balance_explanations_v2"


def test_conviction_gap_and_dominant():
    out = build_balance_explanations(_fixture())
    conv = out["pillars"]["conviction"]
    can = conv["canonical_audit_result"]
    assert can["direction"] == "2"
    assert can["dominance_pp"] is not None
    assert can["top_prob"] is not None
    assert can["second_prob"] is not None
    assert can["top_prob"] >= can["second_prob"]
    assert "convinzione" in conv["formula_symbolic"].lower() or "max" in conv["formula_symbolic"].lower()
    assert conv["consistency"]["status"] in ("match", "rounding_match")


def test_draw_x_rank_and_under_over():
    out = build_balance_explanations(_fixture())
    draw = out["pillars"]["draw_credibility"]
    can = draw["canonical_audit_result"]
    assert can["x_rank"] in (1, 2, 3)
    assert can["under_2_5_norm"] is not None
    assert can["over_2_5_norm"] is not None
    assert abs(can["under_2_5_norm"] + can["over_2_5_norm"] - 100) < 0.1
    assert can["value"] is not None
    assert draw["consistency"]["status"] in ("match", "rounding_match")


def test_coherence_gap_and_formula():
    out = build_balance_explanations(_fixture())
    coh = out["pillars"]["coherence_1_2"]
    can = coh["canonical_audit_result"]
    assert can["gap_pp"] is not None
    assert can["prob_balance"] is not None
    assert can["f36_score"] is not None
    assert "prob_balance" in coh["formula_symbolic"] or "coerenza" in coh["formula_symbolic"].lower()
    assert coh["consistency"]["status"] in ("match", "rounding_match")


def test_classification_trace_present():
    out = build_balance_explanations(_fixture())
    for key in ("geometry", "conviction", "draw_credibility", "coherence_1_2"):
        trace = out["pillars"][key]["classification_trace"]
        assert isinstance(trace, list) and len(trace) >= 2
        assert any(t.get("matched") for t in trace)


def test_source_mode_derived():
    out = build_balance_explanations(_fixture())
    assert out["source_mode"] == "derived_read_only_from_stored_snapshot"


def test_source_mode_persisted():
    row = _fixture()
    output = dict(row.cecchino_output_json)
    output["balance_v5_monitoring"] = {
        "status": "ok",
        "f36_index": 40,
        "prob_1_norm": 20.0,
        "source_mode": "prospective_scan",
    }
    row.cecchino_output_json = output
    out = build_balance_explanations(row)
    assert out["source_mode"] == "persisted_balance_v5_monitoring"


def test_parity_displayed_equals_audit():
    out = build_balance_explanations(_fixture())
    for key, pillar in out["pillars"].items():
        disp = pillar["displayed_result"]
        can = pillar["canonical_audit_result"]
        if disp.get("value") is not None and can.get("value") is not None:
            assert abs(float(disp["value"]) - float(can["value"])) <= 0.01, key
        if disp.get("class") is not None and can.get("class") is not None:
            assert disp["class"] == can["class"], key
        if key in ("geometry", "conviction"):
            if disp.get("direction") is not None and can.get("direction") is not None:
                assert str(disp["direction"]) == str(can["direction"]), key
        assert pillar["consistency"]["status"] in ("match", "rounding_match"), key


def test_parity_with_balance_builder():
    row = _fixture()
    out = build_balance_explanations(row)
    balance = build_cecchino_balance_v5(
        cecchino_final=row.cecchino_output_json["final"],
        goal_markets=row.cecchino_output_json["goal_markets"],
    )
    mapping = {
        "geometry": "f36",
        "conviction": "dominance",
        "draw_credibility": "draw_credibility",
        "coherence_1_2": "gap_coherence",
    }
    for audit_key, canon_key in mapping.items():
        pillar = balance["pillars"][canon_key]
        expl = out["pillars"][audit_key]
        assert expl["displayed_result"]["value"] == pillar["index"]
        assert expl["displayed_result"]["class"] == pillar["class_label"]
        assert expl["displayed_result"]["direction"] == pillar["direction"]


@pytest.mark.parametrize(
    "quota_1,quota_2,expected_class,expected_score",
    [
        (2.10, 2.20, "Equilibrio forte", 100),  # abs 0.10
        (2.10, 2.80, "Equilibrio", 80),  # abs 0.70
        (2.10, 3.40, "Transizione", 60),  # abs 1.30
        (2.10, 4.00, "Squilibrio", 40),  # abs 1.90
        (2.10, 2.60, "Equilibrio forte", 100),  # abs 0.50 boundary (<=0.50)
        (2.10, 2.61, "Equilibrio", 80),  # just above 0.50
        (2.10, 3.10, "Equilibrio", 80),  # abs 1.00 boundary (<=1.00)
        (2.10, 3.11, "Transizione", 60),  # just above 1.00
        (2.10, 3.60, "Transizione", 60),  # abs 1.50 boundary (<=1.50)
        (2.10, 3.61, "Squilibrio", 40),  # just above 1.50
    ],
)
def test_geometry_threshold_cases(quota_1, quota_2, expected_class, expected_score):
    row = _fixture(
        cecchino_output_json={
            "final": _final(quota_1=quota_1, quota_2=quota_2),
            "goal_markets": _goal_markets(),
        }
    )
    geo = build_balance_explanations(row)["pillars"]["geometry"]
    assert geo["canonical_audit_result"]["class"] == expected_class
    assert geo["canonical_audit_result"]["value"] == expected_score


@pytest.mark.parametrize(
    "probs,expected_side",
    [
        ((0.55, 0.25, 0.20), "1"),
        ((0.20, 0.55, 0.25), "X"),
        ((0.20, 0.25, 0.55), "2"),
    ],
)
def test_conviction_dominant_scenarios(probs, expected_side):
    p1, px, p2 = probs
    row = _fixture(
        cecchino_output_json={
            "final": _final(prob_1=p1, prob_x=px, prob_2=p2),
            "goal_markets": _goal_markets(),
        }
    )
    conv = build_balance_explanations(row)["pillars"]["conviction"]
    assert conv["canonical_audit_result"]["direction"] == expected_side
    idx = conviction_index(p1 * 100, px * 100, p2 * 100)
    # builder normalizes raw 0-1 to percent then renormalizes — use builder result
    assert conv["canonical_audit_result"]["class"] == classify_conviction(
        conv["canonical_audit_result"]["value"]
    )


@pytest.mark.parametrize(
    "quota_x,expected",
    [
        (3.00, "Pareggio forte"),
        (3.20, "Pareggio forte"),
        (3.21, "Pareggio possibile"),
        (3.60, "Pareggio possibile"),
        (3.61, "Pareggio debole"),
        (4.20, "Pareggio debole"),
        (4.21, "Pareggio poco probabile"),
    ],
)
def test_draw_threshold_cases(quota_x, expected):
    row = _fixture(
        cecchino_output_json={
            "final": _final(quota_x=quota_x),
            "goal_markets": _goal_markets(),
        }
    )
    draw = build_balance_explanations(row)["pillars"]["draw_credibility"]
    assert draw["canonical_audit_result"]["class"] == expected


@pytest.mark.parametrize(
    "probs,expected_rank",
    [
        ((0.25, 0.50, 0.25), 1),  # X first
        ((0.40, 0.35, 0.25), 2),  # X second
        ((0.45, 0.20, 0.35), 3),  # X third
    ],
)
def test_draw_x_rank_positions(probs, expected_rank):
    p1, px, p2 = probs
    row = _fixture(
        cecchino_output_json={
            "final": _final(prob_1=p1, prob_x=px, prob_2=p2, quota_x=3.40),
            "goal_markets": _goal_markets(),
        }
    )
    draw = build_balance_explanations(row)["pillars"]["draw_credibility"]
    assert draw["canonical_audit_result"]["x_rank"] == expected_rank


def test_coherence_classes_via_canonical():
    # Strong alignment: balanced probs + balanced F36
    row = _fixture(
        cecchino_output_json={
            "final": _final(quota_1=2.20, quota_2=2.30, prob_1=0.34, prob_x=0.32, prob_2=0.34),
            "goal_markets": _goal_markets(),
        }
    )
    coh = build_balance_explanations(row)["pillars"]["coherence_1_2"]
    assert coh["canonical_audit_result"]["class"] in (
        "Confermato",
        "Fortemente Confermato",
        "Parziale",
    )
    idx = coh["canonical_audit_result"]["value"]
    assert classify_gap_coherence(idx) == coh["canonical_audit_result"]["class"]


def test_json_safe_no_nan_infinity():
    out = build_balance_explanations(_fixture())
    raw = json.dumps(out, allow_nan=False)
    assert "NaN" not in raw
    assert "Infinity" not in raw
    parsed = json.loads(raw)
    assert parsed["pillars"]["geometry"]["pillar_number"] == 1


def test_no_post_match_fields():
    out = build_balance_explanations(_fixture())
    blob = json.dumps(out).lower()
    for forbidden in ("settlement", "ft_result", "final_score", "goals_home", "goals_away"):
        assert forbidden not in blob


def test_no_db_write():
    db = MagicMock()
    db.get.return_value = _fixture()
    get_balance_explanations(db, 42)
    assert db.commit.call_count == 0
    assert db.add.call_count == 0
    assert db.flush.call_count == 0


def test_overview_and_version():
    out = build_balance_explanations(_fixture())
    assert out["overview"]["version"] == BALANCE_VERSION
    assert out["overview"]["pre_match_only"] is True
    assert "geometry" in out["overview"]["official_pillars"]
    assert "draw_credibility" in out["overview"]["descriptive_pillars"]


def test_partial_when_pillar_unavailable():
    row = _fixture(
        cecchino_output_json={
            "final": _final(quota_1=None, quota_2=None),
            "goal_markets": _goal_markets(),
        }
    )
    # final still available but F36 missing — builder may still return ok with unavailable pillar
    final = row.cecchino_output_json["final"]
    final["quota_1"] = None
    final["quota_2"] = None
    out = build_balance_explanations(row)
    assert out["status"] in ("ok", "partial", "error")
    if out["status"] != "error":
        assert out["pillars"]["geometry"]["status"] in ("unavailable", "partial")


def test_consistency_match_helper_via_identical():
    out = build_balance_explanations(_fixture())
    for p in out["pillars"].values():
        assert p["consistency"]["status"] != "mismatch"


def test_finite_numbers_only():
    out = build_balance_explanations(_fixture())

    def walk(obj):
        if isinstance(obj, float):
            assert math.isfinite(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(out)
