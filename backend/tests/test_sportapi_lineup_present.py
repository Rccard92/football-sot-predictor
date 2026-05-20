"""Unit test presentazione lineups SportAPI."""

from app.services.sportapi.sportapi_lineup_present import (
    build_tactical_lines,
    classify_missing_group,
    to_display_role,
)
from app.services.sportapi.sportapi_payload import extract_events_list


def test_to_display_role_mapping():
    assert to_display_role("G") == "P"
    assert to_display_role("GK") == "P"
    assert to_display_role("D") == "D"
    assert to_display_role("M") == "C"
    assert to_display_role("F") == "A"
    assert to_display_role(None) == "C"


def test_classify_missing_suspended():
    assert (
        classify_missing_group(
            reason=None,
            description="red_card_suspension",
            external_type=None,
        )
        == "suspended"
    )


def test_classify_missing_injured():
    assert (
        classify_missing_group(
            reason="1",
            description=None,
            external_type=None,
        )
        == "injured"
    )
    assert (
        classify_missing_group(
            reason=None,
            description="Muscle Injury",
            external_type=None,
        )
        == "injured"
    )


def test_extract_events_list():
    ev = {"id": 1}
    assert extract_events_list({"events": [ev]}) == [ev]


def test_build_tactical_lines_433():
    starters = [
        {
            "provider_player_id": 1,
            "player_name": "GK",
            "display_role": "P",
            "original_index": 0,
            "_raw_payload": {},
        },
        *[
            {
                "provider_player_id": 10 + i,
                "player_name": f"D{i}",
                "display_role": "D",
                "original_index": i + 1,
                "_raw_payload": {},
            }
            for i in range(4)
        ],
        *[
            {
                "provider_player_id": 20 + i,
                "player_name": f"C{i}",
                "display_role": "C",
                "original_index": i + 5,
                "_raw_payload": {},
            }
            for i in range(3)
        ],
        *[
            {
                "provider_player_id": 30 + i,
                "player_name": f"A{i}",
                "display_role": "A",
                "original_index": i + 8,
                "_raw_payload": {},
            }
            for i in range(3)
        ],
    ]
    lines = build_tactical_lines("4-3-3", starters)
    assert len(lines) == 4
    assert len(lines[0]) == 1
    assert lines[0][0]["display_role"] == "P"
    assert len(lines[1]) == 4
    assert len(lines[2]) == 3
    assert len(lines[3]) == 3


def test_fiorentina_atalanta_score_roles():
    """Caso test: ruoli e modulo coerenti con payload SportAPI tipico."""
    ev_starters = [
        {"display_role": "P", "original_index": 0, "_raw_payload": {}, "provider_player_id": 1, "player_name": "De Gea"},
        {"display_role": "D", "original_index": 1, "_raw_payload": {}, "provider_player_id": 2, "player_name": "Dodo"},
        {"display_role": "D", "original_index": 2, "_raw_payload": {}, "provider_player_id": 3, "player_name": "Pongracic"},
        {"display_role": "D", "original_index": 3, "_raw_payload": {}, "provider_player_id": 4, "player_name": "Comuzzo"},
        {"display_role": "D", "original_index": 4, "_raw_payload": {}, "provider_player_id": 5, "player_name": "Gosens"},
        {"display_role": "C", "original_index": 5, "_raw_payload": {}, "provider_player_id": 6, "player_name": "Fagioli"},
        {"display_role": "C", "original_index": 6, "_raw_payload": {}, "provider_player_id": 7, "player_name": "Ndour"},
        {"display_role": "C", "original_index": 7, "_raw_payload": {}, "provider_player_id": 8, "player_name": "Brescianini"},
        {"display_role": "A", "original_index": 8, "_raw_payload": {}, "provider_player_id": 9, "player_name": "Harrison"},
        {"display_role": "A", "original_index": 9, "_raw_payload": {}, "provider_player_id": 10, "player_name": "Piccoli"},
        {"display_role": "A", "original_index": 10, "_raw_payload": {}, "provider_player_id": 11, "player_name": "Solomon"},
    ]
    lines = build_tactical_lines("4-3-3", ev_starters)
    assert len(lines) == 4
    assert sum(len(row) for row in lines) == 11
