"""Normalizzazione pura delle forme API-Football v3 (docs/v4/API.md)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.cecchino_v4.live.normalize import (
    api_season_for,
    classify_bet,
    format_line,
    market_family,
    normalize_bets,
    normalize_events,
    normalize_fixture,
    normalize_injuries,
    normalize_lineups,
    normalize_odds_item,
    normalize_players,
    normalize_standings,
    normalize_statistics,
    season_label_from_api,
    snapshot_kind_for,
)
from tests.v4.test_live_support import load_sample


def _items(name: str):
    return load_sample(name)["response"]


# --- fixture ---------------------------------------------------------------------------------------
def test_normalize_fixture_maps_league_dates_and_teams():
    fields = normalize_fixture(_items("fixtures_by_date")[0])
    assert fields is not None
    assert fields["api_fixture_id"] == 1001
    assert fields["league_code"] == "I1"
    assert fields["competition"] == "Serie A"
    assert fields["season_label"] == "2026/2027"
    assert fields["kickoff_at"] == datetime(2026, 9, 21, 18, 45, tzinfo=timezone.utc)
    assert fields["match_date"] == date(2026, 9, 21)
    assert fields["status"] == "NS"
    assert fields["home_team"] == "AC Milan" and fields["away_team"] == "Inter"
    assert fields["home_team_api_id"] == 489 and fields["away_team_api_id"] == 505
    assert fields["referee"] == "D. Orsato" and fields["venue_city"] == "Milano"
    assert fields["ft_home"] is None and fields["ht_home"] is None


def test_normalize_fixture_finished_has_scores():
    fields = normalize_fixture(_items("fixtures_by_date")[2])
    assert fields["status"] == "FT"
    assert (fields["ft_home"], fields["ft_away"]) == (2, 1)
    assert (fields["ht_home"], fields["ht_away"]) == (1, 0)


def test_normalize_fixture_outside_16_leagues_is_none():
    assert normalize_fixture(_items("fixtures_by_date")[3]) is None


def test_match_date_is_rome_local_day():
    item = _items("fixtures_by_date")[0]
    item["fixture"]["date"] = "2026-09-21T22:30:00+00:00"  # 00:30 del 22 a Roma
    fields = normalize_fixture(item)
    assert fields["match_date"] == date(2026, 9, 22)
    assert fields["kickoff_at"].hour == 22


def test_season_helpers():
    assert season_label_from_api(2025) == "2025/2026"
    assert api_season_for(date(2026, 9, 20)) == 2026
    assert api_season_for(date(2026, 3, 1)) == 2025


def test_snapshot_kind_by_rome_hour():
    assert snapshot_kind_for(datetime(2026, 9, 20, 7, 0, tzinfo=timezone.utc)) == "mattina"  # 09:00 Roma
    assert snapshot_kind_for(datetime(2026, 9, 20, 9, 59, tzinfo=timezone.utc)) == "mattina"  # 11:59 Roma
    assert snapshot_kind_for(datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)) == "pomeriggio"  # 12:00 Roma
    assert snapshot_kind_for(datetime(2026, 9, 20, 14, 59, tzinfo=timezone.utc)) == "pomeriggio"  # 16:59 Roma
    assert snapshot_kind_for(datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)) == "sera"  # 17:00 Roma
    assert snapshot_kind_for(datetime(2026, 12, 20, 16, 30, tzinfo=timezone.utc)) == "sera"  # 17:30 Roma (ora solare)


# --- statistiche --------------------------------------------------------------------------------------
def test_normalize_statistics_maps_all_types():
    stats = normalize_statistics(_items("fixture_statistics"), 496, 492)
    assert stats is not None
    home, away = stats["home"], stats["away"]
    assert home == {
        "shots": 14, "sot": 6, "shots_inside": 9, "shots_outside": 5, "blocked": 4, "saves": 3, "corners": 7,
        "fouls": 12, "yellow": 2, "red": None, "possession": 55, "xg": 1.87, "offsides": 2,
    }
    assert away["red"] == 1 and away["possession"] == 45 and away["xg"] == 0.92 and away["sot"] == 4


def test_normalize_statistics_missing_team_is_none():
    assert normalize_statistics(_items("fixture_statistics")[:1], 496, 492) is None
    assert normalize_statistics([], 496, 492) is None


# --- eventi, formazioni, giocatori ------------------------------------------------------------------------
def test_normalize_events_sides_and_types():
    events = normalize_events(_items("fixture_events"), 496, 492)
    assert len(events) == 5
    assert events[0] == {
        "minute": 23, "extra": None, "type": "goal", "team": "home", "player": "D. Vlahovic", "player_id": 30410,
        "assist": "K. Yildiz", "assist_id": 1, "detail": "Normal Goal", "comments": None,
    }
    assert [e["type"] for e in events] == ["goal", "card", "subst", "card", "goal"]
    assert events[3]["team"] == "away" and events[3]["detail"] == "Red Card"
    assert events[4]["minute"] == 90 and events[4]["extra"] == 3


def test_normalize_lineups_official_when_both_start_xi():
    now = datetime(2026, 9, 21, 17, 50, tzinfo=timezone.utc)
    lineups, status = normalize_lineups(_items("fixture_lineups"), 489, 505, fetched_at=now)
    assert status == "ufficiali"
    assert lineups["home"]["formation"] == "3-5-2" and lineups["home"]["coach"] == "M. Allegri"
    assert len(lineups["home"]["starters"]) == 11 and len(lineups["away"]["starters"]) == 11
    assert lineups["home"]["starters"][0] == {"id": 301, "name": "M. Maignan", "pos": "G", "number": 16, "grid": "1:1"}
    assert len(lineups["home"]["bench"]) == 3
    assert lineups["fetched_at"] == now.isoformat()


def test_normalize_lineups_partial_is_not_official():
    items = _items("fixture_lineups")
    items[1]["startXI"] = []
    lineups, status = normalize_lineups(items, 489, 505, fetched_at=datetime.now(timezone.utc))
    assert status == "non_note" and lineups is not None
    assert normalize_lineups([], 489, 505, fetched_at=datetime.now(timezone.utc)) == (None, "non_note")


def test_normalize_players_minutes_started_rating():
    rows = normalize_players(_items("fixture_players"))
    assert len(rows) == 6
    by_id = {r["player_api_id"]: r for r in rows}
    assert by_id[101] == {"team_api_id": 496, "player_api_id": 101, "player_name": "M. Di Gregorio", "position": "G", "minutes": 90, "started": True, "rating": 7.1}
    assert by_id[103]["started"] is False and by_id[103]["minutes"] == 12
    assert by_id[104]["minutes"] == 0 and by_id[104]["rating"] is None
    assert by_id[202]["team_api_id"] == 492


# --- infortuni e classifica -----------------------------------------------------------------------------
def test_normalize_injuries_and_standings():
    inj = normalize_injuries(_items("injuries"))
    assert inj[0] == {"player_id": 30410, "player": "D. Vlahovic", "type": "Missing Fixture", "reason": "Knee Injury", "team_id": 496, "team": "Juventus", "fixture_id": 1010, "fixture_date": "2026-09-27T18:45:00+00:00"}
    table = normalize_standings(_items("standings"))
    assert [r["rank"] for r in table] == [1, 2, 3]
    assert table[0]["team"] == "Juventus" and table[0]["points"] == 9 and table[0]["gf"] == 8 and table[0]["ga"] == 2
    assert table[1]["form"] == "LWW" and table[1]["played"] == 3 and table[1]["goal_diff"] == 2


# --- quote -----------------------------------------------------------------------------------------------
def test_format_line_sign_convention():
    assert format_line(-0.5) == "-0.5"
    assert format_line(0.25) == "+0.25"
    assert format_line(0.0) == "0.0"
    assert format_line(-1.0) == "-1.0"
    assert format_line(1.75) == "+1.75"


def test_classify_bet_variants():
    assert classify_bet("Match Winner") == ("FT_1X2", {})
    assert classify_bet("Double Chance") == ("DOUBLE_CHANCE", {})
    assert classify_bet("Goals Over/Under") == ("FT_OVER_UNDER", {})
    assert classify_bet("First Half Winner") == ("HT_1X2", {})
    assert classify_bet("Half Time Result") == ("HT_1X2", {})
    assert classify_bet("Asian Handicap") == ("AH", {})
    assert classify_bet("Corners Over Under") == ("STAT", {"stat": "corners", "side": "total"})
    assert classify_bet("Total Corners") == ("STAT", {"stat": "corners", "side": "total"})
    assert classify_bet("Home Corners") == ("STAT", {"stat": "corners", "side": "home"})
    assert classify_bet("Corners Over Under - Away") == ("STAT", {"stat": "corners", "side": "away"})
    assert classify_bet("Cards Over/Under") == ("STAT", {"stat": "cards", "side": "total"})
    assert classify_bet("Away Cards") == ("STAT", {"stat": "cards", "side": "away"})
    assert classify_bet("Total Shots") == ("STAT", {"stat": "shots", "side": "total"})
    assert classify_bet("Home Total Shots") == ("STAT", {"stat": "shots", "side": "home"})
    assert classify_bet("Shots On Target") == ("STAT", {"stat": "sot", "side": "total"})
    assert classify_bet("Total Shots On Target") == ("STAT", {"stat": "sot", "side": "total"})
    assert classify_bet("Away Shots On Target") == ("STAT", {"stat": "sot", "side": "away"})
    assert classify_bet("Total ShotOnGoal") == ("STAT", {"stat": "sot", "side": "total"})
    assert classify_bet("Home Total ShotOnGoal") == ("STAT", {"stat": "sot", "side": "home"})
    assert classify_bet("Total Fouls") == ("STAT", {"stat": "fouls", "side": "total"})
    # fuori contratto
    assert classify_bet("Both Teams Score") is None
    assert classify_bet("HT/FT Double") is None
    assert classify_bet("Corners 1x2") is None
    assert classify_bet("Asian Handicap First Half") is None
    assert classify_bet("Goals Over/Under First Half") is None
    assert classify_bet("Player Shots On Target") is None
    assert classify_bet("Second Half Winner") is None


def test_normalize_bets_full_bet365_sample():
    bets = _items("odds_by_fixture")[0]["bookmakers"][0]["bets"]
    markets, unmapped = normalize_bets(bets)
    assert markets["HOME"] == 2.60 and markets["DRAW"] == 3.30 and markets["AWAY"] == 2.75
    assert markets["ONE_X"] == 1.45 and markets["ONE_TWO"] == 1.33 and markets["X_TWO"] == 1.50
    assert markets["OVER_2_5"] == 1.85 and markets["UNDER_2_5"] == 1.95
    assert markets["OVER_0_5"] == 1.03 and markets["UNDER_3_5"] == 1.35
    assert "OVER_4_5" not in markets  # oltre 3,5 non nel contratto
    assert markets["HOME_PT"] == 3.40 and markets["DRAW_PT"] == 2.10 and markets["AWAY_PT"] == 3.60
    # handicap asiatico: segno della squadra indicata, formato -0.5 / +0.25 / 0.0 / -1.0
    assert markets["AH_HOME:-0.5"] == 2.60
    assert markets["AH_AWAY:+0.5"] == 1.50
    assert markets["AH_HOME:+0.25"] == 1.80
    assert markets["AH_AWAY:-0.25"] == 2.05
    assert markets["AH_HOME:0.0"] == 2.00 and markets["AH_AWAY:0.0"] == 1.85
    assert markets["AH_HOME:-1.0"] == 4.20 and markets["AH_AWAY:+1.0"] == 1.22
    # statistiche
    assert markets["STAT:corners:total:over:9.5"] == 1.85 and markets["STAT:corners:total:under:10.5"] == 1.60
    assert not any(k.startswith("STAT:corners:total:over:10.0") for k in markets)  # linea intera scartata
    assert markets["STAT:corners:home:over:4.5"] == 1.70
    assert markets["STAT:corners:away:under:5.5"] == 1.65
    assert markets["STAT:cards:total:over:4.5"] == 1.80
    assert markets["STAT:cards:home:over:1.5"] == 1.60
    assert markets["STAT:cards:away:under:2.5"] == 1.75
    assert markets["STAT:sot:total:over:8.5"] == 1.90
    assert markets["STAT:sot:home:under:3.5"] == 2.15
    assert markets["STAT:sot:away:over:6.5"] == 1.85
    assert markets["STAT:shots:total:over:24.5"] == 1.95
    assert markets["STAT:shots:home:over:12.5"] == 1.90
    assert markets["STAT:fouls:total:over:24.5"] == 1.88
    assert set(unmapped) == {"Both Teams Score", "HT/FT Double", "Corners 1x2", "Player Shots On Target"}


def test_normalize_bets_split_asian_line_is_averaged():
    markets, _ = normalize_bets([{"name": "Asian Handicap", "values": [{"value": "Home -0.5, -1", "odd": "3.00"}, {"value": "Away +0.5/+1", "odd": "1.40"}]}])
    assert markets == {"AH_HOME:-0.75": 3.0, "AH_AWAY:+0.75": 1.4}


def test_normalize_odds_item_filters_bookmakers():
    item = _items("odds_by_fixture")[0]
    out = normalize_odds_item(item, bookmaker_ids={8, 3})
    assert set(out) == {8, 3}
    assert out[3].bookmaker_name == "Betfair"
    assert out[3].markets["AH_HOME:-0.75"] == 3.10 and out[3].markets["AH_AWAY:+0.75"] == 1.36
    assert out[3].unmapped_bets == []
    everything = normalize_odds_item(item)
    assert 11 in everything


def test_market_family():
    assert market_family("HOME") == "FT_1X2"
    assert market_family("ONE_X") == "DOUBLE_CHANCE"
    assert market_family("UNDER_2_5") == "FT_OVER_UNDER"
    assert market_family("DRAW_PT") == "HT_1X2"
    assert market_family("AH_AWAY:+0.5") == "AH"
    assert market_family("STAT:sot:away:over:6.5") == "STAT:sot"
    assert market_family("BTTS") is None
