"""Test lookup/matching profili lineup multi-campionato."""

from app.services.sportapi.lineup_player_profile_lookup import (
    compute_lineup_mapping_stats,
    compute_player_mapping_quality_for_side,
    score_profile_match,
)
from app.services.sportapi.sportapi_lineup_impact_logic import compute_impact_confidence
from app.services.sportapi.sportapi_player_name_normalize import fuzzy_player_name_score, player_names_match


def test_player_names_match_sao_variants():
    assert player_names_match("São Paulo", "Sao Paulo")
    assert player_names_match("Atlético Mineiro", "Atletico Mineiro")


def test_fuzzy_player_name_score_compound_surname():
    score = fuzzy_player_name_score("Gabriel Barbosa", "Gabriel")
    assert score >= 0.75


def test_score_profile_match_exact_team():
    cand = {
        "name": "Gabriel Barbosa",
        "normalized_name": "gabriel barbosa",
        "team_id": 10,
        "position": "A",
        "jersey_number": 9,
    }
    total, breakdown, reason = score_profile_match(
        sportapi_name="Gabriel Barbosa",
        sportapi_short=None,
        sportapi_position="A",
        sportapi_jersey=9,
        candidate=cand,
        same_team=True,
        same_competition=True,
    )
    assert total >= 90
    assert breakdown.get("name") == 50 or breakdown.get("name_fuzzy", 0) >= 35
    assert reason


def test_compute_lineup_mapping_stats():
    lineups = {
        "home": {"starters": [{"provider_player_id": 1}, {"provider_player_id": 2}]},
        "away": {"starters": []},
    }
    matches = [
        {"sportapi_player_id": 1, "recommendation": "AUTO_SAFE", "api_sports_player_id": 100},
        {"sportapi_player_id": 2, "recommendation": "NO_MATCH"},
    ]
    stats = compute_lineup_mapping_stats(lineups, matches)
    assert stats["starters_total"] == 2
    assert stats["starters_matched_auto_safe"] == 1
    assert stats["mapping_rate"] == 0.5


def test_confidence_profiles_present_unmapped():
    label, reasons = compute_impact_confidence(
        confirmed=False,
        top_players=[],
        profiles_missing=False,
        player_profiles_count=50,
        lineup_mapping_stats={"starters_total": 11, "starters_matched_auto_safe": 0},
    )
    assert label in ("media", "bassa")
    assert any("non mappati" in r for r in reasons)


def test_confidence_partial_mapping():
    label, reasons = compute_impact_confidence(
        confirmed=True,
        top_players=[],
        profiles_missing=False,
        player_profiles_count=100,
        lineup_mapping_stats={"starters_total": 11, "starters_matched_auto_safe": 6},
    )
    assert any("Mapping parziale" in r for r in reasons)
    assert any("Confidence ridotta" in r for r in reasons)


def test_confidence_no_profiles():
    _label, reasons = compute_impact_confidence(
        confirmed=True,
        top_players=[],
        profiles_missing=True,
        player_profiles_count=0,
    )
    assert any("non ancora generati" in r for r in reasons)


def test_confidence_good_mapping_no_profile_warning():
    label, reasons = compute_impact_confidence(
        confirmed=True,
        top_players=[],
        profiles_missing=False,
        player_profiles_count=200,
        lineup_mapping_stats={"starters_total": 11, "starters_matched_auto_safe": 9},
    )
    assert not any("non ancora generati" in r for r in reasons)
    assert not any("player_sot_profiles" in r for r in reasons)
    assert label in ("alta", "media")


def test_compute_player_mapping_quality_for_side_nine_auto_safe():
    lineups = {
        "home": {
            "starters": [{"provider_player_id": i} for i in range(1, 12)],
        },
        "away": {"starters": []},
    }
    matches = []
    for i in range(1, 10):
        matches.append(
            {
                "sportapi_player_id": i,
                "recommendation": "AUTO_SAFE",
                "api_sports_player_id": 100 + i,
                "confidence_score": 92,
                "shots_on_per90": 0.5,
            }
        )
    matches.append(
        {
            "sportapi_player_id": 10,
            "recommendation": "REVIEW",
            "api_sports_player_id": 110,
            "confidence_score": 75,
            "shots_on_per90": 0.3,
        }
    )
    matches.append({"sportapi_player_id": 11, "recommendation": "NO_MATCH"})

    quality = compute_player_mapping_quality_for_side("home", lineups, matches)
    assert quality["starters_total"] == 11
    assert quality["starters_auto_safe"] == 9
    assert quality["starters_mapped"] == 10
    assert quality["mapping_confidence"] > 70
    assert quality["mapping_quality_label"] in ("good", "partial")
