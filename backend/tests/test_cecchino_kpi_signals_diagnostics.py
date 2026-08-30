"""Test diagnostics Segnali KPI (leggeri: niente ORM fixture completi)."""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.core.database import get_db
from app.routes.cecchino_kpi_signals import router as kpi_signals_router
from app.services.cecchino.cecchino_kpi_signals import KPI_SIGNAL_MARKET_DEFS
from app.services.cecchino.cecchino_kpi_signals_aggregation import (
    _accumulate_kpi_panel_diagnostics,
    _build_diagnostics,
)
from app.services.cecchino.cecchino_kpi_signals_purchasability import (
    PURCHASABILITY_STATUS_SCORE,
    PURCHASABILITY_STATUS_SCORE_PROVISIONAL,
    PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE,
    PURCHASABILITY_STATUS_UNSUPPORTED,
)
from app.services.cecchino.cecchino_purchasability_v3_opposition import SUPPORTED_V3_MARKETS


DIAGNOSTICS_KEYS = {
    "today_fixtures_count",
    "fixtures_with_kpi_panel",
    "kpi_rows_seen",
    "kpi_rows_supported",
    "kpi_rows_unsupported",
    "kpi_signals_created",
    "kpi_rows_below_50",
    "kpi_rows_without_book_odds",
    "supported_market_definitions",
    "activations_created_by_market",
    "rows_with_v3_snapshot",
    "rows_without_v3_snapshot",
    "rows_with_v31_snapshot",
    "rows_without_v31_snapshot",
    "v31_provisional_count",
    "v31_definitive_count",
    "v3_unsupported_count",
    "purchasability_snapshot_extraction_errors",
    "v3_supported_markets",
}


def test_accumulate_panel_empty_and_invalid():
    assert _accumulate_kpi_panel_diagnostics(None) == (0, 0, 0, 0, 0, 0)
    assert _accumulate_kpi_panel_diagnostics({}) == (0, 0, 0, 0, 0, 0)
    assert _accumulate_kpi_panel_diagnostics({"rows": []}) == (0, 0, 0, 0, 0, 0)
    assert _accumulate_kpi_panel_diagnostics({"rows": ["x"]}) == (1, 0, 0, 0, 0, 0)


def test_accumulate_panel_legacy_semantics():
    panel = {
        "rows": [
            {"market_key": "HOME", "segno": "1", "quota_book": 2.1, "rating": 75},
            {"market_key": "HOME", "segno": "1", "quota_book": 2.0, "rating": 40},
            {"market_key": "UNKNOWN_MKT", "segno": "Z", "quota_book": None, "rating": 80},
            {"market_key": "DRAW", "segno": "X", "quota_book": 3.0, "rating": 55},
        ]
    }
    has_rows, seen, supported, unsupported, below_50, without_book = (
        _accumulate_kpi_panel_diagnostics(panel)
    )
    assert has_rows == 1
    assert seen == 4
    assert supported == 2  # HOME 75 + DRAW 55
    assert unsupported == 1  # UNKNOWN_MKT
    assert below_50 == 1  # rating 40
    assert without_book == 1  # None quota


def _scalar_side_effect(values: list[int]):
    it = iter(values)

    def _inner(*_a, **_k):
        return next(it)

    return _inner


def test_build_diagnostics_shape_and_sql_path_no_full_orm():
    db = MagicMock()
    # count fixtures, count activations
    db.scalar.side_effect = _scalar_side_effect([3, 5])

    panel_rows = [
        ({"rows": [{"market_key": "HOME", "segno": "1", "quota_book": 2.0, "rating": 60}]},),
        ({"rows": []},),
        (
            {
                "rows": [
                    {"market_key": "ZZZ", "segno": "?", "quota_book": None, "rating": 20},
                ]
            },
        ),
    ]
    market_rows = [("HOME", 3), ("DRAW", 2)]
    agg = MagicMock(
        rows_with_v3=2,
        v3_unsupported=1,
        rows_with_v31=3,
        v31_provisional=1,
        v31_definitive=2,
    )

    execute_results = [
        panel_rows,  # stream panels
        market_rows,  # group by market
        agg,  # purchasability aggregates (.one())
    ]
    call_i = {"n": 0}

    def execute(_stmt):
        idx = call_i["n"]
        call_i["n"] += 1
        result = MagicMock()
        payload = execute_results[idx]
        if idx == 0:
            result.__iter__ = lambda self: iter(payload)
        elif idx == 1:
            result.all.return_value = payload
        else:
            result.one.return_value = payload
        return result

    db.execute.side_effect = execute

    out = _build_diagnostics(db, date_from=date(2026, 8, 1), date_to=date(2026, 8, 30))

    assert set(out.keys()) == DIAGNOSTICS_KEYS
    assert out["today_fixtures_count"] == 3
    assert out["fixtures_with_kpi_panel"] == 2
    assert out["kpi_rows_seen"] == 2
    assert out["kpi_rows_supported"] == 1
    assert out["kpi_rows_unsupported"] == 1
    assert out["kpi_rows_below_50"] == 1
    assert out["kpi_rows_without_book_odds"] == 1
    assert out["kpi_signals_created"] == 5
    assert out["activations_created_by_market"]["HOME"] == 3
    assert out["activations_created_by_market"]["DRAW"] == 2
    assert out["rows_with_v3_snapshot"] == 2
    assert out["rows_without_v3_snapshot"] == 3
    assert out["rows_with_v31_snapshot"] == 3
    assert out["rows_without_v31_snapshot"] == 2
    assert out["v31_provisional_count"] == 1
    assert out["v31_definitive_count"] == 2
    assert out["v3_unsupported_count"] == 1
    assert out["supported_market_definitions"] == len(KPI_SIGNAL_MARKET_DEFS)
    assert out["v3_supported_markets"] == sorted(SUPPORTED_V3_MARKETS)
    assert out["purchasability_snapshot_extraction_errors"] == 0
    assert db.scalar.call_count == 2
    assert db.execute.call_count == 3


def test_diagnostics_endpoint():
    app = FastAPI()
    app.include_router(kpi_signals_router, prefix="/api")

    db = MagicMock()
    db.scalar.side_effect = _scalar_side_effect([0, 0])

    def execute(_stmt):
        result = MagicMock()
        result.__iter__ = lambda self: iter([])
        result.all.return_value = []
        result.one.return_value = MagicMock(
            rows_with_v3=0,
            v3_unsupported=0,
            rows_with_v31=0,
            v31_provisional=0,
            v31_definitive=0,
        )
        return result

    db.execute.side_effect = execute

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    res = client.get("/api/cecchino/kpi-signals/diagnostics?date_from=2026-08-01&date_to=2026-08-30")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert set(body["diagnostics"].keys()) == DIAGNOSTICS_KEYS
    assert body["filters"]["date_from"] == "2026-08-01"


def test_purchasability_status_constants_used_in_filters():
    # Guard: semantics empty-state dipendono da questi status string.
    assert PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE == "snapshot_unavailable"
    assert PURCHASABILITY_STATUS_UNSUPPORTED == "unsupported_market"
    assert PURCHASABILITY_STATUS_SCORE == "score"
    assert PURCHASABILITY_STATUS_SCORE_PROVISIONAL == "score_provisional"
