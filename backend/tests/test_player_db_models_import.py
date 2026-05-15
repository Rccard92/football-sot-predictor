"""Verifica import modelli Player DB (no circular import)."""


def test_player_db_models_tabulenames():
    from app.models import (
        PlayerMatchStat,
        PlayerRegistry,
        PlayerSeasonProfile,
        PlayerTeamSeason,
    )

    assert PlayerRegistry.__tablename__ == "player_registry"
    assert PlayerTeamSeason.__tablename__ == "player_team_seasons"
    assert PlayerMatchStat.__tablename__ == "player_match_stats"
    assert PlayerSeasonProfile.__tablename__ == "player_season_profiles"


def test_import_app_main_still_works():
    from app.main import app

    assert app.title
