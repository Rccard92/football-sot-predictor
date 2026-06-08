"""Test KPI panel v2 Betfair-only."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import (
    KPI_V2_ROW_DEFS,
    KPI_V2_VERSION,
    build_cecchino_kpi_panel_v2_betfair,
    normalize_kpi_panel_rows,
    rating_label,
)
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE, STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_goal_poisson_v2 import FORMULA_V2
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_today_odds_fetch import (
    _book_ids_complete,
    _WANTED_BOOK_IDS,
    load_cached_odds_for_fixture,
    write_negative_odds_cache,
)


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


def _betfair_payload() -> dict:
    return {
        "status": "available",
        "bookmakers": [
            {
                "bookmaker_name": "Betfair",
                "provider_bookmaker_id": 3,
                "status": "available",
                "markets": {
                    "MATCH_WINNER_1X2": {
                        "HOME": 4.05,
                        "DRAW": 3.50,
                        "AWAY": 2.10,
                    },
                    "DOUBLE_CHANCE": {
                        "ONE_X": 1.55,
                        "X_TWO": 1.30,
                        "ONE_TWO": 1.20,
                    },
                    "OVER_UNDER_GOALS": {
                        "OVER_1_5": 1.35,
                        "OVER_2_5": 2.10,
                        "UNDER_2_5": 1.75,
                        "UNDER_3_5": 1.25,
                    },
                    "OVER_UNDER_GOALS_FIRST_HALF": {
                        "UNDER_PT_1_5": 1.40,
                        "OVER_PT_0_5": 1.50,
                        "OVER_PT_1_5": 3.20,
                    },
                },
            },
        ],
        "warnings": [],
    }


def _build():
    return build_cecchino_kpi_panel_v2_betfair(
        final_odds=_final_odds(),
        betfair_payload=_betfair_payload(),
    )


def _row_by_key(panel: dict, key: str) -> dict:
    return next(r for r in panel["rows"] if r["market_key"] == key)


def test_kpi_v2_rows_segno_and_label():
    panel = _build()
    expected = {key: label for key, label in KPI_V2_ROW_DEFS}
    for row in panel["rows"]:
        assert row["segno"] == expected[row["market_key"]]
        assert row["label"] == row["segno"]


def test_under_pt_15_segno_with_space():
    panel = _build()
    row = _row_by_key(panel, SEL_UNDER_PT_1_5)
    assert row["segno"] == "Under PT 1.5"
    assert row["label"] == "Under PT 1.5"


def test_normalize_legacy_label_only():
    legacy = {
        "version": KPI_V2_VERSION,
        "rows": [{"market_key": SEL_HOME, "label": "1", "quota_book": 4.05}],
    }
    out = normalize_kpi_panel_rows(legacy)
    assert out["rows"][0]["segno"] == "1"


def test_kpi_v2_columns_and_version():
    panel = _build()
    assert panel["version"] == KPI_V2_VERSION
    assert panel["bookmaker"]["name"] == "Betfair"
    assert panel["bookmaker"]["provider_bookmaker_id"] == 3
    cols = panel["columns"]
    assert "quota_book" in cols
    assert "rating" in cols
    assert len(panel["rows"]) == 13


def test_prob_book_formula():
    row = _row_by_key(_build(), SEL_HOME)
    assert row["quota_book"] == 4.05
    assert abs(row["prob_book"] - 1 / 4.05) < 0.0001


def test_prob_cecchino_formula():
    row = _row_by_key(_build(), SEL_HOME)
    assert row["quota_cecchino"] == 2.11
    assert abs(row["prob_cecchino"] - 1 / 2.11) < 0.0001


def test_vantaggio_prob_formula():
    row = _row_by_key(_build(), SEL_HOME)
    assert abs(row["vantaggio_prob"] - (row["prob_cecchino"] - row["prob_book"])) < 0.0001


def test_edge_pct_formula():
    row = _row_by_key(_build(), SEL_HOME)
    expected = (4.05 / 2.11 - 1) * 100
    assert abs(row["edge_pct"] - round(expected, 2)) < 0.01


def test_score_acquisto_formula():
    row = _row_by_key(_build(), SEL_HOME)
    expected = row["prob_cecchino"] * row["edge_pct"] / 100
    assert abs(row["score_acquisto"] - round(expected, 3)) < 0.001


def test_rating_formula_and_label():
    row = _row_by_key(_build(), SEL_HOME)
    assert row["rating"] is not None
    assert row["rating_label"] == rating_label(row["rating"])
    prob_pct = row["prob_cecchino"] * 100
    vant_pct = row["vantaggio_prob"] * 100
    raw = prob_pct * 0.5 + vant_pct * 2 + row["edge_pct"]
    assert row["rating"] == int(round(max(0, min(100, raw))))


def test_rating_labels():
    assert rating_label(95) == "Elite"
    assert rating_label(84) == "Premium"
    assert rating_label(72) == "Forte"
    assert rating_label(65) == "Buona"
    assert rating_label(55) == "Sufficiente"
    assert rating_label(45) == "Debole"
    assert rating_label(35) == "Scarto"


def test_ou_without_cecchino_no_rating():
    row = _row_by_key(_build(), SEL_OVER_1_5)
    assert row["quota_book"] is not None
    assert row["quota_cecchino"] is None
    assert row["edge_pct"] is None
    assert row["rating"] is None


def test_under_without_cecchino_no_rating():
    row = _row_by_key(_build(), SEL_UNDER_2_5)
    assert row["quota_book"] == 1.75
    assert row["quota_cecchino"] is None
    assert row["rating"] is None


def test_dc_cecchino_derived():
    panel = _build()
    row_1x = _row_by_key(panel, SEL_ONE_X)
    row_x2 = _row_by_key(panel, SEL_X_TWO)
    row_12 = _row_by_key(panel, SEL_ONE_TWO)
    assert row_1x["cecchino_source"] == "derived_from_1x2"
    assert row_1x["quota_cecchino"] == round(1 / (0.4739 + 0.2941), 2)
    assert row_x2["quota_cecchino"] == round(1 / (0.2941 + 0.2222), 2)
    assert row_12["quota_cecchino"] == round(1 / (0.4739 + 0.2222), 2)


def test_1x2_rows_have_rating():
    for key in (SEL_HOME, SEL_DRAW, SEL_AWAY):
        row = _row_by_key(_build(), key)
        assert row["rating"] is not None
        assert row["edge_pct"] is not None


def test_wanted_book_ids_betfair_only():
    assert _WANTED_BOOK_IDS == {3}


def test_book_ids_complete_betfair_only():
    bid = 3
    complete = {
        bid: [
            {
                "bookmakers": [
                    {
                        "bets": [
                            {
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2"},
                                    {"value": "Draw", "odd": "3"},
                                    {"value": "Away", "odd": "4"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }
    assert _book_ids_complete(complete)
    assert not _book_ids_complete({8: complete[bid]})


def _goal_markets() -> dict:
    return {
        SEL_OVER_1_5: {
            "formula_version": FORMULA_V2,
            "final_odd": 2.15,
            "status": STATUS_AVAILABLE,
        },
        SEL_OVER_2_5: {
            "formula_version": FORMULA_V2,
            "final_odd": 2.35,
            "status": STATUS_AVAILABLE,
        },
        SEL_UNDER_2_5: {
            "formula_version": FORMULA_V2,
            "final_odd": 1.90,
            "status": STATUS_AVAILABLE,
        },
        SEL_UNDER_3_5: {
            "formula_version": FORMULA_V2,
            "final_odd": 1.72,
            "status": STATUS_AVAILABLE,
        },
        SEL_OVER_PT_0_5: {
            "formula_version": FORMULA_V2,
            "final_odd": 1.43,
            "status": STATUS_AVAILABLE,
        },
        SEL_OVER_PT_1_5: {
            "formula_version": FORMULA_V2,
            "final_odd": 3.10,
            "status": STATUS_AVAILABLE,
        },
        SEL_UNDER_PT_1_5: {
            "formula_version": FORMULA_V2,
            "final_odd": 1.55,
            "status": STATUS_AVAILABLE,
        },
    }


def _build_with_goals():
    return build_cecchino_kpi_panel_v2_betfair(
        final_odds=_final_odds(),
        betfair_payload=_betfair_payload(),
        goal_markets=_goal_markets(),
    )


def test_kpi_populates_ou_ft_quota_cecchino():
    row = _row_by_key(_build_with_goals(), SEL_OVER_1_5)
    assert row["quota_cecchino"] == 2.15
    assert row["cecchino_source"] == FORMULA_V2
    assert row["prob_cecchino"] == pytest.approx(1 / 2.15, abs=0.0001)


def test_kpi_populates_pt_quota_cecchino():
    row = _row_by_key(_build_with_goals(), SEL_OVER_PT_0_5)
    assert row["quota_cecchino"] == 1.43
    assert row["cecchino_source"] == FORMULA_V2


def test_kpi_ou_edge_score_rating_with_goals():
    row = _row_by_key(_build_with_goals(), SEL_OVER_2_5)
    assert row["edge_pct"] is not None
    assert row["score_acquisto"] is not None
    assert row["rating"] is not None


def test_kpi_ou_insufficient_data_status():
    markets = {
        SEL_OVER_1_5: {
            "formula_version": FORMULA_V2,
            "final_odd": None,
            "status": STATUS_INSUFFICIENT_DATA,
        },
    }
    panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=_final_odds(),
        betfair_payload=_betfair_payload(),
        goal_markets=markets,
    )
    row = _row_by_key(panel, SEL_OVER_1_5)
    assert row["quota_cecchino"] is None
    assert row["status"] == STATUS_INSUFFICIENT_DATA


def test_kpi_ou_null_metrics_when_no_goal_data():
    row = _row_by_key(_build(), SEL_UNDER_3_5)
    assert row["quota_cecchino"] is None
    assert row["edge_pct"] is None
    assert row["rating"] is None
