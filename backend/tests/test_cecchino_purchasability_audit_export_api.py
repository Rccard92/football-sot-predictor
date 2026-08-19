"""Test API GET /api/cecchino/today/{id}/purchasability-audit-export."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes.cecchino_today import router
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit_export import (
    PURCHASABILITY_AUDIT_EXPORT_CONTRACT_VERSION,
    build_purchasability_audit_export,
)
from app.services.cecchino.cecchino_purchasability_v31_opposition import market_label_for
from app.services.cecchino.cecchino_selection_keys import (
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_X_TWO,
)


def _kpi_row(
    market_key: str,
    *,
    quota_book: float | None = 2.10,
    bookmaker_name: str = "Betfair",
    provider_bookmaker_id: int = 3,
    book_fallback_used: bool = False,
) -> dict:
    q_c = 1.95
    pb = (1.0 / quota_book) if quota_book else None
    pc = (1.0 / q_c) if q_c else None
    edge = round((quota_book / q_c - 1) * 100, 2) if quota_book and q_c else None
    return {
        "market_key": market_key,
        "segno": market_label_for(market_key),
        "label": market_label_for(market_key),
        "quota_book": quota_book,
        "quota_cecchino": q_c,
        "prob_book": pb,
        "prob_cecchino": pc,
        "vantaggio_prob": round(pc - pb, 4) if pb is not None and pc is not None else None,
        "edge_pct": edge,
        "score_acquisto": 0.45,
        "rating": 62,
        "rating_label": "Buona",
        "status": "available" if quota_book else "not_available",
        "book_source": "betfair_panel" if not book_fallback_used else "bet365_fallback",
        "bookmaker_name": bookmaker_name,
        "provider_bookmaker_id": provider_bookmaker_id,
        "book_fallback_used": book_fallback_used,
    }


def _v31_item(
    market_key: str,
    *,
    status: str = "score",
    score_v31: int | None = 64,
) -> dict:
    return {
        "market_key": market_key,
        "label": market_label_for(market_key),
        "market_family": "MATCH_WINNER_FT" if market_key == SEL_HOME else None,
        "period": "FT",
        "line": None,
        "status": status,
        "score_v31": score_v31,
        "raw_score_v31": float(score_v31) if score_v31 is not None else None,
        "class_v31": "Alta" if score_v31 and score_v31 >= 60 else "Media",
        "calculation_quality": "full",
        "gate": {"gate_status": "passed", "gate_reason_codes": []},
        "gate_reason_codes": [],
        "reason_codes": ["positive_edge"],
        "reading_short": f"Score {score_v31}",
        "reading_detailed": f"Dettaglio {market_key}",
        "input": {
            "quota_book": 2.10,
            "quota_cecchino": 1.95,
            "edge_pct": 7.69,
            "probability_advantage_pp": 2.5,
            "rating": 62,
        },
        "fair_book_audit": {
            "selected_fair_probability": 0.476,
            "raw_probability": 0.48,
        },
        "theoretical": {"theoretical_raw_score": 70.0, "value_score": 65},
        "historical": {"historical_multiplier": 0.92},
        "formula_steps": ["step1"],
        "formula_version": "cecchino_purchasability_v31_fixed_discount_empirical_v2",
    }


def _eligible_row() -> SimpleNamespace:
    rows = []
    for mk in PANEL_MARKET_KEYS:
        if mk == SEL_X_TWO:
            rows.append(
                _kpi_row(
                    mk,
                    quota_book=2.05,
                    bookmaker_name="Bet365",
                    provider_bookmaker_id=8,
                    book_fallback_used=True,
                )
            )
        elif mk == SEL_OVER_2_5:
            rows.append(_kpi_row(mk, quota_book=None))
        else:
            rows.append(_kpi_row(mk))

    v31_items = [
        _v31_item(SEL_HOME, score_v31=76),
        _v31_item(SEL_DRAW, score_v31=42),
        _v31_item(SEL_X_TWO, score_v31=68),
        _v31_item(SEL_OVER_2_5, status="gate_failed", score_v31=None),
        _v31_item("UNDER_2_5", status="non_calculable", score_v31=None),
    ]

    return SimpleNamespace(
        id=7,
        local_fixture_id=1,
        provider_fixture_id=555,
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc),
        scan_date=date(2026, 8, 19),
        competition_id=1,
        provider_season=2026,
        country_name="Italy",
        league_name="Serie A",
        eligibility_status="eligible",
        goals_home=2,
        goals_away=1,
        score_fulltime_home=2,
        score_fulltime_away=1,
        odds_snapshot_json={},
        cecchino_output_json={
            "purchasability_preview_v31": {
                "snapshot_version": "cecchino_purchasability_snapshot_v31_v2",
                "formula_version": "cecchino_purchasability_v31_fixed_discount_empirical_v2",
                "candidate_version": "cecchino_purchasability_v31_shadow_v2",
                "source_snapshot_at": "2026-08-19T10:00:00+00:00",
                "source_snapshot_verified": True,
                "items": v31_items,
            },
            "purchasability_preview_v3": {
                "formula_version": "cecchino_purchasability_v3_fixed_discount_v1",
                "items": [
                    {
                        "market_key": SEL_HOME,
                        "status": "score",
                        "score": 70,
                        "linked_market_context": {
                            "linked_market_key": "X_TWO",
                            "relationship": "double_chance_overlap",
                        },
                    }
                ],
            },
            "signals_matrix": {"version": "cecchino_signals_v2"},
        },
        kpi_panel_json={
            "version": "cecchino_kpi_v2_canonical_book_v1",
            "rows": rows,
            "warnings": [],
        },
    )


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = MagicMock()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override

    with TestClient(app) as c:
        yield c, db


def test_api_not_found(client):
    c, db = client
    db.get.return_value = None
    r = c.get("/api/cecchino/today/1/purchasability-audit-export")
    assert r.status_code == 404


def test_api_export_ok(client):
    c, db = client
    db.get.return_value = _eligible_row()
    r = c.get("/api/cecchino/today/7/purchasability-audit-export")
    assert r.status_code == 200
    body = r.json()
    assert body["contract_version"] == PURCHASABILITY_AUDIT_EXPORT_CONTRACT_VERSION
    assert len(body["market_order"]) == 19
    assert len(body["markets"]) == 19
    assert len(body["market_context"]["BOOK"]) == 19
    assert len(body["market_context"]["CECCHINO"]) == 19


def test_export_service_contract_and_markets():
    row = _eligible_row()
    db = MagicMock()
    db.get.return_value = row
    payload = build_purchasability_audit_export(db, 7)
    assert payload is not None
    assert payload["contract_version"] == "cecchino_purchasability_audit_export_v1"
    assert payload["fixture"]["today_fixture_id"] == 7
    assert payload["fixture"]["provider_fixture_id"] == 555
    assert "goals_home" not in payload["fixture"]
    assert "final_score" not in payload["fixture"]

    home = payload["markets"][SEL_HOME]
    assert home["purchasability_v31"]["score_v31"] == 76
    assert home["purchasability_v31"]["reading_short"] == "Score 76"
    assert home["complement_selection_keys"]
    assert home["market_family"] == "MATCH_WINNER_FT"
    assert home["linked_relationships"] is not None

    x2 = payload["markets"][SEL_X_TWO]
    assert x2["kpi_raw"]["bookmaker_name"] == "Bet365"
    assert x2["kpi_raw"]["book_fallback_used"] is True
    assert x2["kpi_raw"]["provider_bookmaker_id"] == 8
    assert payload["market_context"]["BOOK"][SEL_X_TWO]["bookmaker_name"] == "Bet365"

    ou = payload["markets"][SEL_OVER_2_5]
    assert ou["kpi_raw"]["quota_book"] is None
    assert ou["purchasability_v31"]["status"] == "gate_failed"

    assert payload["source_versions"]["historical_reliability_version"] == "cecchino_historical_reliability_v1_1"
    assert payload["source_versions"]["signals_version"] == "cecchino_signals_v2"


def test_export_preserves_nulls():
    row = _eligible_row()
    db = MagicMock()
    db.get.return_value = row
    payload = build_purchasability_audit_export(db, 7)
    assert payload is not None
    missing_v31 = payload["markets"]["AWAY_PT"]["purchasability_v31"] is None
    assert missing_v31
    assert payload["market_context"]["BOOK"]["AWAY_PT"]["quota"] is not None


def test_export_no_db_write(client):
    c, db = client
    row = _eligible_row()
    db.get.return_value = row
    r = c.get("/api/cecchino/today/7/purchasability-audit-export")
    assert r.status_code == 200
    db.add.assert_not_called()
    db.commit.assert_not_called()
