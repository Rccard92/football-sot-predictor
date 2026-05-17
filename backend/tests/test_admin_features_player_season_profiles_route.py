def test_route_module_imports():
    from app.routes.admin_features_player_season_profiles import router

    assert router.prefix == "/admin/features/player-season-profiles"
