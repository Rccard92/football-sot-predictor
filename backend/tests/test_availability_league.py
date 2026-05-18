"""Risoluzione league internal vs api_league_id."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.availability.availability_league import (
    AvailabilityLeagueConfigError,
    SerieALeagueContext,
    resolve_serie_a_league_context,
)


@patch("app.services.availability.availability_league.IngestionService")
def test_resolve_serie_a_league_context_internal_vs_api(mock_ing_cls):
    db = MagicMock()
    season_row = MagicMock()
    season_row.id = 10
    season_row.league_id = 1
    mock_ing_cls.return_value._serie_a_season_row.return_value = season_row

    league = MagicMock()
    league.id = 1
    league.api_league_id = 135
    league.name = "Serie A"
    db.scalar.return_value = league

    ctx = resolve_serie_a_league_context(db, 2025)
    assert ctx == SerieALeagueContext(
        league_internal_id=1,
        api_league_id=135,
        league_name="Serie A",
        season_row_id=10,
    )


@patch("app.services.availability.availability_league.IngestionService")
def test_resolve_serie_a_league_context_missing_api_id(mock_ing_cls):
    db = MagicMock()
    season_row = MagicMock()
    season_row.id = 10
    season_row.league_id = 1
    mock_ing_cls.return_value._serie_a_season_row.return_value = season_row

    league = MagicMock()
    league.id = 1
    league.api_league_id = None
    league.name = "Serie A"
    db.scalar.return_value = league

    with pytest.raises(AvailabilityLeagueConfigError, match="API league id mancante"):
        resolve_serie_a_league_context(db, 2025)
