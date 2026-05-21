"""Test delta e motivi refresh formazioni."""

from app.services.sportapi.lineup_refresh_impact_service import (
    FLAT_THRESHOLD,
    LineupRefreshImpactService,
    direction_for_delta,
)


def _snap(home_sot: float, away_sot: float, **home_kw) -> dict:
    home = {
        "predicted_sot": home_sot,
        "offensive_lineup_factor": 1.0,
        "opponent_defensive_weakness_factor": 1.0,
        "lineup_players": [],
        "missing_players": [],
        **home_kw,
    }
    away = {
        "predicted_sot": away_sot,
        "offensive_lineup_factor": 1.0,
        "opponent_defensive_weakness_factor": 1.0,
        "lineup_players": [],
        "missing_players": [],
    }
    return {
        "fixture_id": 1,
        "v20_available": True,
        "home_team_name": "Milan",
        "away_team_name": "Cagliari",
        "predicted_home_sot": home_sot,
        "predicted_away_sot": away_sot,
        "predicted_total_sot": round(home_sot + away_sot, 3),
        "home": home,
        "away": away,
    }


def test_direction_thresholds():
    assert direction_for_delta(0.11) == "UP"
    assert direction_for_delta(-0.11) == "DOWN"
    assert direction_for_delta(0.05) == "FLAT"
    assert direction_for_delta(-FLAT_THRESHOLD) == "FLAT"
    assert direction_for_delta(FLAT_THRESHOLD) == "FLAT"


def test_compare_total_down():
    before = _snap(4.0, 3.67)
    after = _snap(3.5, 3.60)
    out = LineupRefreshImpactService().compare(before, after)
    assert out["direction_total"] == "DOWN"
    assert out["delta_total_sot"] == -0.57


def test_starter_removed_reason():
    before = _snap(
        4.0,
        3.0,
        lineup_players=[
            {"player_id": 1, "player_name": "Rafael Leão", "lineup_status": "STARTER"},
        ],
    )
    after = _snap(
        3.5,
        3.0,
        lineup_players=[
            {"player_id": 1, "player_name": "Rafael Leão", "lineup_status": "BENCH"},
        ],
    )
    out = LineupRefreshImpactService().compare(before, after)
    texts = " ".join(r["text"] for r in out["reasons"])
    assert "non è più titolare" in texts or "Leão" in texts
    assert out["main_reason"]


def test_flat_no_changes():
    before = _snap(4.0, 3.67)
    after = _snap(4.02, 3.65)
    out = LineupRefreshImpactService().compare(before, after)
    assert out["direction_total"] == "FLAT"
