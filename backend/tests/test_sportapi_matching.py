"""Unit test matching/scoring SportAPI (senza chiamate HTTP)."""

from app.services.sportapi.sportapi_matching_service import _recommendation, _score_candidate
from app.services.sportapi.sportapi_payload import extract_events_list


def test_extract_events_list_reads_events_key():
    ev = {"id": 13980080, "homeTeam": {"name": "Fiorentina"}, "awayTeam": {"name": "Atalanta"}}
    body = {"events": [ev]}
    assert extract_events_list(body) == [ev]


def test_score_candidate_fiorentina_atalanta_auto_safe():
    fixture_ts = 1779475500
    ev = {
        "id": 13980080,
        "startTimestamp": fixture_ts,
        "homeTeam": {"name": "Fiorentina"},
        "awayTeam": {"name": "Atalanta"},
        "tournament": {
            "name": "Serie A",
            "country": {"name": "Italy", "alpha2": "IT"},
        },
        "roundInfo": {"round": 38},
    }

    score, breakdown = _score_candidate(
        fixture_ts=fixture_ts,
        home_name="Fiorentina",
        away_name="Atalanta",
        league_name="Serie A",
        round_num=38,
        ev=ev,
    )

    assert score >= 90
    assert breakdown["timestamp_exact"] == 40
    assert breakdown["home_team"] == 25
    assert breakdown["away_team"] == 25
    assert breakdown["competition"] == 10
    assert breakdown["round"] == 5
    assert _recommendation(score) == "AUTO_SAFE"
