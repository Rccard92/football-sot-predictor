"""Test mapping strict Betfair KPI (Cecchino Fase 22)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_betfair_odds_mapping import (
    is_strict_double_chance_market,
    is_strict_match_winner_market,
    normalize_double_chance_selection,
    normalize_match_winner_selection,
)
from app.services.cecchino.cecchino_betfair_odds_payload import build_betfair_payload_from_raw
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER
from app.services.cecchino.cecchino_kpi_debug_json import build_kpi_debug_json, get_kpi_debug_json
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_X_TWO,
)


def _bet(name: str, bet_id: int, values: list[tuple[str, str]]) -> dict:
    return {
        "id": bet_id,
        "name": name,
        "values": [{"value": v, "odd": o} for v, o in values],
    }


def _payload(*bets: dict) -> list[dict]:
    return [{"bookmakers": [{"bets": list(bets)}]}]


def test_strict_match_winner_only():
    assert is_strict_match_winner_market("Match Winner", 1)
    assert not is_strict_match_winner_market("First Half Winner", 13)
    assert not is_strict_match_winner_market("Second Half Winner", 3)
    assert not is_strict_match_winner_market("Team To Score First", 14)


def test_normalize_match_winner_home_draw_away():
    assert normalize_match_winner_selection("Home") == SEL_HOME
    assert normalize_match_winner_selection("Draw") == SEL_DRAW
    assert normalize_match_winner_selection("Away") == SEL_AWAY


def test_normalize_match_winner_team_names():
    assert normalize_match_winner_selection("Inter", "Inter", "Milan") == SEL_HOME
    assert normalize_match_winner_selection("Milan", "Inter", "Milan") == SEL_AWAY


def test_first_half_winner_not_used_for_1x2():
    rows, _ = parse_api_football_odds_response(
        _payload(
            _bet("Match Winner", 1, [("Home", "2.0"), ("Draw", "3.2"), ("Away", "4.0")]),
            _bet("First Half Winner", 13, [("Home", "2.5"), ("Draw", "2.0"), ("Away", "3.0")]),
        ),
        strict_betfair_kpi=True,
        requested_markets=[MARKET_1X2],
    )
    by_sk = {r["selection_key"]: r["odds_value"] for r in rows}
    assert by_sk[SEL_HOME] == 2.0
    assert by_sk[SEL_DRAW] == 3.2
    assert by_sk[SEL_AWAY] == 4.0


def test_double_chance_raw_mapping():
    rows, _ = parse_api_football_odds_response(
        _payload(
            _bet("Match Winner", 1, [("Home", "2.0"), ("Draw", "3.2"), ("Away", "4.0")]),
            _bet("Double Chance", 12, [("Home/Draw", "1.3"), ("Draw/Away", "1.5"), ("Home/Away", "1.2")]),
        ),
        strict_betfair_kpi=True,
    )
    dc = {r["selection_key"]: r for r in rows if r["normalized_market"] == "DOUBLE_CHANCE"}
    assert dc[SEL_ONE_X]["odds_value"] == 1.3
    assert dc[SEL_X_TWO]["odds_value"] == 1.5
    assert dc[SEL_ONE_TWO]["odds_value"] == 1.2
    assert dc[SEL_ONE_X]["provenance"]["source"] == "betfair_raw_double_chance"


def test_dc_derived_when_raw_missing():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    payload = build_betfair_payload_from_raw(
        {bid: _payload(_bet("Match Winner", 1, [("Home", "2.0"), ("Draw", "3.2"), ("Away", "4.0")]))},
        home_team_name="Inter",
        away_team_name="Milan",
    )
    bm = payload["bookmakers"][0]
    assert bm["dc_derived"][SEL_ONE_X] is True
    prov = payload["provenance_by_selection"][SEL_ONE_X]
    assert prov["source"] == "derived_from_betfair_1x2"


def test_1x2_source_betfair_raw_match_winner():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    payload = build_betfair_payload_from_raw(
        {bid: _payload(_bet("Match Winner", 1, [("Home", "2.0"), ("Draw", "3.2"), ("Away", "4.0")]))},
    )
    prov = payload["provenance_by_selection"][SEL_HOME]
    assert prov["source"] == "betfair_raw_match_winner"
    assert prov["raw_market_name"] == "Match Winner"


def test_normalize_dc_variants():
    assert normalize_double_chance_selection("1X") == SEL_ONE_X
    assert normalize_double_chance_selection("Home or Draw") == SEL_ONE_X
    assert normalize_double_chance_selection("12") == SEL_ONE_TWO


def test_kpi_debug_json_betfair_only():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    row = SimpleNamespace(
        id=42,
        local_fixture_id=10,
        provider_fixture_id=999,
        home_team_name="Inter",
        away_team_name="Milan",
        kickoff=None,
        eligibility_status="eligible",
        odds_snapshot_json={
            "raw_by_bookmaker_id": {
                str(bid): _payload(
                    _bet("Match Winner", 1, [("Inter", "2.0"), ("Draw", "3.2"), ("Milan", "4.0")]),
                ),
            },
        },
        cecchino_output_json={
            "final": {
                "status": "available",
                "quota_1": 2.1,
                "quota_x": 3.4,
                "quota_2": 4.5,
                "prob_1": 0.47,
                "prob_x": 0.29,
                "prob_2": 0.22,
            },
        },
        kpi_panel_json=None,
        competition_id=1,
    )
    db = MagicMock()
    out = build_kpi_debug_json(row, db)
    assert out["bookmaker"]["provider_bookmaker_id"] == 3
    assert out["bookmaker"]["name"] == "Betfair"
    assert "Bet365" not in str(out)
    assert "Pinnacle" not in str(out)
    home_used = out["betfair_odds_used"][SEL_HOME]
    assert home_used["raw_market_name"] == "Match Winner"
    assert home_used["raw_value"] == "Inter"
    assert len(out["raw_betfair_markets_used"]) >= 1


def test_get_kpi_debug_json_not_found():
    db = MagicMock()
    db.get.return_value = None
    assert get_kpi_debug_json(db, 1) is None
