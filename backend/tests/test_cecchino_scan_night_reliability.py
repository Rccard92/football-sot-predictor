"""Scansione notturna: 429 mai trattati come quote assenti, elenco quote del giorno, slot mattino."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.jobs.cecchino_auto_scan import SLOT_MORNING, SLOT_PRIMARY, resolve_auto_scan_slot
from app.services import api_football_client as afc
from app.services.api_football_client import ApiFootballClient, ApiFootballError, ApiFootballRateLimited
from app.services.cecchino.cecchino_today_odds_fetch import (
    STRATEGY_DAY_LISTING,
    STRATEGY_ODDS_FETCH_ERROR,
    _BET365_ID,
    _BETFAIR_ID,
    fetch_fixture_odds_for_cecchino_1x2_gate,
    prefetch_day_primary_odds,
)

ROME = "Europe/Rome"


def _resp(status: int, body: dict | None = None, headers: dict | None = None) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.headers = httpx.Headers({"content-type": "application/json", **(headers or {})})
    r.json.return_value = body or {"errors": {}, "response": []}
    if status >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(str(status), request=MagicMock(), response=r)
    else:
        r.raise_for_status = MagicMock()
    return r


@pytest.fixture(autouse=True)
def _reset_rate_state():
    afc._rate_state["remaining"] = None
    afc._rate_state["observed_at"] = 0.0
    yield
    afc._rate_state["remaining"] = None


def test_429_waits_beyond_transient_retries_then_succeeds():
    client = ApiFootballClient(api_key="k")
    seq = [_resp(429)] * 4 + [_resp(200, {"errors": {}, "response": [{"ok": 1}]})]
    sleeps: list[float] = []
    with patch("app.services.api_football_client.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.side_effect = seq
        with patch("app.services.api_football_client.time.sleep", side_effect=sleeps.append):
            data = client.get("odds", {"fixture": 1})
    assert data["response"] == [{"ok": 1}]
    assert sleeps[:4] == [5.0, 10.0, 15.0, 20.0]


def test_429_persisting_raises_rate_limited_not_empty_data():
    client = ApiFootballClient(api_key="k")
    with patch("app.services.api_football_client.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.side_effect = [_resp(429)] * 20
        with patch("app.services.api_football_client.time.sleep"):
            with pytest.raises(ApiFootballRateLimited):
                client.get("odds", {"fixture": 1})


def test_low_minute_remaining_paces_next_request():
    client = ApiFootballClient(api_key="k")
    low = _resp(200, {"errors": {}, "response": []}, {"x-ratelimit-remaining": "3"})
    ok = _resp(200, {"errors": {}, "response": []}, {"x-ratelimit-remaining": "250"})
    sleeps: list[float] = []
    with patch("app.services.api_football_client.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.side_effect = [low, ok]
        with patch("app.services.api_football_client.time.sleep", side_effect=sleeps.append):
            client.get("odds", {"fixture": 1})
            client.get("odds", {"fixture": 2})
    assert sleeps == [afc.RATE_LIMIT_LOW_SLEEP_S]


def _settings(monkeypatch, *, requires_primary: bool) -> None:
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    settings.cecchino_gate_requires_primary_1x2 = requires_primary
    monkeypatch.setattr("app.services.cecchino.cecchino_today_odds_fetch.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.cecchino.cecchino_today_odds_fetch.time.sleep", lambda *_a, **_k: None)


def _primary_raw(winner: dict[str, str]) -> list[dict]:
    return [{
        "update": "2026-09-14T20:00:00+00:00",
        "bookmakers": [{
            "id": _BETFAIR_ID,
            "name": "Bet365",
            "bets": [{"id": 1, "name": "Match Winner", "values": [{"value": k, "odd": v} for k, v in winner.items()]}],
        }],
    }]


def test_gate_uses_day_listing_without_calls(monkeypatch):
    _settings(monkeypatch, requires_primary=True)
    client = MagicMock()
    listing = {501: _primary_raw({"Home": "2.0", "Draw": "3.3", "Away": "3.6"})}
    odds, _, strategy, neg = fetch_fixture_odds_for_cecchino_1x2_gate(client, 501, force_rescan=True, day_odds=listing)
    assert strategy == STRATEGY_DAY_LISTING and neg is False
    client.get_fixture_odds.assert_not_called()
    assert _BETFAIR_ID in odds


def test_gate_not_in_listing_falls_back_to_single_call(monkeypatch):
    _settings(monkeypatch, requires_primary=True)
    client = MagicMock()
    client.get_fixture_odds.return_value = _primary_raw({"Home": "2.0", "Draw": "3.3", "Away": "3.6"})
    _, _, strategy, _ = fetch_fixture_odds_for_cecchino_1x2_gate(client, 502, force_rescan=True, day_odds={})
    assert strategy == "betfair_1x2"
    client.get_fixture_odds.assert_called_once_with(502, _BETFAIR_ID)


def test_gate_api_error_is_fetch_error_not_missing(monkeypatch):
    _settings(monkeypatch, requires_primary=True)
    client = MagicMock()
    client.get_fixture_odds.side_effect = ApiFootballRateLimited("HTTP 429")
    odds, warnings, strategy, neg = fetch_fixture_odds_for_cecchino_1x2_gate(client, 503, force_rescan=True)
    assert strategy == STRATEGY_ODDS_FETCH_ERROR
    assert neg is False
    assert warnings and warnings[0].startswith("odds_fetch_error:")
    assert client.get_fixture_odds.call_count == 1


def test_gate_requires_primary_skips_fallback_call(monkeypatch):
    _settings(monkeypatch, requires_primary=True)
    client = MagicMock()
    client.get_fixture_odds.return_value = []
    _, _, strategy, _ = fetch_fixture_odds_for_cecchino_1x2_gate(client, 504, force_rescan=True)
    assert strategy == "betfair_1x2"
    client.get_fixture_odds.assert_called_once_with(504, _BETFAIR_ID)
    assert all(c.args[1] != _BET365_ID for c in client.get_fixture_odds.call_args_list)


def test_prefetch_day_odds_reads_all_pages_and_keeps_primary_only():
    client = MagicMock()
    pages = {
        1: {"paging": {"current": 1, "total": 2}, "response": [
            {"fixture": {"id": 1}, "update": "u", "bookmakers": [{"id": _BETFAIR_ID, "bets": []}, {"id": 99, "bets": []}]},
        ]},
        2: {"paging": {"current": 2, "total": 2}, "response": [
            {"fixture": {"id": 2}, "update": "u", "bookmakers": [{"id": _BETFAIR_ID, "bets": []}]},
            {"fixture": {"id": 3}, "update": "u", "bookmakers": [{"id": 99, "bets": []}]},
        ]},
    }
    client.get.side_effect = lambda ep, params: pages[params["page"]]
    by_fixture, info = prefetch_day_primary_odds(client, scan_date=date(2026, 9, 15), timezone_name=ROME)
    assert set(by_fixture) == {1, 2}
    assert [b["id"] for b in by_fixture[1][0]["bookmakers"]] == [_BETFAIR_ID]
    assert info["complete"] is True and info["pages"] == 2


def test_prefetch_day_odds_partial_on_error():
    client = MagicMock()
    client.get.side_effect = [
        {"paging": {"current": 1, "total": 3}, "response": [
            {"fixture": {"id": 7}, "bookmakers": [{"id": _BETFAIR_ID, "bets": []}]},
        ]},
        ApiFootballError("HTTP 500"),
    ]
    by_fixture, info = prefetch_day_primary_odds(client, scan_date=date(2026, 9, 15), timezone_name=ROME)
    assert set(by_fixture) == {7}
    assert info["complete"] is False and info["error"]


def _slot(hh: int, mm: int, morning: bool = True) -> str | None:
    now = datetime(2026, 9, 15, hh, mm, tzinfo=ZoneInfo(ROME))
    return resolve_auto_scan_slot(
        now,
        timezone_name=ROME,
        primary_hour=23,
        primary_minute=0,
        recovery_hour=23,
        recovery_minute=50,
        window_minutes=10,
        morning_hour=7 if morning else None,
        morning_minute=30 if morning else None,
    )


def test_morning_slot_window():
    assert _slot(7, 30) == SLOT_MORNING
    assert _slot(7, 30, morning=False) is None
    assert _slot(23, 0) == SLOT_PRIMARY
    assert _slot(12, 0) is None
