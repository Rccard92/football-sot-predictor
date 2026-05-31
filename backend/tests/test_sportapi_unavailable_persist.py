"""Test persist unavailable SportAPI (Step K.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.sportapi.sportapi_unavailable_parser import NormalizedUnavailableRow
from app.services.sportapi.sportapi_unavailable_persist_service import SportApiUnavailablePersistService


def _row(*, fid: int = 146, side: str = "home", pid: int = 10) -> NormalizedUnavailableRow:
    return NormalizedUnavailableRow(
        fixture_id=fid,
        provider_fixture_id=999,
        team_id=1,
        provider_team_id=101,
        player_id=None,
        provider_player_id=pid,
        player_name="Player",
        status="injured",
        reason="injury",
        raw_status="injury",
        source_path="lineups.home.missingPlayers",
        team_side=side,
        raw_json={"player": {"id": pid}},
    )


def test_persist_dry_run_no_delete():
    db = MagicMock()
    result = SportApiUnavailablePersistService().persist_rows(
        db,
        rows=[_row()],
        fixture_id=146,
        competition_id=1,
        provider_lineup_id=5,
        dry_run=True,
    )
    assert result["would_write_count"] == 1
    assert result["written_count"] == 0
    db.execute.assert_not_called()
    db.add.assert_not_called()


@patch("app.services.sportapi.sportapi_unavailable_persist_service.delete")
def test_persist_writes_and_deletes(mock_delete):
    db = MagicMock()
    result = SportApiUnavailablePersistService().persist_rows(
        db,
        rows=[_row(), _row(pid=11, side="away")],
        fixture_id=146,
        competition_id=1,
        provider_lineup_id=5,
        dry_run=False,
        force_refresh=True,
    )
    assert result["written_count"] == 2
    mock_delete.assert_called_once()
    assert db.add.call_count == 2
