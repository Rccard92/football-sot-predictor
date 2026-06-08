"""Test refresh quote Betfair singola fixture Cecchino Today (Fase 23)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER
from app.services.cecchino.cecchino_today_betfair_refresh import (
    build_betfair_markets_json,
    refresh_betfair_odds_by_id,
    refresh_betfair_odds_for_fixture,
)
from app.services.cecchino.cecchino_today_odds_meta import attach_scan_odds_meta

_BETFAIR_ID = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])


def _bet(name: str, bet_id: int, values: list[tuple[str, str]]) -> dict:
    return {
        "id": bet_id,
        "name": name,
        "values": [{"value": v, "odd": o} for v, o in values],
    }


def _raw_payload(*bets: dict, extra_bets: list[dict] | None = None) -> list[dict]:
    all_bets = list(bets)
    if extra_bets:
        all_bets.extend(extra_bets)
    return [{"bookmakers": [{"id": _BETFAIR_ID, "name": "Betfair", "bets": all_bets}]}]


def _snapshot_from_raw(raw: list[dict], *, home: float, draw: float, away: float) -> dict:
    snap = {
        "bookmakers": {"Betfair": {"HOME": home, "DRAW": draw, "AWAY": away}},
        "raw_by_bookmaker_id": {str(_BETFAIR_ID): raw},
    }
    return attach_scan_odds_meta(snap, from_cache=True)


def _eligible_row(**kwargs) -> MagicMock:
    row = MagicMock(spec=CecchinoTodayFixture)
    row.id = kwargs.get("row_id", 42)
    row.scan_date = kwargs.get("scan_date", date(2026, 6, 8))
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    row.provider_fixture_id = kwargs.get("provider_fixture_id", 1499461)
    row.local_fixture_id = kwargs.get("local_fixture_id")
    row.competition_id = kwargs.get("competition_id")
    row.home_team_name = kwargs.get("home", "UAI Urquiza")
    row.away_team_name = kwargs.get("away", "Liniers")
    row.kickoff = datetime(2026, 6, 8, 20, 0, tzinfo=timezone.utc)
    row.odds_checked_at = None
    row.cecchino_output_json = kwargs.get(
        "cecchino_output_json",
        {
            "final": {
                "status": "available",
                "quota_1": 2.5,
                "quota_x": 3.0,
                "quota_2": 3.5,
                "prob_1": 0.4,
                "prob_x": 0.33,
                "prob_2": 0.27,
            },
        },
    )
    row.kpi_panel_json = kwargs.get("kpi_panel_json", {"version": "old", "rows": []})
    row.odds_snapshot_json = kwargs.get(
        "odds_snapshot_json",
        _snapshot_from_raw(
            _raw_payload(
                _bet("Match Winner", 1, [("Home", "2.63"), ("Draw", "2.80"), ("Away", "2.63")]),
            ),
            home=2.63,
            draw=2.80,
            away=2.63,
        ),
    )
    return row


def _new_odds_by_book() -> dict:
    return {
        _BETFAIR_ID: _raw_payload(
            _bet("Match Winner", 1, [("Home", "2.60"), ("Draw", "2.60"), ("Away", "2.80")]),
            _bet("Double Chance", 12, [("Home/Draw", "1.30"), ("Draw/Away", "1.40"), ("Home/Away", "1.20")]),
            _bet("Goals Over/Under", 5, [("Over 2.5", "2.10"), ("Under 2.5", "1.75")]),
        ),
    }


@pytest.fixture
def db():
    mock_db = MagicMock()
    mock_db.get.return_value = None
    return mock_db


def test_refresh_calls_only_betfair_bookmaker_id(db):
    row = _eligible_row()
    client = MagicMock()
    client.get_fixture_odds = MagicMock(return_value=_new_odds_by_book()[_BETFAIR_ID])
    client.get_fixture_odds_by_fixture = MagicMock(side_effect=AssertionError("no single-call"))
    client.set_usage_db = MagicMock()
    client.set_usage_context = MagicMock()

    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_only",
        ) as mock_fetch,
    ):
        mock_fetch.return_value = (_new_odds_by_book(), [])
        out = refresh_betfair_odds_for_fixture(db, row, force=True, rebuild_kpi=True, client=client)

    assert out["status"] == "ok"
    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args[0][1] == 1499461


def test_refresh_does_not_call_other_bookmaker_ids(db):
    row = _eligible_row()
    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_only",
        ) as mock_fetch,
    ):
        mock_fetch.return_value = (_new_odds_by_book(), [])
        refresh_betfair_odds_for_fixture(db, row, force=True, client=MagicMock())

    odds_by_book = mock_fetch.return_value[0]
    assert set(odds_by_book.keys()) == {_BETFAIR_ID}
    assert 8 not in odds_by_book
    assert 4 not in odds_by_book


def test_force_true_skips_load_cached_odds(db):
    row = _eligible_row()
    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_only",
        ) as mock_fetch,
        patch(
            "app.services.cecchino.cecchino_today_odds_fetch.load_cached_odds_for_fixture",
        ) as mock_cache,
    ):
        mock_fetch.return_value = (_new_odds_by_book(), [])
        refresh_betfair_odds_for_fixture(db, row, force=True, client=MagicMock())

    mock_cache.assert_not_called()


def test_refresh_updates_kpi_panel_json(db):
    row = _eligible_row()
    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_only",
        ) as mock_fetch,
    ):
        mock_fetch.return_value = (_new_odds_by_book(), [])
        out = refresh_betfair_odds_for_fixture(db, row, force=True, rebuild_kpi=True, client=MagicMock())

    assert out["status"] == "ok"
    assert row.kpi_panel_json is not None
    assert out["kpi_panel"] is not None
    assert out["kpi_panel"].get("version") != "old"
    assert len(out["kpi_panel"].get("rows") or []) > 0


def test_refresh_response_before_after_changed(db):
    row = _eligible_row()
    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_only",
        ) as mock_fetch,
    ):
        mock_fetch.return_value = (_new_odds_by_book(), [])
        out = refresh_betfair_odds_for_fixture(db, row, force=True, client=MagicMock())

    assert out["before"]["HOME"] == 2.63
    assert out["after"]["HOME"] == 2.60
    assert out["changed"] is True
    assert set(out["changed_markets"]) == {"HOME", "DRAW", "AWAY"}
    assert "manual_comparison_note" in out


def test_betfair_markets_json_from_snapshot_only_betfair(db):
    row = _eligible_row()
    raw = _raw_payload(
        _bet("Match Winner", 1, [("Home", "2.0"), ("Draw", "3.0"), ("Away", "4.0")]),
        _bet("Double Chance", 12, [("Home/Draw", "1.3"), ("Draw/Away", "1.5"), ("Home/Away", "1.2")]),
    )
    row.odds_snapshot_json = _snapshot_from_raw(raw, home=2.0, draw=3.0, away=4.0)

    out = build_betfair_markets_json(db, row, force=False)

    assert out["status"] == "ok"
    assert out["api_calls_used"] == 0
    assert "Bet365" not in str(out)
    assert out["raw_payload"]["filtered_to_betfair_only"] is True


def test_betfair_markets_json_force_fetches_api(db):
    row = _eligible_row()
    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_raw",
        ) as mock_raw,
    ):
        mock_raw.return_value = (_new_odds_by_book(), [], 1)
        out = build_betfair_markets_json(db, row, force=True)

    assert out["status"] == "ok"
    assert out["api_calls_used"] == 1


def test_betfair_markets_includes_all_bets_from_mock(db):
    row = _eligible_row()
    raw = _new_odds_by_book()[_BETFAIR_ID]
    row.odds_snapshot_json = _snapshot_from_raw(raw, home=2.60, draw=2.60, away=2.80)

    out = build_betfair_markets_json(db, row, force=False)
    markets = out["markets"] or []
    raw_names = {m["raw_market_name"] for m in markets}
    assert "Match Winner" in raw_names
    assert "Double Chance" in raw_names
    assert "Goals Over/Under" in raw_names
    assert len(markets) >= 3


def test_betfair_markets_match_winner_home_draw_away(db):
    row = _eligible_row(home="Inter", away="Milan")
    raw = _raw_payload(
        _bet("Match Winner", 1, [("Inter", "2.0"), ("Draw", "3.2"), ("Milan", "4.0")]),
    )
    row.odds_snapshot_json = _snapshot_from_raw(raw, home=2.0, draw=3.2, away=4.0)

    out = build_betfair_markets_json(db, row, force=False)
    mw = next(m for m in out["markets"] if m["raw_market_name"] == "Match Winner")
    by_sel = {v["normalized_selection"]: v for v in mw["values"]}
    assert float(by_sel["HOME"]["odd"]) == 2.0
    assert float(by_sel["DRAW"]["odd"]) == 3.2
    assert float(by_sel["AWAY"]["odd"]) == 4.0


def test_refresh_sets_odds_fetched_at(db):
    row = _eligible_row()
    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_only",
        ) as mock_fetch,
    ):
        mock_fetch.return_value = (_new_odds_by_book(), [])
        out = refresh_betfair_odds_for_fixture(db, row, force=True, client=MagicMock())

    assert out["bookmaker"]["odds_fetched_at"]
    assert out["bookmaker"]["odds_source"] == "api_live_refresh"
    assert out["bookmaker"]["is_cached"] is False


def test_refresh_records_api_usage_context(db):
    row = _eligible_row()
    client = MagicMock()
    client.set_usage_db = MagicMock()
    client.set_usage_context = MagicMock()

    with (
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh.check_api_budget_before_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_betfair_refresh._fetch_betfair_only",
        ) as mock_fetch,
    ):
        mock_fetch.return_value = (_new_odds_by_book(), [])
        refresh_betfair_odds_for_fixture(db, row, force=True, client=client)

    client.set_usage_db.assert_called_once_with(db)
    client.set_usage_context.assert_called_once()
    ctx = client.set_usage_context.call_args[0][0]
    assert "refresh_single_fixture_betfair" in ctx.job_id


def test_refresh_betfair_odds_by_id_not_found(db):
    db.get.return_value = None
    assert refresh_betfair_odds_by_id(db, 999) is None
