"""Ingestion availability — filtri e isolamento package."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_ingestion import _item_in_scope, ingest_serie_a_availability


def test_item_in_scope_fixture_filter():
    item = {"fixture": {"id": 100}, "team": {"id": 1}}
    assert _item_in_scope(item, api_fixture_ids=None, api_team_ids=None, single_api_fixture_id=100) is True
    assert _item_in_scope(item, api_fixture_ids=None, api_team_ids=None, single_api_fixture_id=200) is False


def test_item_in_scope_horizon_set():
    item = {"fixture": {"id": 55}, "team": {"id": 1}}
    assert _item_in_scope(item, api_fixture_ids={55, 66}, api_team_ids=None, single_api_fixture_id=None) is True
    assert _item_in_scope(item, api_fixture_ids={66}, api_team_ids=None, single_api_fixture_id=None) is False


def test_availability_package_no_predictions_import():
    import importlib

    mod = importlib.import_module("app.services.availability.availability_ingestion")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "predictions_v11" not in src
    assert "sot_fixture_explanation_service" not in src


@patch("app.services.availability.availability_ingestion.ApiFootballClient")
@patch("app.services.availability.availability_ingestion.IngestionService")
def test_ingest_empty_api_returns_success_zero(mock_ing_cls, mock_client_cls):
    db = MagicMock()
    season_row = MagicMock()
    season_row.id = 1
    season_row.league_id = 135
    season_row.year = 2025
    mock_ing_cls.return_value._serie_a_season_row.return_value = season_row
    mock_client_cls.return_value.get_injuries.return_value = []

    db.scalars.return_value.all.return_value = []

    summary = ingest_serie_a_availability(db, 2025, client=mock_client_cls.return_value)
    assert summary["status"] == "success"
    assert summary["availability_records_upserted"] == 0
    assert summary["api_calls"] == 1
