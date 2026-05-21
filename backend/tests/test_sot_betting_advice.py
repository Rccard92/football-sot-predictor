"""Test consiglio giocata SOT — linee Over statistiche e caute."""

from __future__ import annotations

from app.services.sot_betting_advice_service import (
    CAUTIOUS_MARGIN,
    MATCH_TOTAL_LINES,
    advice_confidence_label,
    build_market_advice,
    cautious_line,
    risk_label,
    statistical_line,
)


def test_statistical_line_examples():
    assert statistical_line(7.67, MATCH_TOTAL_LINES) == 7.5
    assert statistical_line(6.42, MATCH_TOTAL_LINES) == 5.5
    assert statistical_line(5.88, MATCH_TOTAL_LINES) == 5.5
    assert statistical_line(4.10, MATCH_TOTAL_LINES) == 3.5


def test_cautious_line_examples():
    assert cautious_line(7.67, MATCH_TOTAL_LINES) == 6.5
    assert cautious_line(6.42, MATCH_TOTAL_LINES) == 5.5
    assert cautious_line(5.88, MATCH_TOTAL_LINES) == 4.5


def test_build_market_advice_767():
    out = build_market_advice("match_total_sot", 7.67)
    assert out["statistical_pick"] == "Over 7.5 SOT"
    assert out["statistical_margin"] == 0.17
    assert out["statistical_risk"] == "Molto tirata"
    assert out["cautious_pick"] == "Over 6.5 SOT"
    assert out["cautious_margin"] == 1.17


def test_build_market_advice_642():
    out = build_market_advice("match_total_sot", 6.42)
    assert out["statistical_pick"] == "Over 5.5 SOT"
    assert out["cautious_pick"] == "Over 5.5 SOT"
    assert out["cautious_margin"] == 0.92
    assert out["cautious_margin"] >= CAUTIOUS_MARGIN


def test_build_market_advice_588():
    out = build_market_advice("match_total_sot", 5.88)
    assert out["statistical_pick"] == "Over 5.5 SOT"
    assert out["statistical_margin"] == 0.38
    assert out["cautious_pick"] == "Over 4.5 SOT"
    assert out["cautious_margin"] == 1.38


def test_risk_label_thresholds():
    assert risk_label(0.10) == "Molto tirata"
    assert risk_label(0.30) == "Aggressiva"
    assert risk_label(0.60) == "Moderata"
    assert risk_label(1.00) == "Buon margine"
    assert risk_label(1.50) == "Forte margine"


def test_no_statistical_pick_when_too_low():
    out = build_market_advice("match_total_sot", 3.2)
    assert out["statistical_pick"] is None
    assert "Nessuna" in " ".join(out["reasons"])
