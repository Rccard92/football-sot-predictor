"""Test Affidabilità storica v1.1 — parità con shim empirico e payload canonico."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services.cecchino import cecchino_historical_reliability as hr
from app.services.cecchino import cecchino_purchasability_empirical as emp
from app.services.cecchino.cecchino_selection_keys import SEL_HOME


def _hist(
    *,
    fid: int,
    day: int,
    competition_id: int = 1,
    rating: int = 75,
    won: bool = True,
    selection: str = SEL_HOME,
    odds: float = 2.0,
) -> dict:
    kick = datetime(2026, 1, day, 15, 0, tzinfo=timezone.utc)
    status = "won" if won else "lost"
    profit = (odds - 1.0) if won else -1.0
    return {
        "canonical_row_key": f"h-{fid}-{selection}",
        "competition_id": competition_id,
        "selection": selection,
        "market_key": selection,
        "raw_market_code": selection,
        "rating": rating,
        "odds": odds,
        "settlement_status": status,
        "unit_stake_profit": profit,
        "is_settled_core": True,
        "snapshot_timestamp_verified": True,
        "snapshot_before_kickoff": True,
        "no_post_match_data_in_features": True,
        "leakage_status": "ok",
        "kickoff": kick.isoformat(),
    }


def _current(
    *,
    fid: int,
    rating: int = 76,
    selection: str = SEL_HOME,
    competition_id: int = 1,
    day: int = 28,
) -> dict:
    return {
        "today_fixture_id": fid,
        "provider_fixture_id": fid,
        "competition_id": competition_id,
        "scan_date": "2026-02-28",
        "kickoff": datetime(2026, 2, day, 18, 0, tzinfo=timezone.utc).isoformat(),
        "market_key": selection,
        "selection": selection,
        "raw_market_code": selection,
        "label": selection,
        "rating": rating,
        "odds": 2.05,
    }


def _numeric_fields(item: dict) -> dict:
    keys = (
        "score",
        "class",
        "sample_size",
        "selected_sample_size",
        "local_sample_size",
        "global_sample_size",
        "wins",
        "losses",
        "voids",
        "win_rate",
        "average_odds",
        "average_break_even_probability",
        "realized_margin",
        "roi",
        "stability_ratio",
        "cohort_scope",
        "fallback_used",
        "status",
    )
    return {k: item.get(k) for k in keys}


def test_hr_shim_alias_identity():
    assert emp.EMPIRICAL_VERSION is emp.HISTORICAL_RELIABILITY_VERSION
    assert emp.calculate_empirical_purchasability is hr.calculate_historical_reliability
    assert (
        emp.build_empirical_purchasability_for_panel
        is hr.build_historical_reliability_for_panel
    )
    assert emp.build_empirical_history_index is hr.build_historical_reliability_index
    assert (
        emp.build_empirical_global_history_index
        is hr.build_historical_reliability_global_index
    )


def test_hr_numeric_parity_shim_vs_canonical():
    hist = [
        _hist(fid=i, day=1 + (i % 20), rating=75, won=i % 3 != 0) for i in range(1, 45)
    ]
    currents = [_current(fid=900, rating=74)]
    kwargs = dict(
        date_from=date(2026, 2, 28),
        date_to=date(2026, 2, 28),
        history_rows=hist,
        current_rows=currents,
    )
    a = hr.build_historical_reliability_for_panel(MagicMock(), **kwargs)
    b = emp.build_empirical_purchasability_for_panel(MagicMock(), **kwargs)
    assert set(a["items"]) == set(b["items"])
    for key in a["items"]:
        assert _numeric_fields(a["items"][key]) == _numeric_fields(b["items"][key])
        assert a["items"][key]["score"] == b["items"][key]["score"]
        assert a["items"][key]["class"] == b["items"][key]["class"]


def test_hr_payload_metric_kind_and_versions():
    hist = [_hist(fid=i, day=1 + (i % 20), rating=72, won=True) for i in range(1, 40)]
    payload = hr.build_historical_reliability_for_panel(
        MagicMock(),
        date_from=date(2026, 2, 28),
        date_to=date(2026, 2, 28),
        history_rows=hist,
        current_rows=[_current(fid=1, rating=74)],
    )
    assert payload["metric_kind"] == "historical_reliability"
    assert payload["version"] == "cecchino_historical_reliability_v1_1"
    assert payload["legacy_version"] == "cecchino_purchasability_empirical_rating_v1_1"
    item = next(iter(payload["items"].values()))
    assert item["metric_kind"] == "historical_reliability"
    assert item["version"] == "cecchino_historical_reliability_v1_1"
    assert item["legacy_version"] == "cecchino_purchasability_empirical_rating_v1_1"


def test_hr_rating_below_50():
    payload = hr.build_historical_reliability_for_panel(
        MagicMock(),
        date_from=date(2026, 2, 28),
        date_to=date(2026, 2, 28),
        history_rows=[_hist(fid=1, day=1, rating=75)],
        current_rows=[_current(fid=2, rating=40)],
    )
    item = payload["items"][hr.panel_item_key(today_fixture_id=2, market_key=SEL_HOME)]
    assert item["status"] == "rating_below_scope"
    assert item["score"] is None
    assert item["class"] == "Non valutato"
    assert "Affidabilità storica" in item["explanation"]


def test_hr_insufficient_data():
    hist = [_hist(fid=i, day=1 + (i % 9), rating=75) for i in range(1, 10)]
    payload = hr.build_historical_reliability_for_panel(
        MagicMock(),
        date_from=date(2026, 2, 28),
        date_to=date(2026, 2, 28),
        history_rows=hist,
        current_rows=[_current(fid=99, rating=76)],
    )
    item = payload["items"][hr.panel_item_key(today_fixture_id=99, market_key=SEL_HOME)]
    assert item["status"] == "insufficient_data"
    assert item["score"] is None


def test_hr_local_vs_global_fallback():
    local = [
        _hist(fid=i, day=1 + (i % 20), competition_id=1, rating=75, won=True)
        for i in range(1, 40)
    ]
    payload_local = hr.build_historical_reliability_for_panel(
        MagicMock(),
        date_from=date(2026, 2, 28),
        date_to=date(2026, 2, 28),
        history_rows=local,
        current_rows=[_current(fid=500, rating=76, competition_id=1)],
    )
    item_l = payload_local["items"][
        hr.panel_item_key(today_fixture_id=500, market_key=SEL_HOME)
    ]
    assert item_l["status"] == "ok"
    assert item_l["cohort_scope"] == hr.SCOPE_LOCAL
    assert item_l["fallback_used"] is False

    global_hist = [
        _hist(fid=i, day=1 + (i % 20), competition_id=2, rating=75, won=i % 2 == 0)
        for i in range(1, 40)
    ] + [
        _hist(fid=100 + i, day=1 + (i % 5), competition_id=1, rating=75)
        for i in range(1, 5)
    ]
    payload_g = hr.build_historical_reliability_for_panel(
        MagicMock(),
        date_from=date(2026, 2, 28),
        date_to=date(2026, 2, 28),
        history_rows=global_hist,
        current_rows=[_current(fid=501, rating=76, competition_id=1)],
    )
    item_g = payload_g["items"][
        hr.panel_item_key(today_fixture_id=501, market_key=SEL_HOME)
    ]
    assert item_g["status"] == "ok"
    assert item_g["cohort_scope"] == hr.SCOPE_GLOBAL
    assert item_g["fallback_used"] is True


def test_hr_score_formula_unchanged():
    metrics = {
        "sample_size": 80,
        "wins": 45,
        "losses": 35,
        "voids": 0,
        "win_rate": 45 / 80,
        "average_odds": 2.1,
        "average_break_even_probability": 1 / 2.1,
        "realized_margin": (45 / 80) - (1 / 2.1),
        "total_profit": 8.0,
        "roi": 8.0 / 80,
        "positive_periods": 3,
        "total_periods": 4,
        "stability_ratio": 0.75,
    }
    out_hr = hr.calculate_historical_reliability(
        dict(metrics),
        rating=72,
        rating_band=hr.get_rating_band(72),
        selection=SEL_HOME,
    )
    out_emp = emp.calculate_empirical_purchasability(
        dict(metrics),
        rating=72,
        rating_band=emp.get_rating_band(72),
        selection=SEL_HOME,
    )
    assert out_hr["score"] == out_emp["score"]
    assert out_hr["class"] == out_emp["class"]
    assert out_hr["status"] == "ok"


def test_hr_module_is_not_purchasability_formula():
    src = open(hr.__file__, encoding="utf-8").read()
    assert "HISTORICAL_RELIABILITY_VERSION" in src
    assert "cecchino_purchasability_v1_preview_contract" not in src
    assert "metric_kind" in src
    # Nessuna factory Acquistabilità preview nel modulo HR
    assert "build_purchasability_preview" not in src
