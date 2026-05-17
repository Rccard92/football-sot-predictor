from app.services.player_data.player_profiles_debug import profile_sort_key, sort_player_rows


def test_null_impact_sorts_last():
    rows = [
        {"name": "A", "shooting_impact_score": None, "shots_on_per90": 2.0, "minutes_total": 1000},
        {"name": "B", "shooting_impact_score": 90.0, "shots_on_per90": 1.0, "minutes_total": 500},
        {"name": "C", "shooting_impact_score": 70.0, "shots_on_per90": 0.5, "minutes_total": 800},
    ]
    ordered = sort_player_rows(rows)
    assert [r["name"] for r in ordered] == ["B", "C", "A"]


def test_tie_break_shots_on_per90_then_minutes():
    rows = [
        {"name": "low_sot", "shooting_impact_score": 50.0, "shots_on_per90": 0.5, "minutes_total": 2000},
        {"name": "high_sot", "shooting_impact_score": 50.0, "shots_on_per90": 1.5, "minutes_total": 100},
        {"name": "more_min", "shooting_impact_score": 50.0, "shots_on_per90": 1.5, "minutes_total": 900},
    ]
    ordered = sort_player_rows(rows)
    assert [r["name"] for r in ordered] == ["more_min", "high_sot", "low_sot"]


def test_profile_sort_key_null_impact_is_inf():
    k_null = profile_sort_key({"shooting_impact_score": None, "shots_on_per90": 1.0, "minutes_total": 100})
    k_val = profile_sort_key({"shooting_impact_score": 10.0, "shots_on_per90": 1.0, "minutes_total": 100})
    assert k_null > k_val


def test_debug_sot_player_profiles_route_registered():
    from app.routes.debug_sot import router

    paths = [getattr(r, "path", "") for r in router.routes]
    assert any("player-profiles" in p for p in paths)
