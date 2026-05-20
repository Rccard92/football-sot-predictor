"""Test scoring matching SportAPI — caso Fiorentina vs Atalanta."""

from __future__ import annotations

from app.services.sportapi.sportapi_matching_service import _recommendation, _score_candidate


def _atalanta_fiorentina_event() -> dict:
    return {
        "id": 13980080,
        "startTimestamp": 1779475500,
        "homeTeam": {"id": 2693, "name": "Fiorentina"},
        "awayTeam": {"id": 2686, "name": "Atalanta"},
        "tournament": {
            "name": "Serie A",
            "id": 33,
            "uniqueTournament": {"id": 23, "country": {"name": "Italy"}},
        },
        "season": {"id": 76457, "name": "Serie A 25/26"},
        "roundInfo": {"round": 38},
    }


def test_score_fiorentina_atalanta_auto_safe():
    ev = _atalanta_fiorentina_event()
    score, breakdown = _score_candidate(
        fixture_ts=1779475500,
        home_name="Fiorentina",
        away_name="Atalanta",
        league_name="Serie A",
        round_num=38,
        ev=ev,
    )
    assert score >= 90
    assert _recommendation(score) == "AUTO_SAFE"
    assert breakdown.get("timestamp_exact") == 40
    assert breakdown.get("home_team") == 25
    assert breakdown.get("away_team") == 25


def test_recommendation_thresholds():
    assert _recommendation(90) == "AUTO_SAFE"
    assert _recommendation(80) == "REVIEW"
    assert _recommendation(50) == "NO_MATCH"
