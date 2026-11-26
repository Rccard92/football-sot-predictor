"""Capitolato di Giovanni del 24/11/2026: stati dei segni, R1/R2, motivazione, meteo, zone, foto."""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.services.analyst.motivation import (
    STATUS_DECIDED,
    STATUS_GOAL,
    STATUS_NONE,
    STATUS_SAFETY,
    close_games,
    end_of_season,
    fasce,
    motivation_alerts,
    team_status,
)
from app.services.analyst.rules import DEFAULT_RULES, clean_rules, rules_version
from app.services.analyst.signs import (
    STATE_BLOCKED,
    STATE_CHECK,
    STATE_OUT,
    STATE_PLAYABLE,
    evaluate_row,
    half_up,
    sign_state,
    used_quotes,
)
from app.services.analyst.weather import clean_city, parse_forecast, pick_place, weather_view
from app.services.analyst.zones import parse_standings

RULES = {**DEFAULT_RULES}


def _home(points: int = 7, hts: tuple[str, ...] = ("0-1", "0-1", "1-0", "0-0", "1-0")) -> dict:
    return {"enough": True, "points": points, "max_points": 15, "results": [{"ht": h} for h in hts]}


# --- modifiche 1-3: Juve Stabia - Catanzaro (24/11/2026, quote delle 06:03) -------------------------


def test_juve_stabia_catanzaro_four_signs():
    x = sign_state(RULES, "DRAW", 3.50, 3.75, "Scala 1X", _home())
    assert x["state"] == STATE_PLAYABLE and round(x["value"] * 100) == -7
    xpt = sign_state(RULES, "DRAW_PT", 2.30, 2.09, "Scala 1X", _home())
    assert xpt["state"] == STATE_PLAYABLE and round(xpt["value"] * 100) == 10
    over = sign_state(RULES, "OVER_2_5", 1.75, 2.26, "Scala 1X", _home())
    assert over["state"] == STATE_BLOCKED
    assert over["reasons"][0]["text"] == "R1 · book 23% sotto il Cecchino"
    over_pt = sign_state(RULES, "OVER_PT_0_5", 1.30, 1.56, "Scala 1X", _home())
    assert over_pt["state"] == STATE_BLOCKED
    assert over_pt["reasons"][0]["text"] == "R1 · book 17% sotto il Cecchino"


def test_out_of_range_and_avoid_come_first():
    assert sign_state(RULES, "DRAW", 4.20, 3.0, None, None)["state"] == STATE_OUT  # oltre 3,80
    assert sign_state(RULES, "OVER_3_5", 3.0, 3.0, None, None)["state"] == STATE_OUT  # da evitare


def test_anomaly_over_30_percent_is_to_check():
    s = sign_state(RULES, "DRAW", 3.60, 2.70, None, _home())  # valore +33%
    assert s["state"] == STATE_CHECK
    assert "anomalia >30%" in s["reasons"][0]["text"]


def test_squilibrio_no_under_is_a_block_with_the_site_text():
    s = sign_state(RULES, "UNDER_3_5", 1.90, 1.50, "Squilibrio", _home())
    assert s["state"] == STATE_BLOCKED and s["reasons"][0]["text"] == "squilibrio: niente Under"


def test_r2_home_is_only_a_note_by_default_and_blocks_when_switched_on():
    s = sign_state(RULES, "ONE_X", 1.40, 1.45, None, _home(points=3))
    assert s["state"] == STATE_PLAYABLE
    assert s["notes"][0]["text"] == "R2 · casa 3 punti su 15 in casa"
    on = sign_state({**RULES, "r2_home_block": True}, "ONE_X", 1.40, 1.45, None, _home(points=3))
    assert on["state"] == STATE_BLOCKED and on["reasons"][0]["code"] == "r2_casa"


def test_r2_over_pt_with_three_zero_zero_at_half_time():
    s = sign_state(RULES, "OVER_PT_0_5", 1.40, 1.45, None, _home(hts=("0-0", "0-0", "1-0", "0-0", "2-1")))
    assert s["state"] == STATE_BLOCKED
    assert s["reasons"][0]["text"] == "R2 · casa 3 volte 0-0 al PT su 5"


def test_half_up_rounding():
    assert half_up(12.5) == 13 and half_up(12.49) == 12


def test_second_read_replaces_the_morning_quote():
    quotes = [{"key": "UNDER_3_5", "label": "Under 3.5", "quota": 1.40}, {"key": "DRAW", "label": "X", "quota": 3.5}]
    move = {"status": "ok", "read_at": "2026-11-23T18:15:00+00:00", "markets": [{"key": "UNDER_3_5", "later_quota": 1.30}]}
    used = used_quotes(quotes, move, "2026-11-23T05:00:00+00:00")
    assert used["UNDER_3_5"]["q"] == 1.30 and used["UNDER_3_5"]["source"] == "t75"
    assert round(used["UNDER_3_5"]["change"] * 100, 1) == -7.1
    assert used["DRAW"]["q"] == 3.5 and used["DRAW"]["source"] == "morning"
    # 1,40 si compra, 1,30 e' fuori fascia (minimo 1,35 in questa prova) solo sull'ultima lettura
    row = {
        "quotes": [{**q, "group": "", "quota_cecchino": None} for q in quotes],
        "odds_move": move,
        "odds_checked_at": "2026-11-23T05:00:00+00:00",
        "kickoff": "2026-11-23T19:30:00+00:00",
        "blocks": {},
    }
    ev = evaluate_row({**RULES, "markets": {"UNDER_3_5": {"min": 1.35}}}, row)
    under = next(s for s in ev["signs"] if s["key"] == "UNDER_3_5")
    assert under["state"] == STATE_OUT and under["q"] == 1.30
    assert ev["second_read"]["done"] is True


def test_counts_and_second_read_due_time():
    row = {
        "quotes": [
            {"key": "DRAW", "label": "X", "group": "", "quota": 3.50, "quota_cecchino": 3.75},
            {"key": "OVER_2_5", "label": "Over 2.5", "group": "", "quota": 1.75, "quota_cecchino": 2.26},
        ],
        "odds_move": None,
        "odds_checked_at": "2026-11-24T05:03:00+00:00",
        "kickoff": "2026-11-24T18:00:00+00:00",
        "match_type": "Scala 1X",
        "blocks": {"forma_casa": _home()},
    }
    ev = evaluate_row(RULES, row)
    assert ev["counts"]["playable"] == 1 and ev["counts"]["blocked"] == 1
    assert ev["second_read"]["due"].startswith("2026-11-24T16:45")


def test_rules_version_and_admin_fields():
    assert rules_version(RULES) == "R1 10% + R2 PT · 26 nov 2026"
    clean = clean_rules({"r1_pct": 12, "r2_home_block": True, "markets": {}}, set())
    assert clean["r1_pct"] == 12 and clean["r2_home_block"] is True and clean["r2_pt_block"] is True


# --- modifica 17: motivazione -----------------------------------------------------------------------


def _table(points: list[int], wins: list[int] | None = None) -> list[dict]:
    wins = wins or [p // 3 for p in points]
    return [{"rank": i + 1, "team_id": i + 1, "points": p, "won": w} for i, (p, w) in enumerate(zip(points, wins))]


ZONES20 = {"1": "Champions League", "2": "Champions League", "3": "Champions League", "4": "Champions League", "17": None, "18": "Relegation", "19": "Relegation", "20": "Relegation"}


def test_fasce_need_descriptions():
    assert fasce({}, 20) is None
    z = fasce(ZONES20, 20)
    assert z[0] == "titolo" and z[1] == "obiettivo" and z[9] == "centro" and z[19] == "pericolo"


def test_team_status_two_rounds_from_the_end():
    pts = [85, 75, 60, 58, 54, 48, 46, 45, 44, 43, 42, 41, 40, 39, 38, 37, 36, 30, 20, 15]
    table = _table(pts)
    left = {i + 1: 2 for i in range(20)}
    zones = fasce(ZONES20, 20)
    champion = team_status(1, table, left, zones, descriptions=ZONES20)
    assert champion["status"] == STATUS_DECIDED and "campione" in champion["text"]
    second = team_status(2, table, left, zones, descriptions=ZONES20)
    assert second["status"] == STATUS_DECIDED and "(2ª)" in second["text"]
    last = team_status(20, table, left, zones, descriptions=ZONES20)
    assert last["status"] == STATUS_DECIDED and "retrocessa" in last["text"]
    fourth = team_status(4, table, left, zones, descriptions=ZONES20)
    assert fourth["status"] == STATUS_GOAL
    seventeenth = team_status(17, table, left, zones, descriptions=ZONES20)
    assert seventeenth["status"] == STATUS_SAFETY
    # a due giornate dalla fine il centro classifica e' una posizione decisa (fascia centro)
    middle = team_status(10, table, left, zones, descriptions=ZONES20)
    assert middle["status"] == STATUS_DECIDED and "centro classifica" in middle["text"]


def test_brazil_tie_on_points_is_decided_by_wins():
    pts = [70, 64, 50]
    table = _table(pts, wins=[22, 18, 14])
    left = {1: 2, 2: 2, 3: 2}
    zones = ["titolo", "obiettivo", "centro"]
    # la seconda puo' arrivare a 70 punti ma con al massimo 20 vittorie: la prima ne ha gia' 22
    assert team_status(2, table, left, zones, descriptions={}, wins_tiebreak=True)["text"].startswith("posizione decisa")
    assert team_status(2, table, left, zones, descriptions={}, wins_tiebreak=False)["status"] == STATUS_GOAL


def test_close_games_and_turnover_alerts():
    schedule = {
        "home": {"last": {"days": 2, "league_match": True}, "next": {"days": 5, "league_match": True}, "games_7": 2},
        "away": {"last": {"days": 4, "league_match": True}, "next": {"days": 4, "league_match": False, "competition": "CONMEBOL Libertadores"}, "games_7": 2},
    }
    a = close_games("Chapecoense", "Palmeiras", schedule)
    assert a["code"] == "ravvicinata"
    assert "Chapecoense ha giocato 2 giorni fa (campionato)" in a["text"] and "Palmeiras ha 2 gare in 7 giorni" in a["text"]
    alerts = motivation_alerts(
        home="Chapecoense",
        away="Palmeiras",
        home_status={"status": STATUS_DECIDED},
        away_status={"status": STATUS_DECIDED},
        remaining=None,
        favorite="away",
        schedule=schedule,
    )
    codes = [x["code"] for x in alerts]
    assert codes == ["senza_motivazioni", "turnover"]
    assert alerts[1]["text"] == "⚠ possibile turnover: Palmeiras gioca CONMEBOL Libertadores tra 4 giorni"
    assert close_games("A", "B", {"home": {"last": {"days": 3}, "next": {"days": 4}, "games_7": 1}, "away": None}) is None


def test_p27_and_hypothesis_two():
    p27 = motivation_alerts(home="A", away="B", home_status={"status": STATUS_DECIDED}, away_status={"status": STATUS_GOAL}, remaining=None, favorite="home", schedule=None)
    assert p27[0]["code"] == "p27"
    h2 = motivation_alerts(home="A", away="B", home_status={"status": STATUS_NONE}, away_status={"status": STATUS_SAFETY}, remaining=None, favorite="home", schedule=None)
    assert [x["code"] for x in h2] == ["ipotesi_2"]


def test_end_of_season_only_in_the_last_eight_rounds_and_nd_without_zones():
    remaining = {"home": {"games": 26, "exact": False}, "away": {"games": 26, "exact": False}}
    assert end_of_season(home_id=1, away_id=2, home="A", away="B", remaining=remaining, table=_table([10, 9]), left={1: 26, 2: 26}, zones_row=None, country=None, favorite=None, schedule=None) is None
    near = {"home": {"games": 6, "exact": False}, "away": {"games": 6, "exact": False}}
    out = end_of_season(home_id=1, away_id=2, home="A", away="B", remaining=near, table=_table([10, 9]), left={1: 6, 2: 6}, zones_row=None, country=None, favorite=None, schedule=None)
    assert out["label"] == "⚑ ultime circa 6 giornate" and out["text"] == "motivazione n.d."


def test_parse_standings_single_and_groups():
    one = [{"league": {"standings": [[{"rank": 1, "description": "Promotion - Serie A"}, {"rank": 2, "description": None}]]}}]
    assert parse_standings(one) == ("ok", 2, {"1": "Promotion - Serie A", "2": None})
    two = [{"league": {"standings": [[{"rank": 1}], [{"rank": 1}]]}}]
    assert parse_standings(two)[0] == "groups"
    assert parse_standings([])[0] == "nd"


# --- modifiche 5 e 13: meteo ------------------------------------------------------------------------


def test_weather_city_country_and_forecast():
    assert clean_city("Napoli (NA)") == "Napoli" and clean_city("Castellammare di Stabia, Campania") == "Castellammare di Stabia"
    results = [{"name": "Boston", "country": "United States", "latitude": 42.3, "longitude": -71.0}, {"name": "Boston", "country": "United Kingdom", "latitude": 52.9, "longitude": -0.02}]
    assert pick_place(results, "England")["latitude"] == 52.9
    assert pick_place(results, "Italy") is None
    body = {"hourly": {"time": ["2026-11-24T16:00", "2026-11-24T17:00", "2026-11-24T18:00", "2026-11-24T19:00", "2026-11-24T20:00"], "temperature_2m": [15, 14.5, 14, 13, 12], "precipitation": [0, 0, 0, 0.2, 0], "wind_speed_10m": [10, 12, 12, 9, 8], "weather_code": [3, 3, 3, 61, 3]}}
    hourly = parse_forecast(body)
    w = SimpleNamespace(status="ok", hourly_json=hourly, fetched_at=datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc))
    view = weather_view(w, datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc))
    assert view["kickoff"]["temperature"] == 14 and view["kickoff"]["icon"] == "☁"
    assert len(view["hours"]) == 5
    assert weather_view(SimpleNamespace(status="nd", hourly_json=None, fetched_at=None), None)["status"] == "nd"


# --- modifica 18: foto ------------------------------------------------------------------------------


def test_photo_is_resized_and_loses_exif():
    from PIL import Image

    from app.services.analyst.photos import TOO_BIG, PhotoError, process_photo

    img = Image.new("RGB", (3200, 1600), (200, 10, 10))
    exif = Image.Exif()
    exif[0x010F] = "Telefono di prova"  # Make
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    data, width, height = process_photo(buf.getvalue())
    assert (width, height) == (1600, 800)
    assert not Image.open(io.BytesIO(data)).getexif()
    try:
        process_photo(b"x" * (5 * 1024 * 1024 + 1))
    except PhotoError as exc:
        assert str(exc) == TOO_BIG
    else:  # pragma: no cover
        raise AssertionError("una foto oltre 5 MB va rifiutata")


def test_quota_gap_over_three_percent():
    from app.routes.analyst_journal import quota_gap

    assert quota_gap(1.80, 1.80) is None
    assert quota_gap(1.85, 1.80) is None  # +2,8%: nessun avviso
    gap = quota_gap(1.90, 1.80)
    assert gap["text"] == "La quota presa è diversa da quella del tool di 6%: controlla"