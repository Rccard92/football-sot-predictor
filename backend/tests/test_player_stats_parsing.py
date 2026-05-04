"""Test parser statistiche giocatore (formato annidato API-Sports)."""

from app.services.player_stats_parsing import parse_fixture_player_statistics


def test_parse_nested_v3_shots_and_minutes():
    stats = [
        {
            "games": {
                "minutes": 90,
                "position": "F",
                "rating": "7.2",
                "captain": False,
                "substitute": False,
            },
            "shots": {"total": 4, "on": 2},
            "goals": {"total": 1, "assists": 0},
            "passes": {"total": 20, "key": 2, "accuracy": "83%"},
            "tackles": {"total": 1, "blocks": 0, "interceptions": 1},
            "duels": {"total": 5, "won": 3},
            "dribbles": {"attempts": 2, "success": 1},
            "fouls": {"drawn": 1, "committed": 0},
            "cards": {"yellow": 0, "red": 0},
        },
    ]
    out = parse_fixture_player_statistics(stats)
    assert out["minutes"] == 90
    assert out["position"] == "F"
    assert out["rating"] == 7.2
    assert out["shots_total"] == 4
    assert out["shots_on_target"] == 2
    assert out["passes_key"] == 2
    assert out["passes_accuracy_pct"] == 83.0
    assert out["fouls_drawn"] == 1


def test_parse_flat_legacy_type_value():
    stats = [
        {"type": "Shots on Goal", "value": 3},
        {"type": "Minutes played", "value": "45"},
    ]
    out = parse_fixture_player_statistics(stats)
    assert out["shots_on_target"] == 3
    assert out["minutes"] == 45
