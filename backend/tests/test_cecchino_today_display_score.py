"""Test score PT/FT Cecchino Today display."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.cecchino_today_fixture import MATCH_FINISHED, MATCH_UPCOMING
from app.services.cecchino.cecchino_today_display import extract_display_assets, row_score_payload


def test_extract_halftime_scores():
    assets = extract_display_assets(
        {
            "league": {},
            "teams": {"home": {}, "away": {}},
            "fixture": {"status": {"short": "FT", "elapsed": 90}},
            "goals": {"home": 2, "away": 1},
            "score": {
                "halftime": {"home": 1, "away": 0},
                "fulltime": {"home": 2, "away": 1},
            },
        },
    )
    assert assets["score_halftime_home"] == 1
    assert assets["score_halftime_away"] == 0
    assert assets["score_fulltime_home"] == 2


def test_row_score_payload_nested():
    row = SimpleNamespace(
        match_display_status=MATCH_FINISHED,
        score_halftime_home=1,
        score_halftime_away=0,
        score_fulltime_home=2,
        score_fulltime_away=1,
        goals_home=2,
        goals_away=1,
    )
    score = row_score_payload(row)
    assert score["halftime"]["available"] is True
    assert score["halftime"]["home"] == 1
    assert score["fulltime"]["home"] == 2


def test_row_score_upcoming_empty():
    row = SimpleNamespace(
        match_display_status=MATCH_UPCOMING,
        score_halftime_home=None,
        score_halftime_away=None,
        score_fulltime_home=None,
        score_fulltime_away=None,
        goals_home=None,
        goals_away=None,
    )
    score = row_score_payload(row)
    assert score["halftime"]["available"] is False
    assert score["fulltime"]["available"] is False
