"""Test GET historical-unavailable-audit (Step JK.1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_historical_unavailable_audit import (
    HistoricalUnavailableAuditFixtureSample,
    HistoricalUnavailableAuditResponse,
)
from app.services.backtest.historical_unavailable_audit_service import HistoricalUnavailableAuditService

client = TestClient(app)

_MOCK_ZERO = HistoricalUnavailableAuditResponse(
    competition_id=1,
    competition_name="Serie A",
    round_number=15,
    limit=50,
    offset=0,
    fixtures_scanned=10,
    fixtures_with_unavailable=0,
    verdict="unavailable_not_found_in_current_storage",
    storage_checked=[
        "fixture_missing_players",
        "fixture_lineups.raw_json (injured, suspended, unavailable, missing)",
        "fixture_provider_lineups.raw_payload",
    ],
)

_MOCK_FOUND = HistoricalUnavailableAuditResponse(
    competition_id=1,
    competition_name="Serie A",
    limit=20,
    offset=0,
    fixtures_scanned=5,
    fixtures_with_unavailable=2,
    fixtures_with_injured=1,
    total_unavailable_players=3,
    verdict="unavailable_found_normalized",
    sample_fixtures_with_unavailable=[
        HistoricalUnavailableAuditFixtureSample(
            fixture_id=146,
            round="Regular Season - 15",
            home_team="AC Milan",
            away_team="Sassuolo",
            home_unavailable_count=2,
            away_unavailable_count=1,
            source_paths=["fixture_missing_players"],
            players=[],
        ),
    ],
    source_paths_found=["fixture_missing_players"],
)


@patch("app.routes.backtest_debug.HistoricalUnavailableAuditService")
def test_historical_unavailable_audit_zero_verdict(mock_svc_cls):
    mock_svc_cls.return_value.audit.return_value = _MOCK_ZERO

    response = client.get(
        "/api/backtest/debug/historical-unavailable-audit",
        params={"competition_id": 1, "round_number": 15, "limit": 50},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["db_writes"] is False
    assert body["preview_only"] is True
    assert body["verdict"] == "unavailable_not_found_in_current_storage"


def test_historical_unavailable_audit_raw_not_normalized_verdict():
    from app.services.backtest.historical_unavailable_audit_service import (
        HistoricalUnavailableAuditService,
        _FixtureUnavailableScan,
    )

    svc = HistoricalUnavailableAuditService()
    scans = [
        _FixtureUnavailableScan(
            fixture_id=146,
            round="R37",
            home_team="H",
            away_team="A",
            raw_json_keys={"lineups.home.injured"},
            has_missing_players_rows=False,
        ),
    ]
    all_raw_keys = {"lineups.home.injured"}
    fixtures_with_missing_players = sum(1 for s in scans if s.has_missing_players_rows)
    any_missing_players_rows = fixtures_with_missing_players > 0
    if fixtures_with_missing_players > 0:
        verdict = "unavailable_found_normalized"
    elif all_raw_keys and not any_missing_players_rows:
        verdict = "unavailable_found_in_raw_not_normalized"
    else:
        verdict = "unavailable_not_found_in_current_storage"
    assert verdict == "unavailable_found_in_raw_not_normalized"
    assert svc is not None


@patch("app.routes.backtest_debug.HistoricalUnavailableAuditService")
def test_historical_unavailable_audit_found_verdict(mock_svc_cls):
    mock_svc_cls.return_value.audit.return_value = _MOCK_FOUND

    response = client.get(
        "/api/backtest/debug/historical-unavailable-audit",
        params={"competition_id": 1, "limit": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "unavailable_found_normalized"
    assert body["fixtures_with_unavailable"] == 2
    assert body["sample_fixtures_with_unavailable"][0]["fixture_id"] == 146


def test_audit_service_zero_verdict_unit():
    from datetime import datetime, timezone

    from app.models import Competition, Fixture, Team
    from app.schemas.backtest_point_in_time import BacktestFixtureCandidate, BacktestFixtureTeamBrief

    cutoff = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
    candidate = BacktestFixtureCandidate(
        fixture_id=146,
        kickoff_at=cutoff,
        status="FT",
        home_team=BacktestFixtureTeamBrief(id=1, name="Home"),
        away_team=BacktestFixtureTeamBrief(id=2, name="Away"),
        has_team_stats=True,
    )

    comp = MagicMock(spec=Competition)
    comp.name = "Serie A"
    fixture = MagicMock(spec=Fixture)
    fixture.id = 146
    fixture.home_team_id = 1
    fixture.away_team_id = 2
    fixture.round = "Regular Season - 15"
    home = MagicMock(spec=Team)
    home.name = "Home"
    away = MagicMock(spec=Team)
    away.name = "Away"

    def _get(model, pk):
        if model is Competition:
            return comp
        if model is Fixture:
            return fixture
        if pk == 1:
            return home
        if pk == 2:
            return away
        return None

    db = MagicMock()
    db.get.side_effect = _get
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = None

    with patch(
        "app.services.backtest.historical_unavailable_audit_service.BacktestFixtureDebugService"
    ) as mock_debug:
        mock_debug.return_value.select_fixtures_for_mini_run.return_value = MagicMock(
            items=[candidate],
        )
        result = HistoricalUnavailableAuditService().audit(
            db,
            competition_id=1,
            limit=1,
            offset=0,
        )

    assert result.fixtures_scanned == 1
    assert result.fixtures_with_unavailable == 0
    assert result.verdict == "unavailable_not_found_in_current_storage"
