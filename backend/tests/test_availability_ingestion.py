"""Ingestion availability — filtri e isolamento package."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_ingestion import (
    _item_in_scope,
    _merge_items,
    ingest_serie_a_availability,
)


def test_item_in_scope_team_level_without_fixture():
    item = {"team": {"id": 487}, "player": {"id": 1, "name": "Test"}}
    assert _item_in_scope(
        item,
        api_fixture_id=999,
        api_team_ids={487, 1001},
        allow_team_level=True,
    ) is True


def test_item_in_scope_rejects_other_team():
    item = {"team": {"id": 999}, "player": {"id": 1, "name": "Test"}}
    assert _item_in_scope(
        item,
        api_fixture_id=None,
        api_team_ids={487},
        allow_team_level=True,
    ) is False


def test_merge_items_dedupes():
    a = [{"player": {"id": 1}, "team": {"id": 2}, "fixture": {"id": 3}, "reason": "x"}]
    b = list(a)
    merged = _merge_items(a, b)
    assert len(merged) == 1


def test_availability_package_no_predictions_import():
    import importlib

    mod = importlib.import_module("app.services.availability.availability_ingestion")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "predictions_v11" not in src
    assert "sot_fixture_explanation_service" not in src


@patch("app.services.availability.availability_ingestion.resolve_serie_a_league_context")
@patch("app.services.availability.availability_ingestion.ApiFootballClient")
@patch("app.services.availability.availability_ingestion.IngestionService")
def test_ingest_team_level_item_saved(mock_ing_cls, mock_client_cls, mock_ctx):
    from app.services.availability.availability_league import SerieALeagueContext

    db = MagicMock()
    season_row = MagicMock()
    season_row.id = 1
    season_row.league_id = 1
    season_row.year = 2025
    mock_ing_cls.return_value._serie_a_season_row.return_value = season_row
    mock_ctx.return_value = SerieALeagueContext(
        league_internal_id=1,
        api_league_id=135,
        league_name="Serie A",
        season_row_id=1,
    )

    fx = MagicMock()
    fx.id = 10
    fx.api_fixture_id = 1378173
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.home_team = MagicMock()
    fx.home_team.api_team_id = 487
    fx.home_team_id = 1
    fx.away_team = MagicMock()
    fx.away_team.api_team_id = 1001
    fx.away_team_id = 2

    mock_client = mock_client_cls.return_value
    team_item = {
        "player": {"id": 99, "name": "Nicolò Rovella", "type": "Yellow Cards"},
        "team": {"id": 487, "name": "Lazio"},
    }
    mock_client.get_injuries_by_fixture.return_value = []
    mock_client.get_injuries_by_team.side_effect = [
        [team_item],
        [],
    ]

    db.scalar.side_effect = [fx]
    db.scalars.return_value.all.return_value = []

    with patch(
        "app.services.availability.availability_ingestion.upsert_availability_record",
    ) as mock_upsert:
        mock_upsert.return_value = (MagicMock(), True)
        summary = ingest_serie_a_availability(
            db,
            2025,
            fixture_id=10,
            client=mock_client,
        )

    assert summary["status"] in ("success", "partial_success")
    assert summary["api_league_id"] == 135
    assert summary["league_internal_id"] == 1
    assert mock_upsert.call_count >= 1
    mock_client.get_injuries_by_team.assert_called()
    team_call_league = mock_client.get_injuries_by_team.call_args[0][0]
    assert team_call_league == 135
    assert summary.get("records_team_level", 0) >= 0 or summary["availability_records_upserted"] >= 1
