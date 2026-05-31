"""Test filtro giornata esatta mini-run PIT."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.round_filter import (
    extract_fixture_round_number,
    fixture_matches_round_number,
)

_KICKOFF_3 = datetime(2025, 9, 1, 18, 45, tzinfo=timezone.utc)
_KICKOFF_13 = datetime(2025, 11, 1, 18, 45, tzinfo=timezone.utc)


def test_extract_fixture_round_number_serie_a():
    assert extract_fixture_round_number("Regular Season - 3") == 3
    assert extract_fixture_round_number("Regular Season - 13") == 13
    assert extract_fixture_round_number("regular season - 15") == 15


def test_fixture_matches_round_number_excludes_wrong_round():
    assert fixture_matches_round_number("Regular Season - 3", 3) is True
    assert fixture_matches_round_number("Regular Season - 13", 3) is False
    assert fixture_matches_round_number("Regular Season - 23", 3) is False


def test_select_fixtures_for_mini_run_round_number_exact():
    db = MagicMock()
    comp = MagicMock()
    db.get.return_value = comp

    fx3 = MagicMock()
    fx3.id = 29
    fx3.competition_id = 1
    fx3.home_team_id = 1
    fx3.away_team_id = 2
    fx3.kickoff_at = _KICKOFF_3
    fx3.round = "Regular Season - 3"
    fx3.status = "FT"

    fx13 = MagicMock()
    fx13.id = 130
    fx13.competition_id = 1
    fx13.home_team_id = 3
    fx13.away_team_id = 4
    fx13.kickoff_at = _KICKOFF_13
    fx13.round = "Regular Season - 13"
    fx13.status = "FT"

    db.scalars.return_value.all.return_value = [fx3, fx13]
    db.scalar.return_value = 2

    svc = BacktestFixtureDebugService()
    with patch.object(svc, "_fixture_to_candidate", side_effect=lambda _db, f: MagicMock(fixture_id=f.id, round=f.round)):
        selection = svc.select_fixtures_for_mini_run(
            db,
            competition_id=1,
            round_number=3,
            limit=20,
            offset=0,
        )

    assert len(selection.items) == 1
    assert selection.items[0].round == "Regular Season - 3"


@patch("app.routes.backtest_debug.SotV21MiniRunPreviewService")
def test_mini_run_post_round_number_filter_mode(mock_svc_cls):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.backtest_sot_v21_mini_run import (
        SotV21MiniRunResponse,
        SotV21MiniRunSelection,
        SotV21MiniRunSummary,
    )

    mock_svc_cls.return_value.run_preview.return_value = SotV21MiniRunResponse(
        status="ok",
        competition_id=1,
        competition_name="Serie A",
        selection=SotV21MiniRunSelection(
            limit=20,
            offset=0,
            round_number=3,
            round_contains=None,
            round_filter_mode="exact_round_number",
        ),
        summary=SotV21MiniRunSummary(fixtures_processed=10, fixtures_failed=0),
    )

    client = TestClient(app)
    response = client.post(
        "/api/backtest/debug/sot-v21-mini-run",
        json={
            "competition_id": 1,
            "round_number": 3,
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selection"]["round_filter_mode"] == "exact_round_number"
    assert body["selection"]["round_number"] == 3
    mock_svc_cls.return_value.run_preview.assert_called_once()
    assert mock_svc_cls.return_value.run_preview.call_args.kwargs["round_number"] == 3
