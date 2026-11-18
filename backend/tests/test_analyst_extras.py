"""Migliorie del Diario del 18/11/2026: seconda lettura quote, calendario con le coppe, formazioni."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.analyst.calendar import _item_row, team_schedule
from app.services.analyst.lineups import habitual_xi, parse_fixture_item, roles_text, squad_status
from app.services.analyst.odds_reads import movement

T0 = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


def test_movement_towards_the_cecchino():
    morning = {"HOME": 2.10, "DRAW": 3.40, "AWAY": 3.60, "UNDER_2_5": 1.80, "OVER_2_5": 1.95}
    later = {"HOME": 1.90, "DRAW": 3.50, "AWAY": 4.00, "UNDER_2_5": 1.95, "OVER_2_5": 1.80}
    cecchino = {"HOME": 1.92, "UNDER_2_5": 1.70}
    rows = {r["key"]: r for r in movement(morning, later, cecchino)}
    home = rows["HOME"]
    # la vittoria in casa sale e il Cecchino la dava piu' probabile del mattino: verso il Cecchino, CLV positivo
    assert home["move_points"] > 0 and home["toward_cecchino"] is True and home["clv_morning"] > 0
    under = rows["UNDER_2_5"]
    # l'Under scende ma il Cecchino lo dava sopra il mattino: contro il Cecchino
    assert under["move_points"] < 0 and under["toward_cecchino"] is False and under["clv_morning"] < 0
    assert rows["DRAW"]["cecchino_prob"] is None and rows["DRAW"]["toward_cecchino"] is None
    assert "OVER_1_5" not in rows  # quota mancante: non si calcola


def _lineup_item(fid, home_id, away_id, home_xi, yellow_home=2):
    def xi(ids):
        return [{"player": {"id": i, "name": f"P{i}", "pos": "G" if i % 100 == 1 else "D" if i % 100 < 6 else "M"}} for i in ids]

    return {
        "fixture": {"id": fid, "status": {"short": "FT"}},
        "teams": {"home": {"id": home_id}, "away": {"id": away_id}},
        "lineups": [{"team": {"id": home_id}, "formation": "4-4-2", "startXI": xi(home_xi)}],
        "events": [{"type": "Card", "detail": "Yellow Card", "team": {"id": home_id}}] * yellow_home,
    }


def test_parse_fixture_item_lineups_and_yellows():
    rows = parse_fixture_item(_lineup_item(5, 10, 20, range(101, 112)))
    home, away = rows
    assert home["status"] == "ok" and len(home["starters_json"]) == 11 and home["yellow_cards"] == 2 and home["formation"] == "4-4-2"
    assert away["status"] == "nd" and away["starters_json"] is None and away["yellow_cards"] == 0


def test_habitual_starters_over_ten_games_and_squad_status():
    base = list(range(101, 112))
    games = [{"starters": [{"id": i, "name": f"P{i}", "pos": "G" if i == 101 else "D" if i < 106 else "M"} for i in base]} for _ in range(8)]
    # nelle ultime 2 gare mancano il portiere e due difensori (sostituiti da 201-203)
    rotated = [201, 202, 203] + base[3:]
    games += [{"starters": [{"id": i, "name": f"P{i}", "pos": "G" if i in (101, 201) else "D"} for i in rotated]} for _ in range(2)]
    hab = habitual_xi(games)
    assert {p["id"] for p in hab} == set(base) and hab[0]["of"] == 10
    st = squad_status(games[-1]["starters"], hab)
    assert st["missing"] == 3 and st["text"] == "−3 titolari (portiere, 2 difensori)"
    assert squad_status(games[0]["starters"], hab) == {"complete": True, "missing": 0, "text": "completa"}
    assert habitual_xi(games[:4]) is None  # meno di 5 formazioni
    assert roles_text([{"pos": "F"}, {"pos": None}]) == "attaccante, 1 n.d."


def _game(fid, days, home, away, league=1, name="Serie A", status="FT"):
    return SimpleNamespace(
        provider_fixture_id=fid, kickoff=T0 + timedelta(days=days), status=status, provider_league_id=league, league_name=name,
        home_provider_team_id=home, away_provider_team_id=away, home_team_name=f"T{home}", away_team_name=f"T{away}",
    )


def test_last_and_next_game_with_cups():
    games = [
        _game(1, -10, 7, 8),
        _game(2, -4, 9, 7, league=99, name="Coppa"),
        _game(3, -2, 7, 5, status="PST"),  # rinviata: non conta
        _game(4, 0, 7, 6),  # la partita stessa
        _game(5, 3, 4, 7, league=99, name="Coppa"),
    ]
    s = team_schedule(games, 7, cutoff=T0, provider_fixture_id=4, league_id=1)
    assert s["last"]["competition"] == "Coppa" and s["last"]["league_match"] is False and s["last"]["days"] == 4
    assert s["next"]["date"] == (T0 + timedelta(days=3)).date().isoformat() and s["next"]["home"] is False
    assert s["games_7"] == 1 and s["games_14"] == 2
    assert team_schedule([], 7, cutoff=T0, provider_fixture_id=4, league_id=1) is None


def test_calendar_item_row():
    item = {
        "fixture": {"id": 77, "date": "2026-11-20T19:45:00+00:00", "status": {"short": "NS"}},
        "league": {"id": 45, "name": "FA Cup", "country": "England", "round": "1st Round"},
        "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
    }
    row = _item_row(item, date(2026, 11, 20))
    assert row["provider_fixture_id"] == 77 and row["league_name"] == "FA Cup" and row["home_provider_team_id"] == 1
    assert row["kickoff"] == datetime(2026, 11, 20, 19, 45, tzinfo=timezone.utc)
    assert _item_row({"fixture": {}}, date(2026, 11, 20)) is None
