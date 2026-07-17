"""Test Preview v5 Equilibrio vs Squilibrio — Fase 2A."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.encoders import jsonable_encoder

from app.services.cecchino.cecchino_balance_analysis import (
    VERSION as BALANCE_VERSION,
    build_cecchino_balance_analysis,
)
from app.services.cecchino.cecchino_balance_research_candidates import (
    RESEARCH_CANDIDATES_VERSION,
    conviction_index_candidate,
    dominant_side_to_market_label,
    gap_coherence_index_candidate,
    probability_balance_index,
)
from app.services.cecchino.cecchino_balance_v5_preview import (
    VERSION,
    build_balance_v5_preview,
)
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_HOME, SEL_UNDER_2_5


def _balance(**kwargs):
    defaults = dict(
        quota_cecchino_1=2.10,
        quota_cecchino_x=3.40,
        quota_cecchino_2=3.60,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    )
    defaults.update(kwargs)
    return build_cecchino_balance_analysis(**defaults)


def _kpi_with_book():
    return {
        "version": "cecchino_kpi_v2_betfair",
        "rows": [
            {"market_key": SEL_HOME, "quota_cecchino": 2.1, "quota_book": 2.2},
            {"market_key": SEL_DRAW, "quota_cecchino": 3.4, "quota_book": 3.5},
            {"market_key": "2", "quota_cecchino": 3.6, "quota_book": 3.7},
            {"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85, "quota_book": 1.9},
            {"market_key": "OVER_2_5", "quota_cecchino": 2.05, "quota_book": 2.1},
        ],
    }


def test_version_is_v1_1():
    assert VERSION == "balance_v5_preview_v1_1"
    preview = build_balance_v5_preview(balance_analysis=_balance())
    assert preview["version"] == VERSION
    assert preview["status"] == "ok"


def test_identity_inconsistent_blocks_preview():
    preview = build_balance_v5_preview(
        balance_analysis=_balance(),
        identity_consistency={"status": "inconsistent", "warnings": ["fixture_kickoff_mismatch"]},
    )
    assert preview["status"] == "unavailable"
    assert preview["version"] == VERSION
    assert preview["production_changes"] is False
    assert "fixture_identity_mismatch" in preview["warnings"]
    assert all(p["status"] == "unavailable" and p["index"] is None for p in preview["pillars"])
    assert preview["market_deviation"]["status"] == "unavailable"
    assert preview["market_deviation"]["pairs"] == []


def test_f36_uses_productive_value_not_recalculated():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal)
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    assert f36["status"] == "official"
    assert f36["index"] == bal["f36"]["score"]
    assert f36["class_label"] == bal["f36"]["label"]
    # pass-through: stesso score, nessuna soglia nuova
    assert f36["index"] in (40, 60, 80, 100)


def test_dominance_maps_home_draw_away_to_1x2():
    assert dominant_side_to_market_label("HOME") == "1"
    assert dominant_side_to_market_label("DRAW") == "X"
    assert dominant_side_to_market_label("AWAY") == "2"
    bal = _balance(prob_cecchino_1=0.50, prob_cecchino_x=0.25, prob_cecchino_2=0.25)
    preview = build_balance_v5_preview(balance_analysis=bal)
    dom = next(p for p in preview["pillars"] if p["key"] == "dominance")
    assert dom["direction"] == "1"


def test_dominance_research_when_candidate_available():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal)
    dom = next(p for p in preview["pillars"] if p["key"] == "dominance")
    assert dom["status"] == "research"
    assert dom["index"] is not None
    expected = conviction_index_candidate(42.0, 28.0, 30.0)
    assert abs(dom["index"] - expected) < 0.01


def test_draw_credibility_calibration_pending_null_index_no_book():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal, kpi_panel=_kpi_with_book())
    dc = next(p for p in preview["pillars"] if p["key"] == "draw_credibility")
    assert dc["status"] == "calibration_pending"
    assert dc["index"] is None
    assert dc["class_label"] is None
    blob = str(dc).lower()
    assert "quota_book" not in blob
    assert "prob_book" not in blob
    for c in dc["components"]:
        assert "book" not in c["key"].lower()
        assert "book" not in c["label"].lower()


def test_gap_research_when_candidate_available():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal)
    gap = next(p for p in preview["pillars"] if p["key"] == "gap_coherence")
    assert gap["status"] == "research"
    assert gap["index"] is not None
    pb = probability_balance_index(42.0, 30.0)
    expected = gap_coherence_index_candidate(bal["f36"]["score"], pb)
    assert abs(gap["index"] - expected) < 0.01


def test_gap_calibration_pending_when_absent():
    preview = build_balance_v5_preview(
        balance_analysis={"status": "insufficient_data", "version": "x", "inputs": {}, "f36": {}},
    )
    gap = next(p for p in preview["pillars"] if p["key"] == "gap_coherence")
    assert gap["status"] == "calibration_pending"
    assert gap["index"] is None


def test_market_separated_from_pillars():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal, kpi_panel=_kpi_with_book())
    assert "market_deviation" in preview
    assert preview["market_deviation"]["title"] == "Scostamento dal mercato"
    assert "mercato non modifica" in preview["market_deviation"]["subtitle"].lower()
    pillar_keys = {p["key"] for p in preview["pillars"]}
    assert "market" not in pillar_keys
    assert "market_deviation" not in pillar_keys
    assert any(p.get("quota_book") for p in preview["market_deviation"]["pairs"])


def test_no_new_formula_f36_unchanged_and_production_false():
    bal = _balance()
    score_before = bal["f36"]["score"]
    preview = build_balance_v5_preview(balance_analysis=bal)
    assert preview["production_changes"] is False
    assert preview["version"] == VERSION
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    assert f36["index"] == score_before


def test_json_serializable_and_no_db_writes():
    db = MagicMock()
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal, kpi_panel=_kpi_with_book())
    jsonable_encoder(preview)
    assert not db.add.called
    assert not db.commit.called


def test_pillar_order():
    preview = build_balance_v5_preview(balance_analysis=_balance())
    keys = [p["key"] for p in preview["pillars"]]
    assert keys == ["f36", "dominance", "draw_credibility", "gap_coherence"]


def test_f36_reading_not_predictive():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal)
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    reading = f36["reading"].lower()
    assert "il modello tende" not in reading
    assert "prevede" not in reading
    assert "favorito" not in reading
    assert "tende a vincere" not in reading


def test_f36_imbalance_structural_reading():
    # |F36| > 1.5 → Squilibrio; signed > 0 → lato 1
    bal = _balance(quota_cecchino_1=2.0, quota_cecchino_2=4.0, quota_cecchino_x=3.2)
    assert bal["f36"]["class_key"] == "imbalance"
    preview = build_balance_v5_preview(balance_analysis=bal)
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    assert "sbilanciata verso il lato 1" in f36["reading"]
    assert f36["index"] == bal["f36"]["score"]


def test_f36_balance_structural_reading():
    bal = _balance(quota_cecchino_1=2.05, quota_cecchino_2=2.10, quota_cecchino_x=3.40)
    assert bal["f36"]["class_key"] in ("strong_balance", "balance")
    preview = build_balance_v5_preview(balance_analysis=bal)
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    assert "relativamente vicine" in f36["reading"] or "appare equilibrata" in f36["reading"]
    assert "il modello tende" not in f36["reading"].lower()


def test_source_versions_research_vs_balance_v4():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal)
    by_key = {p["key"]: p for p in preview["pillars"]}
    assert by_key["f36"]["source_version"] == BALANCE_VERSION
    assert by_key["f36"]["source_version"] == "cecchino_balance_analysis_v4"
    assert by_key["dominance"]["source_version"] == RESEARCH_CANDIDATES_VERSION
    assert by_key["gap_coherence"]["source_version"] == RESEARCH_CANDIDATES_VERSION
    assert by_key["draw_credibility"]["source_version"] is None


def test_market_labels_simplified():
    preview = build_balance_v5_preview(balance_analysis=_balance(), kpi_panel=_kpi_with_book())
    labels = [p["label"] for p in preview["market_deviation"]["pairs"]]
    assert labels == ["Segno X", "Segno 1", "Segno 2", "Under 2.5", "Over 2.5"]


def test_gap_reading_no_market_disclaimer_and_linked_to_f36():
    bal = _balance(quota_cecchino_1=2.0, quota_cecchino_2=4.0)
    preview = build_balance_v5_preview(balance_analysis=bal)
    gap = next(p for p in preview["pillars"] if p["key"] == "gap_coherence")
    assert "suggerimento di mercato" not in gap["reading"].lower()
    if bal["f36"]["class_key"] == "imbalance" and gap["status"] == "research":
        assert "squilibrio" in gap["reading"].lower() or "non conferma" in gap["reading"].lower()


def test_indices_unchanged_vs_candidates():
    bal = _balance()
    preview = build_balance_v5_preview(balance_analysis=bal)
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    dom = next(p for p in preview["pillars"] if p["key"] == "dominance")
    gap = next(p for p in preview["pillars"] if p["key"] == "gap_coherence")
    assert f36["index"] == bal["f36"]["score"]
    assert abs(dom["index"] - conviction_index_candidate(42.0, 28.0, 30.0)) < 0.01
    pb = probability_balance_index(42.0, 30.0)
    assert abs(gap["index"] - gap_coherence_index_candidate(bal["f36"]["score"], pb)) < 0.01
