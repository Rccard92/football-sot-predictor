"""Unit test scoring K.3 mapping fixture SportAPI."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.sportapi.sportapi_fixture_mapping_scoring import (
    pick_best_candidate,
    score_mapping_candidate,
)


def _ev(
    *,
    eid: int,
    ts: int,
    home: str,
    away: str,
    round_n: int | None = 37,
) -> dict:
    return {
        "id": eid,
        "startTimestamp": ts,
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "tournament": {"name": "Serie A", "country": {"name": "Italy"}},
        "roundInfo": {"round": round_n},
    }


def test_same_day_required():
    fixture_ts = int(datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc).timestamp())
    match_date = date(2024, 5, 18)
    wrong_day_ts = int(datetime(2024, 5, 19, 18, 45, tzinfo=timezone.utc).timestamp())
    ev = _ev(eid=100, ts=wrong_day_ts, home="Inter", away="Lazio")

    row = score_mapping_candidate(
        fixture_ts=fixture_ts,
        match_date=match_date,
        home_name="Inter",
        away_name="Lazio",
        round_num=37,
        ev=ev,
    )

    assert row.score == 0.0
    assert row.confidence == "none"
    assert row.breakdown.get("same_day") is False


def test_high_confidence_serie_a_match():
    fixture_ts = int(datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc).timestamp())
    match_date = date(2024, 5, 18)
    ev = _ev(eid=146001, ts=fixture_ts, home="Inter", away="Lazio", round_n=37)

    row = score_mapping_candidate(
        fixture_ts=fixture_ts,
        match_date=match_date,
        home_name="Inter",
        away_name="Lazio",
        round_num=37,
        ev=ev,
    )

    assert row.score >= 85
    assert row.confidence == "high"
    assert row.breakdown["home_team"] == 35
    assert row.breakdown["away_team"] == 35
    assert row.breakdown["kickoff_within_15m"] == 20
    assert row.breakdown["round"] == 10


def test_ambiguous_high_matches():
    fixture_ts = int(datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc).timestamp())
    match_date = date(2024, 5, 18)
    c1 = score_mapping_candidate(
        fixture_ts=fixture_ts,
        match_date=match_date,
        home_name="Inter",
        away_name="Lazio",
        round_num=37,
        ev=_ev(eid=1, ts=fixture_ts, home="Inter", away="Lazio"),
    )
    c2 = score_mapping_candidate(
        fixture_ts=fixture_ts,
        match_date=match_date,
        home_name="Inter",
        away_name="Lazio",
        round_num=37,
        ev=_ev(eid=2, ts=fixture_ts + 60, home="Inter", away="Lazio"),
    )

    best, ambiguous, warnings = pick_best_candidate([c1, c2])
    assert best is not None
    assert ambiguous is True
    assert warnings


def test_medium_confidence_no_round_bonus():
    fixture_ts = int(datetime(2024, 5, 18, 18, 45, tzinfo=timezone.utc).timestamp())
    match_date = date(2024, 5, 18)
    ev = _ev(eid=3, ts=fixture_ts + 3600, home="Inter", away="Lazio", round_n=99)

    row = score_mapping_candidate(
        fixture_ts=fixture_ts,
        match_date=match_date,
        home_name="Inter",
        away_name="Lazio",
        round_num=37,
        ev=ev,
    )

    assert 70 <= row.score < 85
    assert row.confidence == "medium"
    assert row.breakdown["round"] == 0
