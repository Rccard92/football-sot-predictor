"""Test payload Betfair da raw/snapshot (Cecchino Fase 21)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cecchino.cecchino_betfair_odds_payload import (
    build_betfair_payload_from_raw,
    build_betfair_payload_from_snapshot,
)
from app.services.cecchino.cecchino_bookmaker_derive import derive_double_chance_from_1x2
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import (
    KPI_V2_ROW_DEFS,
    KPI_V2_VERSION,
    build_cecchino_kpi_panel_v2_betfair,
    normalize_kpi_panel_rows,
)
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
)
from app.services.cecchino.cecchino_today_service import (
    _kpi_panel_needs_rebuild,
    _resolve_kpi_panel_for_detail,
)


def _mock_1x2(h: float = 2.0, d: float = 3.2, a: float = 3.8) -> list[dict]:
    return [
        {
            "bookmakers": [
                {
                    "bets": [
                        {
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


def _mock_full_raw() -> dict[int, list]:
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    return {
        bid: [
            {
                "bookmakers": [
                    {
                        "bets": [
                            {
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "4.05"},
                                    {"value": "Draw", "odd": "3.50"},
                                    {"value": "Away", "odd": "2.10"},
                                ],
                            },
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 1.5", "odd": "1.35"},
                                    {"value": "Over 2.5", "odd": "2.10"},
                                    {"value": "Under 2.5", "odd": "1.75"},
                                    {"value": "Under 3.5", "odd": "1.25"},
                                ],
                            },
                            {
                                "name": "Goals Over/Under First Half",
                                "values": [
                                    {"value": "Under 1.5", "odd": "1.40"},
                                    {"value": "Over 0.5", "odd": "1.50"},
                                    {"value": "Over 1.5", "odd": "3.20"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _final_odds() -> dict:
    return {
        "status": "available",
        "quota_1": 2.11,
        "quota_x": 3.40,
        "quota_2": 4.50,
        "prob_1": 0.4739,
        "prob_x": 0.2941,
        "prob_2": 0.2222,
    }


def test_all_kpi_rows_have_segno_and_label():
    payload = build_betfair_payload_from_raw(_mock_full_raw())
    panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=_final_odds(),
        betfair_payload=payload,
    )
    expected = {key: label for key, label in KPI_V2_ROW_DEFS}
    for row in panel["rows"]:
        assert row["segno"] == expected[row["market_key"]]
        assert row["label"] == row["segno"]


def test_raw_match_winner_populates_quota_book():
    payload = build_betfair_payload_from_raw(_mock_full_raw())
    panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=_final_odds(),
        betfair_payload=payload,
    )
    by_key = {r["market_key"]: r for r in panel["rows"]}
    assert by_key[SEL_HOME]["quota_book"] == 4.05
    assert by_key[SEL_DRAW]["quota_book"] == 3.50
    assert by_key[SEL_AWAY]["quota_book"] == 2.10


def test_missing_betfair_quota_book_null():
    payload = build_betfair_payload_from_raw({})
    panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=_final_odds(),
        betfair_payload=payload,
    )
    assert payload["status"] == "not_available"
    assert all(r["quota_book"] is None for r in panel["rows"])


def test_dc_derived_from_1x2_formula():
    derived = derive_double_chance_from_1x2(2.0, 3.2, 4.0)
    p1, px, p2 = 1 / 2.0, 1 / 3.2, 1 / 4.0
    assert derived[SEL_ONE_X] == round(1 / (p1 + px), 2)

    payload = build_betfair_payload_from_raw({3: _mock_1x2(2.0, 3.2, 4.0)})
    bm = payload["bookmakers"][0]
    dc = bm["markets"][MARKET_DC]
    assert dc[SEL_ONE_X] == derived[SEL_ONE_X]
    assert bm["dc_derived"][SEL_ONE_X] is True


def test_ou_ft_mapped():
    payload = build_betfair_payload_from_raw(_mock_full_raw())
    ou = payload["bookmakers"][0]["markets"][MARKET_OU]
    assert ou[SEL_OVER_1_5] == 1.35
    assert ou[SEL_OVER_2_5] == 2.10
    assert ou[SEL_UNDER_2_5] == 1.75
    assert ou[SEL_UNDER_3_5] == 1.25


def test_ou_fh_mapped():
    payload = build_betfair_payload_from_raw(_mock_full_raw())
    ou_fh = payload["bookmakers"][0]["markets"][MARKET_OU_FH]
    assert ou_fh[SEL_UNDER_PT_1_5] == 1.40
    assert ou_fh[SEL_OVER_PT_0_5] == 1.50
    assert ou_fh[SEL_OVER_PT_1_5] == 3.20


def test_build_from_snapshot_raw_by_bookmaker():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    snapshot = {"raw_by_bookmaker_id": {str(bid): _mock_1x2(2.5, 3.0, 3.5)}}
    payload = build_betfair_payload_from_snapshot(snapshot)
    assert payload["status"] == "available"
    assert payload["odds_source"] == "cached_betfair_odds"


def test_normalize_kpi_panel_label_to_segno():
    legacy = {
        "version": KPI_V2_VERSION,
        "rows": [
            {"market_key": SEL_HOME, "label": "1", "quota_book": 2.0},
            {"market_key": SEL_DRAW, "label": "X"},
        ],
    }
    out = normalize_kpi_panel_rows(legacy)
    assert out["rows"][0]["segno"] == "1"
    assert out["rows"][0]["label"] == "1"
    assert out["rows"][1]["segno"] == "X"


def test_kpi_panel_needs_rebuild_when_quota_book_all_null():
    panel = {
        "version": KPI_V2_VERSION,
        "rows": [{"market_key": SEL_HOME, "segno": "1", "quota_book": None}],
    }
    assert _kpi_panel_needs_rebuild(panel) is True


def test_resolve_kpi_panel_rebuilds_from_snapshot():
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    row = SimpleNamespace(
        kpi_panel_json={
            "version": KPI_V2_VERSION,
            "rows": [{"market_key": SEL_HOME, "label": "1", "quota_book": None}],
        },
        odds_snapshot_json={"raw_by_bookmaker_id": {str(bid): _mock_1x2(2.0, 3.2, 4.0)}},
        cecchino_output_json={"final": _final_odds()},
        competition_id=1,
        local_fixture_id=10,
        home_team_name="Home FC",
        away_team_name="Away FC",
    )
    db = MagicMock()
    resolved = _resolve_kpi_panel_for_detail(row, db)
    home = next(r for r in resolved["rows"] if r["market_key"] == SEL_HOME)
    assert home["segno"] == "1"
    assert home["quota_book"] == 2.0
