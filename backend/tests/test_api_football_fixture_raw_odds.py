"""Test fixture raw odds filtrati e bookmaker_odds_detail."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app
from app.services.bookmakers.api_football_fixture_raw_odds_service import (
    ApiFootballFixtureRawOddsService,
)
from app.services.cecchino.cecchino_bookmaker_odds_detail import build_bookmaker_odds_detail
from app.services.cecchino.cecchino_selection_keys import SEL_OVER_1_5, SEL_OVER_2_5

client = TestClient(app)


def _mock_payload(*, with_over: bool = False) -> list[dict]:
    bets = [
        {
            "id": 1,
            "name": "Match Winner",
            "values": [
                {"value": "Home", "odd": "2.0"},
                {"value": "Draw", "odd": "3.0"},
                {"value": "Away", "odd": "4.0"},
            ],
        },
    ]
    if with_over:
        bets.append(
            {
                "id": 5,
                "name": "Goals Over/Under",
                "values": [
                    {"value": "Over 1.5", "odd": "1.42"},
                    {"value": "Over 2.5", "odd": "2.25"},
                ],
            },
        )
    return [{"bookmakers": [{"id": 8, "name": "Bet365", "bets": bets}]}]


def test_raw_odds_service_only_whitelist_bookmakers():
    svc = ApiFootballFixtureRawOddsService()
    with patch.object(svc._client, "get_fixture_odds", return_value=_mock_payload()) as mock_get:
        out = svc.run(provider_fixture_id=1520609, bookmaker_ids=[8, 3, 4, 99])
    assert out["status"] == "ok"
    assert mock_get.call_count == 3
    ids = {b["bookmaker_id"] for b in out["bookmakers"]}
    assert ids == {8, 3, 4}
    assert 99 not in ids


def test_raw_odds_summary_over_not_found():
    svc = ApiFootballFixtureRawOddsService()
    with patch.object(svc._client, "get_fixture_odds", return_value=_mock_payload(with_over=False)):
        out = svc.run(provider_fixture_id=1520609, bookmaker_ids=[8])
    assert out["summary"]["over_1_5_found"] is False
    assert out["summary"]["over_2_5_found"] is False
    assert out["over_under_debug"]["over_1_5"]["found"] is False


def test_raw_odds_summary_over_found():
    svc = ApiFootballFixtureRawOddsService()
    with patch.object(svc._client, "get_fixture_odds", return_value=_mock_payload(with_over=True)):
        out = svc.run(provider_fixture_id=1520609, bookmaker_ids=[8])
    assert out["summary"]["over_1_5_found"] is True
    assert out["summary"]["over_2_5_found"] is True
    assert "Bet365" in out["over_under_debug"]["over_1_5"]["found_in_bookmakers"]
    assert "Goals Over/Under" in out["over_under_debug"]["over_1_5"]["raw_market_names"]


def test_raw_odds_json_no_api_key():
    svc = ApiFootballFixtureRawOddsService()
    with patch.object(svc._client, "get_fixture_odds", return_value=_mock_payload(with_over=True)):
        out = svc.run(provider_fixture_id=1520609, bookmaker_ids=[8])
    blob = json.dumps(out).lower()
    assert "x-apisports-key" not in blob
    assert "api_football_key" not in blob


def test_bookmaker_odds_detail_always_includes_over_rows():
    detail = build_bookmaker_odds_detail({"rows": []})
    keys = [r["market_key"] for r in detail["rows"]]
    assert SEL_OVER_1_5 in keys
    assert SEL_OVER_2_5 in keys
    over_15 = next(r for r in detail["rows"] if r["market_key"] == SEL_OVER_1_5)
    assert over_15["book_average"] is None
    assert all(v is None for v in over_15["bookmakers"].values())
    assert over_15["status"] == "not_available"


def test_bookmaker_odds_detail_over_average_null_when_all_null():
    detail = build_bookmaker_odds_detail(
        {
            "rows": [
                {
                    "market_key": SEL_OVER_1_5,
                    "label": "OVER 1.5",
                    "bookmakers": {"Bet365": None, "Betfair": None, "Pinnacle": None},
                    "book_average": 3.08,
                    "status": "available",
                },
            ],
        },
    )
    over = next(r for r in detail["rows"] if r["market_key"] == SEL_OVER_1_5)
    assert over["book_average"] is None
    assert over["status"] == "not_available"


def test_bookmaker_odds_detail_over_partial_average():
    detail = build_bookmaker_odds_detail(
        {
            "rows": [
                {
                    "market_key": SEL_OVER_1_5,
                    "label": "OVER 1.5",
                    "bookmakers": {"Bet365": 1.4, "Betfair": 1.6, "Pinnacle": None},
                    "book_average": 1.5,
                    "status": "partial",
                },
            ],
        },
    )
    over = next(r for r in detail["rows"] if r["market_key"] == SEL_OVER_1_5)
    assert over["book_average"] == 1.5
    assert over["status"] == "partial"


def test_fixture_raw_odds_endpoint_mock():
    with patch(
        "app.routes.admin_bookmakers.ApiFootballFixtureRawOddsService.run",
        return_value={
            "status": "ok",
            "provider_source": "api_football",
            "provider_fixture_id": 1520609,
            "bookmakers_requested": [{"id": 8, "name": "Bet365"}],
            "bookmakers": [{"bookmaker_id": 8, "bookmaker_name": "Bet365", "markets": []}],
            "summary": {
                "bookmakers_found": [],
                "markets_found": [],
                "over_under_candidates": [],
                "match_winner_found": False,
                "over_1_5_found": False,
                "over_2_5_found": False,
            },
            "over_under_debug": {
                "over_1_5": {"found": False, "found_in_bookmakers": [], "raw_market_names": [], "raw_values": []},
                "over_2_5": {"found": False, "found_in_bookmakers": [], "raw_market_names": [], "raw_values": []},
            },
        },
    ):
        with patch("app.routes.admin_bookmakers.get_settings") as gs:
            gs.return_value.api_football_key = "test-key"
            resp = client.get(
                "/api/admin/bookmakers/fixture-raw-odds",
                params={"provider_fixture_id": 1520609, "bookmaker_ids": "8,3,4"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider_fixture_id"] == 1520609
    assert len(body["bookmakers"]) == 1
