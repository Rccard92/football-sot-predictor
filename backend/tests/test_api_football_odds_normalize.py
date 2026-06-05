"""Test normalizzazione e coerenza Over/Under API-Football."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app
from app.services.bookmakers.bookmaker_constants import MARKET_OVER_UNDER_GOALS
from app.services.bookmakers.market_normalize import (
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    normalize_api_football_market,
    normalize_over_under_selection,
)
from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_derive import build_bookmaker_structures
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS
from app.services.cecchino.cecchino_kpi_panel import build_cecchino_kpi_panel
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, MARKET_OU
from app.services.cecchino.cecchino_today_service import sync_today_bookmaker_odds

client = TestClient(app)


def _mock_ou_payload(*, over_15: float = 1.4, over_25: float = 2.2) -> list[dict]:
    return [
        {
            "bookmakers": [
                {
                    "bets": [
                        {
                            "id": 5,
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 1.5", "odd": str(over_15)},
                                {"value": "Under 1.5", "odd": "3.0"},
                                {"value": "Over 2.5", "odd": str(over_25)},
                                {"value": "Under 2.5", "odd": "1.8"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]


def _mock_1x2_payload(h: float = 2.0, d: float = 3.2, a: float = 4.0) -> list[dict]:
    return [
        {
            "bookmakers": [
                {
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": str(h)},
                                {"value": "Draw", "odd": str(d)},
                                {"value": "Away", "odd": str(a)},
                            ],
                        },
                    ],
                },
            ],
        },
    ]


def _row(bid: str, mkt: str, sk: str, val: float) -> SimpleNamespace:
    return SimpleNamespace(
        provider_bookmaker_id=bid,
        normalized_market=mkt,
        selection_key=sk,
        odds_value=val,
    )


def test_goals_over_under_market_normalized():
    assert normalize_api_football_market("Goals Over/Under", ["Over 1.5", "Under 1.5"]) == MARKET_OVER_UNDER_GOALS


def test_over_15_selection_normalized():
    assert normalize_over_under_selection("Over 1.5") == SEL_OVER_1_5


def test_over_25_selection_normalized():
    assert normalize_over_under_selection("Over 2.5") == SEL_OVER_2_5


def test_parse_api_football_over_rows():
    rows, missing = parse_api_football_odds_response(
        _mock_ou_payload(over_15=1.42, over_25=2.25),
        requested_markets=[MARKET_OU],
    )
    assert MARKET_OU not in missing
    keys = {r["selection_key"] for r in rows}
    assert SEL_OVER_1_5 in keys
    assert SEL_OVER_2_5 in keys
    over_15 = next(r for r in rows if r["selection_key"] == SEL_OVER_1_5)
    assert over_15["odds_value"] == 1.42
    assert over_15["market_label"] == "Goals Over/Under"
    assert over_15["provider_market_id"] == "5"


def test_sync_today_persists_over_with_bookmaker_id():
    db = MagicMock()
    odds_by_book = {8: _mock_ou_payload(over_15=1.5, over_25=2.5)}
    with patch("app.services.cecchino.cecchino_today_service.upsert_selection_odds") as upsert:
        saved = sync_today_bookmaker_odds(
            db,
            competition_id=1,
            fixture_id=10,
            api_fixture_id=999,
            odds_by_bookmaker=odds_by_book,
        )
    assert saved >= 2
    over_calls = [
        c
        for c in upsert.call_args_list
        if c.kwargs.get("normalized_market") == MARKET_OU
        and c.kwargs.get("selection_key") == SEL_OVER_1_5
    ]
    assert len(over_calls) == 1
    assert over_calls[0].kwargs["provider_bookmaker_id"] == "8"
    assert over_calls[0].kwargs["bookmaker_name"] == "Bet365"


def test_build_bookmaker_average_over_three_books():
    rows = []
    for bm in CECCHINO_BOOKMAKERS:
        bid = str(bm["provider_bookmaker_id"])
        rows.extend(
            [
                _row(bid, MARKET_1X2, "HOME", 2.0),
                _row(bid, MARKET_1X2, "DRAW", 3.0),
                _row(bid, MARKET_1X2, "AWAY", 4.0),
                _row(bid, MARKET_OU, SEL_OVER_1_5, 1.4),
                _row(bid, MARKET_OU, SEL_OVER_2_5, 2.2),
            ],
        )
    _, avg, _, status = build_bookmaker_structures(rows, bookmaker_defs=CECCHINO_BOOKMAKERS)
    assert status == "available"
    assert avg[MARKET_OU][SEL_OVER_1_5] == 1.4
    assert avg[MARKET_OU][SEL_OVER_2_5] == 2.2


def test_build_bookmaker_average_over_partial():
    rows = [
        _row("8", MARKET_1X2, "HOME", 2.0),
        _row("8", MARKET_1X2, "DRAW", 3.0),
        _row("8", MARKET_1X2, "AWAY", 4.0),
        _row("8", MARKET_OU, SEL_OVER_1_5, 1.4),
        _row("3", MARKET_1X2, "HOME", 2.1),
        _row("3", MARKET_1X2, "DRAW", 3.1),
        _row("3", MARKET_1X2, "AWAY", 4.1),
        _row("3", MARKET_OU, SEL_OVER_1_5, 1.6),
    ]
    _, avg, _, status = build_bookmaker_structures(rows, bookmaker_defs=CECCHINO_BOOKMAKERS)
    assert status == "partial"
    assert avg[MARKET_OU][SEL_OVER_1_5] == 1.5


def test_build_bookmaker_average_over_null_when_missing():
    rows = [
        _row("8", MARKET_1X2, "HOME", 2.0),
        _row("8", MARKET_1X2, "DRAW", 3.0),
        _row("8", MARKET_1X2, "AWAY", 4.0),
    ]
    _, avg, _, _ = build_bookmaker_structures(rows, bookmaker_defs=CECCHINO_BOOKMAKERS)
    assert avg[MARKET_OU][SEL_OVER_1_5] is None
    assert avg[MARKET_OU][SEL_OVER_2_5] is None


def _bookmaker_payload_with_ou(
    *,
    bet365_ou: dict[str, float] | None = None,
    betfair_ou: dict[str, float] | None = None,
    pinnacle_ou: dict[str, float] | None = None,
) -> dict:
    def _bm(name: str, ou: dict[str, float] | None) -> dict:
        if ou is None:
            return {"bookmaker_name": name, "status": "missing", "markets": {}}
        return {
            "bookmaker_name": name,
            "status": "available",
            "markets": {
                MARKET_1X2: {"HOME": 2.0, "DRAW": 3.0, "AWAY": 4.0},
                MARKET_OU: ou,
            },
        }

    bookmakers = [
        _bm("Bet365", bet365_ou),
        _bm("Betfair", betfair_ou),
        _bm("Pinnacle", pinnacle_ou),
    ]
    available = [b for b in bookmakers if b["status"] == "available"]
    avg_ou: dict[str, float | None] = {}
    for sk in (SEL_OVER_1_5, SEL_OVER_2_5):
        vals = [
            float(b["markets"][MARKET_OU][sk])
            for b in available
            if b["markets"].get(MARKET_OU, {}).get(sk) is not None
        ]
        avg_ou[sk] = round(sum(vals) / len(vals), 2) if vals else None

    return {
        "status": "available" if len(available) == 3 else ("partial" if available else "not_available"),
        "bookmakers": bookmakers,
        "bookmaker_average": {MARKET_1X2: {"HOME": 2.0, "DRAW": 3.0, "AWAY": 4.0}, MARKET_OU: avg_ou},
        "warnings": [],
    }


def test_kpi_over_rows_include_bookmakers_and_coherent_average():
    payload = _bookmaker_payload_with_ou(
        bet365_ou={SEL_OVER_1_5: 1.4, SEL_OVER_2_5: 2.2},
        betfair_ou={SEL_OVER_1_5: 1.5, SEL_OVER_2_5: 2.3},
        pinnacle_ou={SEL_OVER_1_5: 1.6, SEL_OVER_2_5: 2.4},
    )
    panel = build_cecchino_kpi_panel(
        statistical={"status": "not_available"},
        final_odds={"status": "not_available"},
        bookmaker_payload=payload,
    )
    over_15 = next(r for r in panel["rows"] if r["label"] == "OVER 1.5")
    assert over_15["bookmakers"]["Bet365"] == 1.4
    assert over_15["bookmakers"]["Betfair"] == 1.5
    assert over_15["bookmakers"]["Pinnacle"] == 1.6
    assert over_15["book_average"] == 1.5
    assert over_15["book"] == 1.5
    assert over_15["status"] == "available"


def test_kpi_over_no_average_when_all_books_empty():
    payload = _bookmaker_payload_with_ou()
    panel = build_cecchino_kpi_panel(
        statistical={"status": "not_available"},
        final_odds={"status": "not_available"},
        bookmaker_payload=payload,
    )
    over_15 = next(r for r in panel["rows"] if r["label"] == "OVER 1.5")
    assert over_15["bookmakers"]["Bet365"] is None
    assert over_15["book_average"] is None
    assert over_15["book"] is None
    assert over_15["status"] == "not_available"


def test_kpi_over_partial_status():
    payload = _bookmaker_payload_with_ou(
        bet365_ou={SEL_OVER_1_5: 1.4, SEL_OVER_2_5: 2.2},
        betfair_ou={SEL_OVER_1_5: 1.5, SEL_OVER_2_5: 2.3},
    )
    panel = build_cecchino_kpi_panel(
        statistical={"status": "not_available"},
        final_odds={"status": "not_available"},
        bookmaker_payload=payload,
    )
    over_15 = next(r for r in panel["rows"] if r["label"] == "OVER 1.5")
    assert over_15["status"] == "partial"
    assert over_15["book_average"] == 1.45


def test_goal_line_does_not_map_to_main_over():
    rows, _ = parse_api_football_odds_response(
        [
            {
                "bookmakers": [
                    {
                        "bets": [
                            {
                                "id": 5,
                                "name": "Goal Line",
                                "values": [{"value": "Over 1.5", "odd": "1.5"}],
                            },
                        ],
                    },
                ],
            },
        ],
        requested_markets=[MARKET_OU],
    )
    assert rows == []


def test_fixture_markets_debug_endpoint_mock():
    mock_payload = _mock_ou_payload()
    mock_payload[0]["bookmakers"][0]["bets"].append(
        {
            "id": 1,
            "name": "Match Winner",
            "values": [{"value": "Home", "odd": "2.0"}],
        },
    )
    with patch(
        "app.services.bookmakers.api_football_fixture_markets_debug_service.ApiFootballClient.get_fixture_odds",
        return_value=mock_payload,
    ):
        with patch("app.routes.admin_bookmakers.get_settings") as gs:
            gs.return_value.api_football_key = "test-key"
            resp = client.get(
                "/api/admin/bookmakers/fixture-markets-debug",
                params={"provider_fixture_id": 123456, "bookmaker_ids": "8"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider_fixture_id"] == 123456
    assert body["bookmakers"][0]["bookmaker_name"] == "Bet365"
    assert any(m["normalized_market"] == MARKET_OVER_UNDER_GOALS for m in body["bookmakers"][0]["markets"])
    assert len(body["detected_over_candidates"]) >= 2
    assert "api" not in str(body).lower() or "x-apisports-key" not in str(body)
