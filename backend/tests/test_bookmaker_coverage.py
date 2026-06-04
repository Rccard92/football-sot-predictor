"""Test coverage bookmaker per competizione."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.models.fixture import Fixture
from app.services.bookmakers.bookmaker_coverage_service import BookmakerCoverageService


def _fx(fid: int, kickoff: datetime) -> Fixture:
    fx = MagicMock(spec=Fixture)
    fx.id = fid
    fx.competition_id = 99
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.kickoff_at = kickoff
    fx.status = "NS"
    fx.round = "R18"
    fx.raw_json = None
    return fx


@patch("app.services.bookmakers.bookmaker_coverage_service.list_odds_for_fixtures")
@patch("app.services.bookmakers.bookmaker_coverage_service.select_next_round_fixtures")
def test_coverage_pct_and_isolation(mock_select, mock_list_odds):
    now = datetime.now(timezone.utc)
    f1 = _fx(1, now + timedelta(days=2))
    f2 = _fx(2, now + timedelta(days=3))
    mock_select.return_value = MagicMock(fixtures=[f1, f2], final_round="R18")

    odd = MagicMock()
    odd.fixture_id = 1
    odd.bookmaker_name = "Sisal"
    odd.provider_source = "sportapi"
    odd.provider_bookmaker_id = "1"
    odd.home_odds = 2.0
    odd.draw_odds = 3.0
    odd.away_odds = 4.0
    odd.odds_updated_at = now
    mock_list_odds.return_value = [odd]

    comp = MagicMock()
    comp.id = 99
    comp.key = "test_league"

    db = MagicMock()
    svc = BookmakerCoverageService(comp_svc=MagicMock())
    svc._comp_svc.get_by_id_or_raise.return_value = comp
    db.scalars.return_value.all.return_value = [f1, f2]
    db.get.return_value = MagicMock(name="Home")

    out = svc.get_coverage(db, 99, only_next_round=True, market="MATCH_WINNER_1X2")

    assert out["competition_id"] == 99
    assert out["fixtures_total"] == 2
    assert out["fixtures_with_odds"] == 1
    assert out["coverage_pct"] == 50.0
    mock_list_odds.assert_called_once()
    call_kw = mock_list_odds.call_args.kwargs
    assert call_kw["competition_id"] == 99
