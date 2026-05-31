"""Test GET historical-lineup-audit (Step G2A)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_historical_lineup_audit import (
    HistoricalLineupAuditFixtureResponse,
    HistoricalLineupAuditRoundFixtureBrief,
    HistoricalLineupAuditRoundResponse,
    HistoricalLineupAuditRoundSummary,
    HistoricalLineupPlayerMappingSummary,
    HistoricalLineupSideAudit,
    HistoricalLineupSideCoverage,
)
from app.services.backtest.historical_lineup_audit_service import HistoricalLineupAuditService
from app.services.backtest.pit_player_rolling_stats import RawPlayerRow, build_player_prior_stats, timestamp_audit

client = TestClient(app)

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)

_SIDE = HistoricalLineupSideAudit(
    team_id=1,
    team_name="AC Milan",
    coverage=HistoricalLineupSideCoverage(
        has_official_xi=True,
        starters_count=11,
        bench_count=9,
        formation="4-3-3",
        source_table="fixture_lineups",
        source_provider="api_football",
        source_timestamp=_CUTOFF,
        is_timestamp_safe=True,
        source_timestamp_status="safe",
    ),
    mapping=HistoricalLineupPlayerMappingSummary(
        starters_with_provider_player_id=11,
        starters_with_internal_player_id=10,
        starters_matched_to_fixture_player_stats_prior=9,
        mapping_coverage_pct=100.0,
        player_stats_prior_coverage_pct=81.82,
    ),
)

_MOCK_FIXTURE = HistoricalLineupAuditFixtureResponse(
    competition_id=1,
    competition_name="Serie A",
    fixture_id=146,
    round="Regular Season - 15",
    kickoff_at=_CUTOFF,
    cutoff_time=_CUTOFF,
    fixture_status="FT",
    home_team="AC Milan",
    away_team="Sassuolo",
    home_team_id=1,
    away_team_id=2,
    home=_SIDE,
    away=_SIDE.model_copy(update={"team_id": 2, "team_name": "Sassuolo"}),
)

_MOCK_ROUND = HistoricalLineupAuditRoundResponse(
    competition_id=1,
    competition_name="Serie A",
    round_number=15,
    limit=20,
    offset=0,
    summary=HistoricalLineupAuditRoundSummary(
        fixtures_processed=10,
        fixtures_with_official_xi_both_teams=8,
        fixtures_with_partial_lineup=1,
        fixtures_without_lineup=1,
        avg_mapping_coverage_pct=92.5,
        avg_player_stats_prior_coverage_pct=78.0,
        timestamp_safe_count=7,
        timestamp_missing_count=3,
    ),
    fixtures=[
        HistoricalLineupAuditRoundFixtureBrief(
            fixture_id=146,
            match="AC Milan vs Sassuolo",
            round="Regular Season - 15",
            kickoff_at=_CUTOFF,
            home_has_official_xi=True,
            away_has_official_xi=True,
            home_starters_count=11,
            away_starters_count=11,
            home_mapping_coverage_pct=100.0,
            away_mapping_coverage_pct=100.0,
            home_prior_stats_coverage_pct=81.82,
            away_prior_stats_coverage_pct=72.73,
            source_timestamp_status="safe",
        ),
    ],
    db_writes=False,
)


@patch("app.routes.backtest_debug.HistoricalLineupAuditService")
def test_historical_lineup_audit_fixture_success(mock_svc_cls):
    mock_svc_cls.return_value.audit_fixture.return_value = _MOCK_FIXTURE

    response = client.get(
        "/api/backtest/debug/historical-lineup-audit/fixture",
        params={"competition_id": 1, "fixture_id": 146},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["db_writes"] is False
    assert body["preview_only"] is True
    assert body["audit_mode"] == "historical_official_xi"
    assert body["home"]["coverage"]["has_official_xi"] is True
    assert body["home"]["coverage"]["starters_count"] == 11


@patch("app.routes.backtest_debug.HistoricalLineupAuditService")
def test_historical_lineup_audit_round_success(mock_svc_cls):
    mock_svc_cls.return_value.audit_round.return_value = _MOCK_ROUND

    response = client.get(
        "/api/backtest/debug/historical-lineup-audit/round",
        params={"competition_id": 1, "round_number": 15},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["fixtures_processed"] == 10
    assert body["db_writes"] is False
    assert body["competition_id"] == 1


@patch("app.routes.backtest_debug.HistoricalLineupAuditService")
def test_historical_lineup_audit_fixture_competition_mismatch(mock_svc_cls):
    mock_svc_cls.return_value.audit_fixture.side_effect = HTTPException(
        status_code=422,
        detail={"code": "fixture_competition_mismatch", "message": "mismatch"},
    )

    response = client.get(
        "/api/backtest/debug/historical-lineup-audit/fixture",
        params={"competition_id": 2, "fixture_id": 146},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "fixture_competition_mismatch"


def test_timestamp_missing_does_not_block_audit():
    ts, is_safe, status, warnings = timestamp_audit(None)
    assert status == "missing"
    assert is_safe is False
    assert ts is None
    assert "historical_official_xi_without_source_timestamp" in warnings


def test_player_prior_leakage_warning():
    row = RawPlayerRow(
        player_name="Test Player",
        provider_player_id=None,
        api_player_id=999,
        position="F",
        is_starter=True,
    )
    db = MagicMock()
    db.scalars.return_value.all.side_effect = [[], []]
    player = build_player_prior_stats(
        db,
        row=row,
        competition_id=1,
        team_id=1,
        cutoff=_CUTOFF,
    )
    assert player.mapping_status in ("no_internal_id", "no_prior_stats", "matched", "ambiguous")
    assert player.latest_player_stat_fixture_used_at is None or player.latest_player_stat_fixture_used_at < _CUTOFF


def test_lineup_audit_service_no_db_writes():
    from app.models import Competition, Fixture, Team

    db = MagicMock()
    comp = MagicMock()
    comp.name = "Serie A"
    home_team = MagicMock()
    home_team.name = "AC Milan"
    away_team = MagicMock()
    away_team.name = "Sassuolo"
    fixture = MagicMock()
    fixture.id = 146
    fixture.competition_id = 1
    fixture.home_team_id = 1
    fixture.away_team_id = 2
    fixture.kickoff_at = _CUTOFF
    fixture.round = "Regular Season - 15"
    fixture.status = "FT"

    def _get(model, pk):
        if model is Competition:
            return comp
        if model is Fixture:
            return fixture
        if model is Team and pk == 1:
            return home_team
        if model is Team and pk == 2:
            return away_team
        return None

    db.get.side_effect = _get
    db.scalars.return_value.all.return_value = []

    svc = HistoricalLineupAuditService()
    with patch.object(svc, "_build_side_audit", return_value=_SIDE):
        result = svc.audit_fixture(db, competition_id=1, fixture_id=146)

    assert result.db_writes is False
    assert result.preview_only is True
    db.add.assert_not_called()
    db.commit.assert_not_called()
