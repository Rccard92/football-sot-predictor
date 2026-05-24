"""Test report rapido Prossima giornata."""

from __future__ import annotations

from app.services.next_round_quick_report_service import _slim_lineup_refresh_impact


def test_slim_lineup_refresh_impact_strips_payloads():
    full = {
        "has_comparison": True,
        "delta_total_sot": 1.5,
        "main_reason": "Cambio titolari",
        "before_payload": {"predicted_total_sot": 7.0, "raw": "heavy"},
        "after_payload": {"predicted_total_sot": 8.5},
        "before_total_sot": 7.0,
        "after_total_sot": 8.5,
    }
    slim = _slim_lineup_refresh_impact(full)
    assert "before_payload" not in slim
    assert "after_payload" not in slim
    assert slim.get("delta_total_sot") == 1.5
    assert slim.get("main_reason") == "Cambio titolari"
