"""Test rebuild offline Pannello KPI da cache Cecchino."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
    PROVIDER_API_FOOTBALL,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER, STATUS_AVAILABLE
from app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache import rebuild_kpi_panels_from_cache
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW_PT


def _goal_markets_draw_pt() -> dict:
    return {
        "DRAW_PT": {
            "market_key": "DRAW_PT",
            "final_odd": 2.20,
            "status": "available",
            "formula_version": "first_half_draw_empirical_shrinkage_v1",
        },
    }


def _snapshot_with_xpt_raw() -> dict:
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    return {
        "raw_by_bookmaker_id": {
            str(bid): [
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
                                    "name": "First Half Winner",
                                    "id": 13,
                                    "values": [
                                        {"value": "Home", "odd": "2.50"},
                                        {"value": "Draw", "odd": "2.05"},
                                        {"value": "Away", "odd": "3.00"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    }


def _snapshot_without_xpt_raw() -> dict:
    bid = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
    return {
        "raw_by_bookmaker_id": {
            str(bid): [
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
                            ],
                        },
                    ],
                },
            ],
        },
    }


def _fixture_row(*, snapshot: dict, goal_markets: dict | None) -> CecchinoTodayFixture:
    row = CecchinoTodayFixture(
        scan_date=date(2026, 7, 2),
        provider_source=PROVIDER_API_FOOTBALL,
        provider_fixture_id=999,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        home_team_name="Home FC",
        away_team_name="Away FC",
        league_name="Serie A",
        country_name="Italy",
    )
    row.id = 50
    row.odds_snapshot_json = snapshot
    row.cecchino_output_json = {
        "final": {
            "status": "available",
            "quota_1": 2.11,
            "quota_x": 3.40,
            "quota_2": 4.50,
            "prob_1": 0.47,
            "prob_x": 0.29,
            "prob_2": 0.22,
        },
        "goal_markets": goal_markets,
        "signals_matrix": {"status": STATUS_AVAILABLE, "inputs": {}, "rows": []},
    }
    row.kpi_panel_json = {"version": "legacy", "rows": []}
    return row


def test_rebuild_kpi_with_xpt_raw_sets_book_quote(monkeypatch):
    db = MagicMock()
    row = _fixture_row(snapshot=_snapshot_with_xpt_raw(), goal_markets=_goal_markets_draw_pt())
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache._fixtures_in_range",
        lambda *_a, **_k: [row],
    )

    payload = rebuild_kpi_panels_from_cache(
        db,
        date_from=date(2026, 7, 2),
        date_to=date(2026, 7, 2),
        include_xpt=True,
    )

    assert payload["kpi_rebuilt"] == 1
    assert payload["xpt_book_found"] == 1
    assert payload["xpt_cecchino_found"] == 1
    xpt = next(r for r in row.kpi_panel_json["rows"] if r["market_key"] == SEL_DRAW_PT)
    assert xpt["quota_book"] == pytest.approx(2.05)
    assert xpt["quota_cecchino"] == pytest.approx(2.20)
    db.commit.assert_called_once()
    db.delete.assert_not_called()


def test_rebuild_kpi_without_xpt_raw_reports_missing(monkeypatch):
    db = MagicMock()
    row = _fixture_row(snapshot=_snapshot_without_xpt_raw(), goal_markets=_goal_markets_draw_pt())
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache._fixtures_in_range",
        lambda *_a, **_k: [row],
    )

    payload = rebuild_kpi_panels_from_cache(
        db,
        date_from=date(2026, 7, 2),
        date_to=date(2026, 7, 2),
        include_xpt=True,
    )

    assert payload["status"] == "partial"
    assert payload["xpt_book_missing"] >= 1
    assert any("xpt_book_missing" in err for err in payload["errors"])


def test_rebuild_without_goal_markets_reports_missing(monkeypatch):
    db = MagicMock()
    row = _fixture_row(snapshot=_snapshot_with_xpt_raw(), goal_markets=None)
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache._fixtures_in_range",
        lambda *_a, **_k: [row],
    )

    payload = rebuild_kpi_panels_from_cache(
        db,
        date_from=date(2026, 7, 2),
        date_to=date(2026, 7, 2),
        include_xpt=True,
    )

    assert any("missing_goal_markets" in err for err in payload["errors"])
    assert payload["xpt_cecchino_missing"] >= 1


def test_rebuild_signals_after_applies_sync(monkeypatch):
    db = MagicMock()
    row = _fixture_row(snapshot=_snapshot_with_xpt_raw(), goal_markets=_goal_markets_draw_pt())
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache._fixtures_in_range",
        lambda *_a, **_k: [row],
    )
    sync_calls: list[int] = []

    def _fake_sync(_db, fixture_id):
        sync_calls.append(fixture_id)
        return {"min_book_odd_skipped": 0, "value_passed": 0}

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache.sync_cecchino_signal_activations",
        _fake_sync,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_panel_rebuild_from_cache.evaluate_activations_for_fixture",
        lambda *_a, **_k: {"evaluated": 0},
    )

    payload = rebuild_kpi_panels_from_cache(
        db,
        date_from=date(2026, 7, 2),
        date_to=date(2026, 7, 2),
        rebuild_signals_after=True,
        evaluate_after=True,
    )

    assert payload["signals_rebuilt"] == 1
    assert sync_calls == [50]
