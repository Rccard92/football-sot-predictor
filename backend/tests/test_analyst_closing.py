"""Quota di chiusura e CLV del Diario analisi (documento "Modifiche" di Giovanni, 09/11/2026)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.analyst.closing import (
    CLOSING_ND,
    CLOSING_OK,
    NOTE_RECOVERED,
    apply_closing,
    book_quotes,
    clv_value,
    pick_closing,
    refresh_clv,
    run_closing,
)

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)


def bets(home=None, draw=None, away=None, under25=None, over25=None):
    out = []
    if home or draw or away:
        out.append(
            {
                "id": 1,
                "name": "Match Winner",
                "values": [v for v in ({"value": "Home", "odd": home}, {"value": "Draw", "odd": draw}, {"value": "Away", "odd": away}) if v["odd"]],
            }
        )
    if under25 or over25:
        out.append(
            {
                "id": 5,
                "name": "Goals Over/Under",
                "values": [v for v in ({"value": "Over 2.5", "odd": over25}, {"value": "Under 2.5", "odd": under25}) if v["odd"]],
            }
        )
    return out


def response(*books):
    return [{"fixture": {"id": 1}, "bookmakers": [{"id": bid, "name": name, "bets": b} for bid, name, b in books]}]


def entry(**kw):
    base = dict(
        market_key="HOME",
        quota=2.20,
        kickoff=NOW + timedelta(minutes=50),
        provider_fixture_id=111,
        closing_quota=None,
        closing_bookmaker=None,
        closing_at=None,
        closing_status=None,
        closing_note=None,
        clv=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_clv_is_taken_over_closing_minus_one():
    assert clv_value(2.20, 2.00) == 0.1
    assert clv_value(1.80, 2.00) == -0.1
    assert clv_value(2.0, None) is None
    assert clv_value(2.0, 1.0) is None


def test_bet365_first_then_pinnacle_then_betfair():
    items = response((8, "Bet365", bets("2.00", "3.40", "3.60")), (4, "Pinnacle", bets("2.05", "3.50", "3.70", "1.90", "1.95")))
    assert book_quotes(items, 8, "Bet365", "bet365")["HOME"] == 2.0
    assert pick_closing(items, "HOME") == (2.0, "Bet365")
    # Bet365 non ha l'Under 2,5: si prende Pinnacle e si dice quale
    assert pick_closing(items, "UNDER_2_5") == (1.9, "Pinnacle")
    only_betfair = response((3, "Betfair", bets("2.10", "3.30", "3.50")))
    assert pick_closing(only_betfair, "AWAY") == (3.5, "Betfair")
    assert pick_closing(only_betfair, "UNDER_2_5") == (None, None)


def test_double_chance_derived_from_1x2_is_not_a_closing_price():
    items = response((8, "Bet365", bets("2.00", "3.40", "3.60")))
    assert "ONE_X" not in book_quotes(items, 8, "Bet365", "bet365")
    assert pick_closing(items, "ONE_X") == (None, None)


def test_apply_closing_sets_book_status_and_clv():
    e = entry()
    apply_closing(e, response((8, "Bet365", bets("2.00", "3.40", "3.60"))), NOW)
    assert (e.closing_quota, e.closing_bookmaker, e.closing_status, e.clv) == (2.0, "Bet365", CLOSING_OK, 0.1)
    assert e.closing_note is None
    nd = entry(market_key="UNDER_2_5")
    apply_closing(nd, response((8, "Bet365", bets("2.00", "3.40", "3.60"))), NOW)
    assert nd.closing_status == CLOSING_ND and nd.clv is None and "Bet365, Pinnacle o Betfair" in nd.closing_note


def test_changing_the_taken_odds_recomputes_clv():
    e = entry(quota=2.20, closing_quota=2.0, closing_status=CLOSING_OK, clv=0.1)
    e.quota = 1.90
    refresh_clv(e)
    assert e.clv == -0.05


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: self.rows)

    def commit(self):
        self.commits += 1


class FakeClient:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def get_fixture_odds_by_fixture(self, fixture_id):
        self.calls.append(fixture_id)
        return self.items


def test_one_call_per_match_old_matches_nd_and_past_ones_recovered():
    a = entry(market_key="HOME")
    b = entry(market_key="AWAY")  # stessa partita: una sola chiamata
    past = entry(provider_fixture_id=222, kickoff=NOW - timedelta(days=1))
    old = entry(provider_fixture_id=333, kickoff=NOW - timedelta(days=10))
    no_provider = entry(provider_fixture_id=None)
    client = FakeClient(response((8, "Bet365", bets("2.00", "3.40", "3.60"))))
    db = FakeDb([a, b, past, old, no_provider])
    out = run_closing(db, client, NOW)
    assert sorted(client.calls) == [111, 222]
    assert a.closing_status == b.closing_status == CLOSING_OK and b.closing_quota == 3.6
    assert past.closing_status == CLOSING_OK and past.closing_note == NOTE_RECOVERED
    assert old.closing_status == CLOSING_ND and no_provider.closing_status == CLOSING_ND
    assert out["calls"] == 2 and out["recovered"] == 1 and db.commits == 1


def test_provider_error_retries_before_kickoff_but_not_after():
    class Broken(FakeClient):
        def get_fixture_odds_by_fixture(self, fixture_id):
            raise RuntimeError("timeout")

    soon = entry()
    past = entry(provider_fixture_id=222, kickoff=NOW - timedelta(hours=2))
    run_closing(FakeDb([soon, past]), Broken(None), NOW)
    assert soon.closing_status is None  # si riprova al giro dopo
    assert past.closing_status == CLOSING_ND
