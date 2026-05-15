from app.services.player_data.fixtures_players_statistics import extract_statistics_row_nullable


def test_nested_v3_nullable_no_default_zero_for_shots():
    statistics = [
        {
            "games": {"minutes": None, "rating": "7.1", "substitute": False},
            "shots": {"total": None, "on": None},
            "goals": {"total": 1, "assists": None},
            "passes": {"total": 10, "key": None, "accuracy": "80%"},
            "dribbles": {},
            "fouls": {},
            "cards": {},
            "penalties": {},
        },
    ]
    out = extract_statistics_row_nullable(statistics)
    assert out["minutes"] is None
    assert out["shots_total"] is None
    assert out["shots_on"] is None
    assert out["goals_total"] == 1
    assert out["goals_assists"] is None
    assert out["passes_accuracy"] == 80.0
    assert out["rating"] == 7.1
